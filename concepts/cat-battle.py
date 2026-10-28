#!/usr/bin/env python3
"""Cat Battle — 4 cats bounce in a shrinking arena. Every crash = -1 HP for the cat that gets hit.
Last cat standing wins (crown + confetti).

Autonomous: numpy + pillow + scipy + ffmpeg. 1080x1920, 60 fps, H.264 + AAC.
Characters: round PNGs from assets/ (Yanis). Audio: sounds/fah.mp3 on every crash
(--sound-mode word) + original synthesized effects (bonk, boom, riser, fanfare).

    python3 cat-battle.py --seed 3 --out out.mp4
"""
import argparse, os, subprocess, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter
from scipy.signal import resample

W, H, FPS = 1080, 1920, 60
CX, CY = 540, 1090
R0, R1 = 430, 250                 # arena radius: start -> end (shrinks)
CR = 72                           # cat radius on screen (<= 100 px, assets are small)
SR = 44100
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CATS = [  # file, name, team color
    ("chat-rire.png", "LOL", (255, 170, 30)),
    ("chat-noir.png", "BRUH", (170, 90, 255)),
    ("chat-what.png", "WHAT", (255, 70, 90)),
    ("chat-gris.png", "OMG", (60, 220, 255)),
]


def font(size):
    for p in ("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


_tm = {}


def text_mask(txt, size, stroke=0):
    k = (txt, size, stroke)
    if k in _tm:
        return _tm[k]
    f = font(size)
    tmp = Image.new("L", (10, 10))
    b = ImageDraw.Draw(tmp).textbbox((0, 0), txt, font=f, stroke_width=stroke)
    im = Image.new("L", (b[2] - b[0] + 8, b[3] - b[1] + 8), 0)
    ImageDraw.Draw(im).text((4 - b[0], 4 - b[1]), txt, font=f, fill=255, stroke_width=stroke)
    _tm[k] = np.asarray(im, np.float32) / 255.0
    return _tm[k]


def blit_text(img, mask, cx, cy, color, gain=1.0, shadow=True):
    if shadow:
        _blit(img, mask, cx + 5, cy + 6, (0, 0, 0), gain * 0.75)
    _blit(img, mask, cx, cy, color, gain)


def _blit(img, mask, cx, cy, color, gain):
    h, w = mask.shape
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if xa >= xb or ya >= yb or gain <= 0:
        return
    m = mask[ya - y0:yb - y0, xa - x0:xb - x0, None] * gain
    img[ya:yb, xa:xb] = img[ya:yb, xa:xb] * (1 - m) + np.asarray(color, np.float32) * m


def blit_rgba(img, rgba, cx, cy, gain=1.0):
    h, w = rgba.shape[:2]
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if xa >= xb or ya >= yb:
        return
    s = rgba[ya - y0:yb - y0, xa - x0:xb - x0]
    a = s[..., 3:4] * gain
    img[ya:yb, xa:xb] = img[ya:yb, xa:xb] * (1 - a) + s[..., :3] * a


def disc(r, color, ring=0, ring_color=(255, 255, 255)):
    """anti-aliased disc (optionally only a ring) as float RGBA."""
    n = int(np.ceil(r)) + 3
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1]
    d = np.sqrt(xx ** 2 + yy ** 2)
    a = np.clip(r + 0.5 - d, 0, 1)
    if ring:
        a = a * np.clip(d - (r - ring) + 0.5, 0, 1)
    out = np.zeros(d.shape + (4,), np.float32)
    out[..., :3] = color
    out[..., 3] = a
    return out


class CatSprites:
    def __init__(self, path, color):
        self.src = Image.open(path).convert("RGBA")
        self.color = color
        self.cache = {}

    def get(self, rx, ry, grey=False):
        k = (int(rx), int(ry), grey)
        if k not in self.cache:
            sw, sh = max(2 * k[0], 4), max(2 * k[1], 4)
            im = self.src.resize((sw, sh), Image.LANCZOS)
            # soft round mask (anti-aliased edge) + colored team ring
            yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
            e = np.sqrt(((xx + 0.5 - sw / 2) / (sw / 2)) ** 2 + ((yy + 0.5 - sh / 2) / (sh / 2)) ** 2)
            arr = np.asarray(im, np.float32) / 255.0
            rgb = arr[..., :3] * 255
            if grey:
                g = rgb.mean(2, keepdims=True)
                rgb = np.repeat(g, 3, 2) * 0.6
            a = np.clip((1 - e) * min(sw, sh) / 2 + 0.5, 0, 1) * np.maximum(arr[..., 3], (e < 0.97))
            ring = np.clip(1 - np.abs(e - 0.95) * min(sw, sh) / 2 / 4.5, 0, 1)
            rgb = rgb * (1 - ring[..., None]) + np.asarray(self.color, np.float32) * ring[..., None]
            self.cache[k] = np.dstack([rgb, a]).astype(np.float32)
        return self.cache[k]


# ------------------------------------------------------------ simulation ----
def simulate(args):
    rng = np.random.default_rng(args.seed)
    n = len(CATS)
    pos = np.array([[CX + 230 * np.cos(a), CY + 230 * np.sin(a)]
                    for a in np.linspace(0, 2 * np.pi, n, endpoint=False) + 0.4], np.float64)
    ang = rng.uniform(0, 2 * np.pi, n)
    vel = np.stack([np.cos(ang), np.sin(ang)], 1) * args.speed
    hp = np.full(n, args.hp)
    alive = np.ones(n, bool)
    squash = np.zeros(n)
    sq_dir = np.zeros((n, 2))
    dt = 1.0 / FPS
    frames, events = [], []
    crashes = 0
    pair_t = {}
    T, winner = None, None
    t = 0.0
    R = R0
    while True:
        if T is None:
            R_target = {4: R0, 3: 390, 2: R1}.get(int(alive.sum()), R1)
            R = max(R_target, R - 45 * dt)
            spd = args.speed * (1 + 0.035 * crashes)
            sub = 4
            for _ in range(sub):
                h = dt / sub
                pos[alive] += vel[alive] * h
                # walls
                for i in np.nonzero(alive)[0]:
                    rel = pos[i] - (CX, CY)
                    d = np.linalg.norm(rel)
                    if d > R - CR:
                        nr = rel / d
                        if np.dot(vel[i], nr) > 0:
                            vel[i] -= 2 * np.dot(vel[i], nr) * nr
                            # small random kick so it never loops
                            a = rng.uniform(-0.12, 0.12)
                            c, s = np.cos(a), np.sin(a)
                            vel[i] = (c * vel[i][0] - s * vel[i][1], s * vel[i][0] + c * vel[i][1])
                            events.append((t, "wall", pos[i][0]))
                            squash[i], sq_dir[i] = 1.0, nr
                        pos[i] = (CX, CY) + nr * (R - CR)
                # cat vs cat
                ids = np.nonzero(alive)[0]
                for a_ in range(len(ids)):
                    for b_ in range(a_ + 1, len(ids)):
                        i, j = ids[a_], ids[b_]
                        rel = pos[j] - pos[i]
                        d = np.linalg.norm(rel)
                        if d < 2 * CR and d > 1e-6:
                            nr = rel / d
                            vrel = np.dot(vel[i] - vel[j], nr)
                            overlap = 2 * CR - d
                            pos[i] -= nr * overlap / 2
                            pos[j] += nr * overlap / 2
                            if vrel > 0:
                                vel_i_old = vel[i].copy()
                                vel[i] -= vrel * nr
                                vel[j] += vrel * nr
                                if t - pair_t.get((i, j), -9) < args.cooldown:
                                    continue        # bounce only, no damage (avoids double hits)
                                pair_t[(i, j)] = t
                                # attacker = the one pushing harder along the line of impact
                                push_i = np.dot(vel_i_old, nr)
                                push_j = vrel - push_i
                                loser = j if push_i >= push_j else i
                                hp[loser] -= 1
                                crashes += 1
                                mid = (pos[i] + pos[j]) / 2
                                events.append((t, "crash", mid[0]))
                                frames_ev = ("crash", loser, mid.copy(), t)
                                squash[i], sq_dir[i] = 1.0, nr
                                squash[j], sq_dir[j] = 1.0, -nr
                                if hp[loser] <= 0:
                                    alive[loser] = False
                                    events.append((t, "ko", pos[loser][0]))
                                frames.append(frames_ev)
            # keep speeds at the escalating target
            for i in np.nonzero(alive)[0]:
                v = np.linalg.norm(vel[i])
                vel[i] *= spd / max(v, 1e-6)
            if alive.sum() == 1:
                T = t
                winner = int(np.nonzero(alive)[0][0])
                events.append((t, "win", CX))
        squash *= 0.86
        frames.append(("state", pos.copy(), hp.copy(), alive.copy(), squash.copy(), sq_dir.copy(),
                       crashes, R if T is None else None, t))
        t += dt
        if T is not None and t - T > args.outro:
            break
        if t > 70:
            break
    return frames, events, T, winner, t


# --------------------------------------------------------------- render ----
def make_bg(args, rng):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    g = (yy / H)[..., None]
    bg = np.array([22, 10, 30], np.float32) * (1 - g) + np.array([8, 6, 14], np.float32) * g
    v = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)[..., None]
    bg = bg * np.clip(1.25 - v, 0.25, 1.1)
    stripes = (((xx + yy) % 90) < 45).astype(np.float32)[..., None] * np.array([6, 3, 8], np.float32)
    bg = bg + stripes + rng.normal(0, 2.0, (H, W, 1)).astype(np.float32)
    bg = np.clip(bg, 0, 255)
    lines = [args.title] if len(args.title) <= 22 else _wrap(args.title)
    for i, ln in enumerate(lines):
        blit_text(bg, text_mask(ln, 70 if len(ln) <= 22 else 58, 3), W / 2 - 40, 200 + i * 90, (255, 255, 255))
    blit_text(bg, text_mask(args.handle, 50, 2), W / 2, 1665, (255, 255, 255), 0.7)
    d = np.sqrt((xx - CX) ** 2 + (yy - CY) ** 2)
    return bg, d


def _wrap(t):
    w = t.split()
    k = min(range(1, len(w)), key=lambda i: abs(len(" ".join(w[:i])) - len(" ".join(w[i:]))))
    return [" ".join(w[:k]), " ".join(w[k:])]


def render(args, frames, T, winner, tmp_video):
    rng = np.random.default_rng(args.seed + 5)
    bg, dist = make_bg(args, rng)
    sprites = [CatSprites(os.path.join(ROOT, "assets", f), c) for f, _, c in CATS]
    icons = [s.get(48, 48) for s in sprites]
    icons_dead = [s.get(48, 48, grey=True) for s in sprites]
    heart_on, heart_off = disc(9, (255, 60, 90)), disc(9, (70, 60, 80))
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
         "-pix_fmt", "yuv420p", "-an", tmp_video], stdin=subprocess.PIPE)
    pops = []      # floating texts: (t0, x, y, text, color)
    parts = []     # particles: [x, y, vx, vy, t0, color]
    last_crash = -9
    count_pop = 0.0
    prev_crashes = 0
    shake_t = -9
    R_last = R0
    for fr in frames:
        if fr[0] == "crash":
            _, loser, mid, tc = fr
            last_crash = tc
            name = CATS[loser][1]
            pops.append((tc, mid[0], mid[1] - 40, "FAH!", (255, 255, 255)))
            for _ in range(14):
                a = rng.uniform(0, 2 * np.pi)
                parts.append([mid[0], mid[1], np.cos(a) * rng.uniform(200, 600), np.sin(a) * rng.uniform(200, 600),
                              tc, np.array(CATS[loser][2], np.float32)])
            continue
        _, pos, hp, alive, squash, sq_dir, crashes, R, t = fr
        if R is None:
            R = R_last
        R_last = R
        tt = None if T is None or t < T else t - T
        img = bg.copy()
        # arena ring with glow (color heats up with crashes)
        heat = min(crashes / 30.0, 1.0)
        rc = np.array([150, 80, 255], np.float32) * (1 - heat) + np.array([255, 70, 30], np.float32) * heat
        flash = max(0.0, 1 - (t - last_crash) * 6)
        band = np.clip(1 - np.abs(dist - (R + 6)) / 6.0, 0, 1)
        gl = np.clip(1 - np.abs(dist - (R + 6)) / 40.0, 0, 1) ** 2 * 0.35
        fade = 1.0 if tt is None else max(0.0, 1 - tt * 1.5)
        img += ((band + gl)[..., None] * (rc + 80 * flash)) * fade
        if tt is not None and tt < 1.2:     # shockwave
            sw = np.clip(1 - np.abs(dist - tt * 1700) / 30, 0, 1)[..., None] * (1 - tt / 1.2) ** 1.5
            img += sw * np.array([255, 210, 120], np.float32)
        # particles
        for p in parts:
            age = t - p[4]
            if 0 <= age < 0.7:
                x, y = p[0] + p[2] * age, p[1] + p[3] * age + 500 * age * age
                blit_rgba(img, disc(7 * (1 - age / 0.7) + 2, p[5]), x, y)
        # cats
        for i in range(len(CATS)):
            if not alive[i]:
                continue
            k = 1.0
            if tt is not None and i == winner:
                k = 1 + 0.35 * min(tt / 0.8, 1)
            s = squash[i] * 0.22
            ax = abs(sq_dir[i][0])
            rx = CR * k * (1 - s * ax + s * (1 - ax) * 0.6)
            ry = CR * k * (1 - s * (1 - ax) + s * ax * 0.6)
            px, py = pos[i]
            if tt is not None and i == winner:
                e = min(tt / 0.8, 1)
                e = e * e * (3 - 2 * e)
                px, py = px + (CX - px) * e, py + (CY - py) * e
            blit_rgba(img, sprites[i].get(rx, ry), px, py)
            # small hp bar above cat
            if tt is None:
                frac = hp[i] / args.hp
                bx0, bx1, by = int(px - 60), int(px + 60), int(py - ry - 22)
                if 0 < by < H - 10 and bx0 > 0 and bx1 < W:
                    img[by - 6:by + 6, bx0:bx1] = img[by - 6:by + 6, bx0:bx1] * 0.3
                    c = np.array([90, 255, 90], np.float32) * frac + np.array([255, 50, 50], np.float32) * (1 - frac)
                    img[by - 4:by + 4, bx0 + 2:bx0 + 2 + int((bx1 - bx0 - 4) * frac)] = c
        # winner crown + confetti
        if tt is not None:
            e = min(tt / 0.8, 1)
            cy_top = CY - CR * (1 + 0.35 * e) - 30
            if tt > 0.6:
                a_ = min((tt - 0.6) * 4, 1)
                crown = Image.new("L", (240, 150), 0)
                ImageDraw.Draw(crown).polygon([(10, 140), (230, 140), (230, 30), (175, 80), (120, 5), (65, 80), (10, 30)],
                                              fill=255)
                cm = np.asarray(crown.resize((240, 150), Image.LANCZOS), np.float32) / 255
                bob = 8 * np.sin(tt * 6)
                _blit(img, cm, CX, cy_top - 60 + bob, (255, 205, 40), a_)
            for j in range(90):
                r2 = np.random.default_rng(j)
                x0, sp = r2.uniform(0, W - 140), r2.uniform(350, 700)
                y = -40 + (tt - r2.uniform(0, 0.8)) * sp
                if 0 < y < 1640:
                    c = np.array(CATS[r2.integers(0, 4)][2], np.float32)
                    x = x0 + 30 * np.sin(tt * 4 + j)
                    img[int(y):int(y) + 18, int(x):int(x) + 10] = c
            fl = np.exp(-tt * 6) * 200
            img += fl
        # counter: CRASHES
        if crashes != prev_crashes:
            count_pop, prev_crashes = 1.0, crashes
        count_pop *= 0.85
        size = int(150 * (1 + 0.35 * count_pop))
        blit_text(img, text_mask(str(crashes), size, 4), W / 2 - 160, 420,
                  np.array([255, 220, 60], np.float32) * (1 - heat) + np.array([255, 90, 50], np.float32) * heat)
        blit_text(img, text_mask("CRASHES", 54, 2), W / 2 + 120, 440, (255, 255, 255), 0.9)
        # roster: icon + name + hearts
        for i, (f, name, c) in enumerate(CATS):
            x = 115 + i * 200
            y = 560
            blit_rgba(img, icons[i] if alive[i] else icons_dead[i], x - 40, y)
            blit_text(img, text_mask(name, 34, 2), x + 45, y - 22, c if alive[i] else (110, 110, 110), shadow=False)
            for h_ in range(args.hp):
                hx = x + 6 + (h_ % 5) * 20
                hy = y + 12 + (h_ // 5) * 20
                blit_rgba(img, heart_on if h_ < hp[i] else heart_off, hx, hy)
            if not alive[i]:
                blit_text(img, text_mask("X", 90, 3), x - 40, y, (255, 40, 40), 0.9, shadow=False)
        # floating texts
        for (t0, x, y, txt, col) in pops:
            age = t - t0
            if 0 <= age < 0.55:
                s = min(age * 12, 1) * (1 - max(0, age - 0.35) / 0.2)
                blit_text(img, text_mask(txt, int(84 + 40 * max(0, 0.15 - age) / 0.15), 4),
                          min(max(x, 160), 880), y - 120 * age, (255, 230, 60), s)
        if tt is not None:
            wname = CATS[winner][1]
            a_ = min(max(tt - 0.4, 0) * 4, 1)
            blit_text(img, text_mask("WINNER!", 150, 5), W / 2, CY + 330, (255, 210, 40), a_)
            blit_text(img, text_mask(wname, 110, 4), W / 2, CY + 470, CATS[winner][2], a_)
        out = np.clip(img, 0, 255).astype(np.uint8)
        sh = 0
        if t - last_crash < 0.15:
            sh = int(10 * (1 - (t - last_crash) / 0.15))
        if tt is not None and tt < 0.6:
            sh = int(24 * np.exp(-tt * 6))
        if sh:
            out = np.roll(out, (sh * (1 if int(t * 60) % 2 else -1), sh * (1 if int(t * 60) % 3 else -1)), (0, 1))
        ff.stdin.write(out.tobytes())
    ff.stdin.close()
    ff.wait()


# ---------------------------------------------------------------- audio ----
def load_word(path):
    with tempfile.TemporaryDirectory() as td:
        w = os.path.join(td, "w.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(SR), w], check=True)
        with wave.open(w) as f:
            s = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32) / 32768
    s = s[:int(0.9 * SR)]
    fade = int(0.08 * SR)
    s[-fade:] *= np.linspace(1, 0, fade)
    return s / max(np.abs(s).max(), 1e-6)


def synth(events, T, total, args):
    rng = np.random.default_rng(args.seed + 1)
    N = int((total + 1.0) * SR)
    L = np.zeros(N, np.float32)
    Rr = np.zeros(N, np.float32)

    def add(sig, t0, pan=0.5, gain=1.0):
        i0 = int(t0 * SR)
        if i0 >= N or i0 < 0:
            return
        seg = sig[:N - i0]
        L[i0:i0 + len(seg)] += seg * gain * (1 - pan) ** 0.5
        Rr[i0:i0 + len(seg)] += seg * gain * pan ** 0.5

    def tone(f, dur=0.5, decay=6.5):
        t = np.arange(int(dur * SR)) / SR
        env = np.exp(-t * decay) * np.minimum(t / 0.004, 1)
        return ((np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) * np.exp(-t * 9)) * env).astype(np.float32)

    def bonk(f0):
        d = int(0.12 * SR)
        t = np.arange(d) / SR
        f = f0 * (1 + 1.5 * np.exp(-t * 60))
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 30)).astype(np.float32)

    word = load_word(os.path.join(ROOT, "sounds", "fah.mp3")) if args.sound_mode == "word" else None
    last_word = -9
    for (t, kind, x) in events:
        pan = float(np.clip(x / W, 0.15, 0.85))
        if kind == "wall":
            add(bonk(rng.uniform(170, 230)), t, pan, 0.22)
        elif kind == "crash":
            if word is not None and t - last_word > 0.14:
                last_word = t
                p = rng.uniform(0.87, 1.15)
                add(resample(word, int(len(word) / p)).astype(np.float32), t, pan, 0.75)
            add(bonk(110), t, pan, 0.45)
            if word is None:
                add(tone(rng.choice([523, 587, 659, 784]), 0.3, 9), t, pan, 0.3)
        elif kind == "ko":
            n_i = int(0.9 * SR)
            ti = np.arange(n_i) / SR
            f = 45 + 130 * np.exp(-ti * 10)
            imp = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-ti * 4) + rng.normal(0, 1, n_i) * np.exp(-ti * 14) * 0.6
            add(np.tanh(2.5 * imp).astype(np.float32), t, pan, 0.6)
    # riser into the win, then boom + fanfare (synthesized)
    rd = 2.5
    n_r = int(rd * SR)
    tr = np.arange(n_r) / SR
    ph = 2 * np.pi * np.cumsum(200 * (1800 / 200) ** (tr / rd)) / SR
    env = (tr / rd) ** 2
    add(((0.5 * np.sin(ph) + 0.25 * rng.normal(0, 1, n_r) * env) * env).astype(np.float32), T - rd, 0.5, 0.25)
    n_i = int(1.2 * SR)
    ti = np.arange(n_i) / SR
    imp = np.sin(2 * np.pi * np.cumsum(40 + 150 * np.exp(-ti * 9)) / SR) * np.exp(-ti * 3.2)
    add(np.tanh(3 * (imp + 0.6 * rng.normal(0, 1, n_i) * np.exp(-ti * 12))).astype(np.float32), T, 0.5, 0.8)
    for k_, (f, dtt) in enumerate([(523.3, 0.5), (659.3, 0.65), (784.0, 0.8), (1046.5, 0.95)]):
        add(tone(f, 1.2 if k_ == 3 else 0.4, 3 if k_ == 3 else 7), T + dtt, 0.5, 0.35)
    if word is not None:
        add(word, T + 1.3, 0.5, 0.9)
    st = np.tanh(1.2 * np.stack([L, Rr], 1))
    st *= 0.85 / max(np.abs(st).max(), 1e-6)
    return (st * 32767).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--title", default="Every crash = -1 HP")
    ap.add_argument("--handle", default="@novalabs.hq")
    ap.add_argument("--sound-mode", default="word", choices=["word", "effects"])
    ap.add_argument("--character", default="cats", choices=["cats"])
    ap.add_argument("--hp", type=int, default=10)
    ap.add_argument("--cooldown", type=float, default=0.8)
    ap.add_argument("--speed", type=float, default=360.0)
    ap.add_argument("--outro", type=float, default=3.6)
    ap.add_argument("--dry", action="store_true", help="simulate only, print timing")
    ap.add_argument("--out", default="cat-battle.mp4")
    args = ap.parse_args()

    frames, events, T, winner, total = simulate(args)
    ko = [round(e[0], 1) for e in events if e[1] == "ko"]
    print(f"seed {args.seed}: crashes {sum(e[1] == 'crash' for e in events)}, KOs at {ko}, "
          f"win at {T}, winner {CATS[winner][1] if winner is not None else None}, total {total:.1f}s")
    if args.dry or T is None:
        return
    with tempfile.TemporaryDirectory() as td:
        vid, wav = os.path.join(td, "v.mp4"), os.path.join(td, "a.wav")
        render(args, frames, T, winner, vid)
        pcm = synth(events, T, total, args)
        with wave.open(wav, "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-i", wav, "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart",
                        args.out], check=True)
    print(f"done: {args.out}")


if __name__ == "__main__":
    main()
