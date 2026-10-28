#!/usr/bin/env python3
"""Focus Doubling — balls launched from one focus of an ellipse always meet at the other focus.
Every time they meet, their number doubles: 1 -> 2 -> 4 ... -> 128. Will all 128 hit the same point?

Exact ray geometry (no integration drift): a path focus -> wall -> other focus always has length 2a,
so every ball of a trip arrives at the same instant. Positions are computed analytically.

Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS down to 1080x1920, 60 fps.
Audio fully synthesized (pentatonic bells, chords, riser, payoff), -1 dBFS.

    python3 focus-doubling.py --sim                 # timeline check, no render
    python3 focus-doubling.py --frames 0,0.2,0.4,0.6,0.8,0.97 --outdir keys/
    python3 focus-doubling.py --out video.mp4
"""
import argparse, math, os, subprocess, tempfile, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, S = 1080, 1920, 60, 2
SR = 44100
CX, CY = 530.0, 1045.0
A_AX, B_AX = 575.0, 405.0                 # semi-axes (A vertical)
C_F = math.sqrt(A_AX ** 2 - B_AX ** 2)
F1 = np.array([CX, CY + C_F])             # bottom focus (start)
F2 = np.array([CX, CY - C_F])             # top focus
BALL_R = 25.0
DOUBLINGS = 7                             # 1 -> 128
FINAL_N = 2 ** DOUBLINGS
INTRO = 1.3
TRIPS = [3.6, 3.9, 3.8, 3.6, 3.45, 3.35, 3.4, 3.9]   # last trip slower: tension before payoff
PAYOFF_HOLD = 4.6
FIRST_ANGLE = math.radians(-58)           # first ball heads up-right

BG_TOP, BG_BOT = np.array([14, 17, 32.]), np.array([5, 6, 13.])
RIM = np.array([214, 224, 255.])
GOLD = np.array([255, 200, 72.])
GRAD = [np.array(c, float) for c in ((62, 230, 255), (124, 108, 255), (255, 84, 196))]

FONT_PATHS = ("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def font(px):
    for p in FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, int(px))
    return ImageFont.load_default()


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def grad_color(u):
    u = (u % 1.0) * 2.0                    # cyan -> violet -> pink -> violet -> cyan (cyclic)
    u = u if u <= 1 else 2 - u
    if u < 0.5:
        k = u / 0.5
        return GRAD[0] * (1 - k) + GRAD[1] * k
    k = (u - 0.5) / 0.5
    return GRAD[1] * (1 - k) + GRAD[2] * k


# ---------------------------------------------------------------- geometry / timeline
def wall_hit(p, d):
    """First intersection of ray p + t d (t>0) with the ellipse."""
    x0, y0 = p[0] - CX, p[1] - CY
    qa = d[0] ** 2 / B_AX ** 2 + d[1] ** 2 / A_AX ** 2
    qb = 2 * (x0 * d[0] / B_AX ** 2 + y0 * d[1] / A_AX ** 2)
    qc = x0 ** 2 / B_AX ** 2 + y0 ** 2 / A_AX ** 2 - 1
    t = (-qb + math.sqrt(qb * qb - 4 * qa * qc)) / (2 * qa)
    return p + t * d, t


def build_timeline():
    starts, t = [], INTRO
    for T in TRIPS:
        starts.append(t)
        t += T
    end_payoff = t
    total = end_payoff + PAYOFF_HOLD
    trips = []
    for k, T in enumerate(TRIPS):
        src, dst = (F1, F2) if k % 2 == 0 else (F2, F1)
        n = 2 ** min(k, DOUBLINGS)
        # at every meeting the balls burst out again as a perfectly even fan (reflected rays alone
        # would all collapse onto the major axis after a few trips)
        off = FIRST_ANGLE + k * 0.61
        angs = [off + 2 * math.pi * i / n for i in range(n)]
        if min(abs(math.cos(a)) for a in angs) < 0.03:
            angs = [a + math.pi / n / 2 for a in angs]
        segs = []
        for i, ang in enumerate(angs):
            d = np.array([math.cos(ang), math.sin(ang)])
            P, L1 = wall_hit(src, d)
            L2 = float(np.linalg.norm(dst - P))
            assert abs(L1 + L2 - 2 * A_AX) < 1e-6, (L1 + L2)
            segs.append(dict(P=P, L1=L1, d1=d, d2=(dst - P) / L2, hue=(i / n + k * 0.11) % 1.0, born=k,
                             t_wall=starts[k] + T * L1 / (2 * A_AX)))
        trips.append(dict(k=k, t0=starts[k], T=T, src=src, dst=dst, segs=segs, n=n))
    return trips, end_payoff, total


TRIPS_TL, T_PAYOFF, T_TOTAL = build_timeline()


def trip_at(t):
    for tr in TRIPS_TL:
        if tr["t0"] <= t < tr["t0"] + tr["T"]:
            return tr
    return None


def seg_pos(tr, s, t):
    d = (t - tr["t0"]) / tr["T"] * 2 * A_AX
    d = min(max(d, 0.0), 2 * A_AX)
    if d <= s["L1"]:
        return tr["src"] + s["d1"] * d
    return s["P"] + s["d2"] * (d - s["L1"])


def balls_at(t):
    """[(x, y, hue, born, age_in_trip)] at time t."""
    if t < INTRO:
        return [(F1[0], F1[1], 0.0, 0)]
    tr = trip_at(t)
    if tr is None:                         # payoff: everyone sits on the final focus
        tr = TRIPS_TL[-1]
        return [(tr["dst"][0], tr["dst"][1], s["hue"], s["born"]) for s in tr["segs"]]
    return [(*seg_pos(tr, s, t), s["hue"], s["born"]) for s in tr["segs"]]


def count_at(t):
    if t < INTRO:
        return 1
    tr = trip_at(t)
    return FINAL_N if tr is None else tr["n"]


# ---------------------------------------------------------------- static layers
def make_background():
    y = np.linspace(0, 1, H * S)[:, None, None]
    bg = BG_TOP * (1 - y) + BG_BOT * y
    bg = np.broadcast_to(bg, (H * S, W * S, 3)).copy()
    yy, xx = np.mgrid[0:H * S, 0:W * S].astype(np.float32)
    ex = ((xx / S - CX) / B_AX) ** 2 + ((yy / S - CY) / A_AX) ** 2
    inside = np.clip((1.0 - ex) * 6, 0, 1)[..., None]
    bg += inside * np.array([6, 7, 14.]) * (1 - 0.5 * ex[..., None].clip(0, 1))
    return bg.astype(np.float32), ex


def rim_layer(ex, color, width=3.2, glow=14.0):
    """Analytic anti-aliased ellipse stroke + soft glow."""
    g = np.sqrt(ex)                        # ~ normalized radius
    dist = np.abs(g - 1.0) * (A_AX + B_AX) / 2 * S   # approx px distance at 2x
    core = np.clip(width * S / 2 - dist + 1.0, 0, 1)
    halo = np.exp(-(dist / (glow * S)) ** 2) * 0.22
    return (core + halo)[..., None] * color[None, None, :] / 255.0


def make_sprite(color, r, glow=2.1):
    """Shaded sphere (radial gradient, specular, rim darkening) + soft glow. Returns (rgb_add, alpha, rgb)."""
    size = int(r * glow * 2 * S) | 1
    c = size / 2
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) + 0.5
    dx, dy = (xx - c) / (r * S), (yy - c) / (r * S)
    d = np.sqrt(dx ** 2 + dy ** 2)
    alpha = np.clip((1.0 - d) * r * S, 0, 1)
    nz = np.sqrt(np.clip(1 - d ** 2, 0, 1))
    light = np.array([-0.45, -0.55, 0.70]); light /= np.linalg.norm(light)
    lam = np.clip(dx * light[0] + dy * light[1] + nz * light[2], 0, 1)
    base = color[None, None, :] * (0.38 + 0.72 * lam[..., None])
    spec = np.clip((dx + 0.36) ** 2 + (dy + 0.40) ** 2, 0, 1)
    spec = np.exp(-spec / 0.028)[..., None] * 0.85
    rimd = np.clip((d - 0.78) / 0.22, 0, 1)[..., None] * 0.30
    rgb = np.clip(base * (1 - rimd) + 255 * spec, 0, 255)
    glow_a = np.exp(-((d - 0.6).clip(0) / 0.55) ** 2) * (d > 0.9) * 0.20
    glow_rgb = color[None, None, :] * glow_a[..., None]
    return glow_rgb.astype(np.float32), alpha[..., None].astype(np.float32), rgb.astype(np.float32)


SPRITES = {}


def sprite_for(hue_key, color, r):
    key = (hue_key, round(r, 1))
    if key not in SPRITES:
        SPRITES[key] = make_sprite(color, r)
    return SPRITES[key]


def blit(img, spr, x, y, a_mul=1.0):
    glow, alpha, rgb = spr
    h, w = alpha.shape[:2]
    x0, y0 = int(round(x * S - w / 2)), int(round(y * S - h / 2))
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, img.shape[1]), min(y0 + h, img.shape[0])
    if xa >= xb or ya >= yb:
        return
    sl = (slice(ya - y0, yb - y0), slice(xa - x0, xb - x0))
    reg = img[ya:yb, xa:xb]
    reg += glow[sl] * a_mul
    a = alpha[sl] * a_mul
    reg *= (1 - a)
    reg += rgb[sl] * a


def text_img(txt, px, color, shadow=True):
    f = font(px * S)
    tmp = ImageDraw.Draw(Image.new("L", (4, 4)))
    b = tmp.textbbox((0, 0), txt, font=f)
    pad = int(14 * S)
    im = Image.new("L", (b[2] - b[0] + 2 * pad, b[3] - b[1] + 2 * pad), 0)
    ImageDraw.Draw(im).text((pad - b[0], pad - b[1]), txt, font=f, fill=255)
    m = np.asarray(im, np.float32)[..., None] / 255.0
    sh = np.asarray(im.filter(ImageFilter.GaussianBlur(5 * S)), np.float32)[..., None] / 255.0 if shadow else None
    return m, sh, np.asarray(color, np.float32)


def blit_text(img, ti, cx, cy, scale=1.0, alpha=1.0):
    m, sh, col = ti
    if scale != 1.0:
        hh, ww = m.shape[:2]
        nw, nh = max(int(ww * scale), 1), max(int(hh * scale), 1)
        m = np.asarray(Image.fromarray((m[..., 0] * 255).astype(np.uint8)).resize((nw, nh), Image.LANCZOS), np.float32)[..., None] / 255
        if sh is not None:
            sh = np.asarray(Image.fromarray((sh[..., 0] * 255).astype(np.uint8)).resize((nw, nh), Image.LANCZOS), np.float32)[..., None] / 255
    h, w = m.shape[:2]
    x0, y0 = int(cx * S - w / 2), int(cy * S - h / 2)
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, img.shape[1]), min(y0 + h, img.shape[0])
    if xa >= xb or ya >= yb:
        return
    sl = (slice(ya - y0, yb - y0), slice(xa - x0, xb - x0))
    reg = img[ya:yb, xa:xb]
    if sh is not None:
        reg *= (1 - sh[sl] * 0.55 * alpha)
    a = m[sl] * alpha
    reg *= (1 - a)
    reg += col * a


# ---------------------------------------------------------------- trails (string art)
def trail_color(hue, n):
    c = grad_color(hue)                    # more balls -> finer, dimmer strings (keeps the string art clean)
    return tuple(int(v) for v in c * (0.36 / (1 + n / 56)))


def draw_trails(draw, t_from, t_to):
    """Draw every path piece travelled in (t_from, t_to] onto the 2x trail canvas."""
    for tr in TRIPS_TL:
        a, b = max(t_from, tr["t0"]), min(t_to, tr["t0"] + tr["T"])
        if b <= a:
            continue
        for s in tr["segs"]:
            pts = [seg_pos(tr, s, a)]
            if a < s["t_wall"] < b:
                pts.append(s["P"])
            pts.append(seg_pos(tr, s, b))
            draw.line([(float(p[0] * S), float(p[1] * S)) for p in pts], fill=trail_color(s["hue"], tr["n"]),
                      width=int(2 * S), joint="curve")


# ---------------------------------------------------------------- frame renderer
class Renderer:
    def __init__(self):
        self.bg, ex = make_background()
        self.rim_white = rim_layer(ex, RIM)
        self.rim_gold = rim_layer(ex, GOLD, width=4.0, glow=22.0)
        self.ex = ex
        self.trail = Image.new("RGB", (W * S, H * S), (0, 0, 0))
        self.trail_draw = ImageDraw.Draw(self.trail)
        self.trail_t = 0.0
        self.q = text_img(f"Will all {FINAL_N} balls hit the same point?", 50, (236, 240, 255))
        self.num_cache = {}
        self.wm = text_img("@novalabs.hq", 26, (255, 255, 255), shadow=False)
        yy, xx = np.mgrid[0:H * S, 0:W * S].astype(np.float32)
        self.yy, self.xx = yy, xx

    def num_text(self, n, gold):
        key = (n, gold)
        if key not in self.num_cache:
            label = f"{n}/{n}" if gold else (f"{n} ball" if n == 1 else f"{n} balls")
            self.num_cache[key] = text_img(label, 150, GOLD if gold else (255, 255, 255))
        return self.num_cache[key]

    def focus_marker(self, img, f, strength, gold=False):
        col = GOLD if gold else np.array([150, 160, 200.])
        fx, fy = f * S
        x0, x1, y0, y1 = int(fx - 90 * S), int(fx + 90 * S), int(fy - 90 * S), int(fy + 90 * S)
        xx, yy = self.xx[y0:y1, x0:x1], self.yy[y0:y1, x0:x1]
        d = np.sqrt((xx - fx) ** 2 + (yy - fy) ** 2) / S
        ring = np.clip(1.6 - np.abs(d - 34), 0, 1) * (0.35 + 0.65 * strength)
        dot = np.clip(4.5 - d, 0, 1) * (0.5 + 0.5 * strength)
        halo = np.exp(-(d / 40) ** 2) * 0.25 * strength
        img[y0:y1, x0:x1] += (ring + dot + halo)[..., None] * col

    def render(self, t):
        if t < self.trail_t:                       # restart canvas (worker jumped back)
            self.trail = Image.new("RGB", (W * S, H * S), (0, 0, 0))
            self.trail_draw = ImageDraw.Draw(self.trail)
            self.trail_t = 0.0
        if t > self.trail_t:
            draw_trails(self.trail_draw, self.trail_t, t)
            self.trail_t = t
        img = self.bg.copy()
        img += np.asarray(self.trail, np.float32)

        # payoff progress
        pay = (t - T_PAYOFF) if t >= T_PAYOFF else -1.0
        gold_mix = ease_out(pay / 0.6) if pay >= 0 else 0.0
        rim = self.rim_white * (1 - gold_mix * 0.85) + self.rim_gold * gold_mix * (1.0 if pay < 0 else 0.55 + 0.45 * math.exp(-pay * 1.2))
        img += rim * 255.0 * 0.9

        # focus markers: the one about to receive balls brightens
        tr = trip_at(t)
        if tr is not None:
            p = (t - tr["t0"]) / tr["T"]
            recv = tr["dst"]
            send = tr["src"]
            self.focus_marker(img, recv, 0.25 + 0.75 * p ** 2, gold=(tr["k"] == len(TRIPS) - 1))
            self.focus_marker(img, send, 0.15 + 0.85 * (1 - ease_out(p * 4)))
        elif t < INTRO:
            self.focus_marker(img, F1, 0.6)
            self.focus_marker(img, F2, 0.3)
        else:
            self.focus_marker(img, TRIPS_TL[-1]["dst"], 1.0, gold=True)
            self.focus_marker(img, TRIPS_TL[-1]["src"], 0.15)

        # arrival flash / shockwave at each convergence
        for tr2 in TRIPS_TL:
            ta = tr2["t0"] + tr2["T"]
            dt = t - ta
            final = tr2 is TRIPS_TL[-1]
            if 0 <= dt < (2.2 if final else 0.7):
                f = tr2["dst"]
                fx, fy = f * S
                rad = (60 + 520 * ease_out(dt / 1.6)) if final else (30 + 130 * ease_out(dt / 0.7))
                fade = (1 - dt / (2.2 if final else 0.7)) ** 2
                col = GOLD if final else np.array([255, 255, 255.])
                R = int((rad + 40) * S)
                x0, x1 = max(int(fx - R), 0), min(int(fx + R), W * S)
                y0, y1 = max(int(fy - R), 0), min(int(fy + R), H * S)
                xx, yy = self.xx[y0:y1, x0:x1], self.yy[y0:y1, x0:x1]
                d = np.sqrt((xx - fx) ** 2 + (yy - fy) ** 2) / S
                inside = (self.ex[y0:y1, x0:x1] < 1.0)
                ring = np.exp(-((d - rad) / (10 if final else 6)) ** 2) * fade * (0.9 if final else 0.55) * inside
                core = np.exp(-(d / (70 if final else 40)) ** 2) * fade * (1.0 if final else 0.6)
                img[y0:y1, x0:x1] += (ring + core)[..., None] * col

        # balls (motion blur: 3 sub-samples over 1/2 frame shutter)
        if pay < 0:
            subs = [t - k * (0.5 / FPS) / 2 for k in (2, 1, 0)]
            weights = [0.22, 0.33, 1.0]
            base = balls_at(t)
            intro_scale = 1.0
            for sub, wgt in zip(subs, weights):
                pos = balls_at(max(sub, 0)) if sub >= INTRO or t < INTRO else base
                if len(pos) != len(base):
                    continue
                for (x, y, hue, born) in pos:
                    col = grad_color(hue)
                    spr = sprite_for(round(hue, 4), col, BALL_R * intro_scale)
                    blit(img, spr, x, y, wgt if wgt < 1 else 1.0)
        else:
            # merge into one big golden ball, then settle to normal size (loops back to a single ball)
            f = TRIPS_TL[-1]["dst"]
            m = ease_out(pay / 0.45)
            if pay < 0.45:
                for (x, y, hue, born) in balls_at(t):
                    spr = sprite_for(round(hue, 4), grad_color(hue), BALL_R)
                    blit(img, spr, x, y, 1 - m)
            pulse = 1.0 + 0.9 * math.exp(-pay * 3.0) * math.sin(min(pay * 9, math.pi))
            r = BALL_R * (1.25 + 0.6 * pulse) if pay < 1.4 else BALL_R * (1.25 + 0.6 * pulse) * 1.0
            r = round(r * 4) / 4
            spr = sprite_for("gold", GOLD, r)
            blit(img, spr, f[0], f[1], m)

        # text
        n = count_at(t)
        blit_text(img, self.q, W / 2, 205)
        last_arrival = max([tr2["t0"] + tr2["T"] for tr2 in TRIPS_TL if tr2["t0"] + tr2["T"] <= t] or [-9])
        punch = 1.0 + 0.16 * math.exp(-(t - last_arrival) * 9) if t - last_arrival < 1 else 1.0
        blit_text(img, self.num_text(n, pay >= 0), W / 2, 352, scale=punch)
        blit_text(img, self.wm, W / 2, 1655, alpha=0.35)

        out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        return out.resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- audio
def adsr(n, a=0.004, r=None):
    env = np.ones(n)
    na = max(int(a * SR), 1)
    env[:na] = np.linspace(0, 1, na) ** 2
    return env


def bell(freq, dur, amp, bright=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = adsr(n) * np.exp(-t * (5.0 / dur))
    s = (np.sin(2 * np.pi * freq * t) + 0.35 * bright * np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t * 6)
         + 0.12 * bright * np.sin(2 * np.pi * freq * 3.01 * t) * np.exp(-t * 10))
    fade = np.minimum(1, (n - np.arange(n)) / (0.01 * SR))
    return s * env * amp * fade


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def add(buf, t, snd):
    i = int(round(t * SR))
    j = min(i + len(snd), len(buf))
    if i < len(buf):
        buf[i:j] += snd[:j - i]


def reverb(x, seconds=1.4, mix=0.22, seed=3):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR * (6.9 / seconds))
    ir[:int(0.012 * SR)] = 0
    ir /= np.sqrt(np.sum(ir ** 2))
    nfft = 1 << int(np.ceil(np.log2(len(x) + n)))
    wet = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[:len(x)]
    return x * (1 - mix) + wet * mix * 1.4


PENTA = [0, 2, 4, 7, 9]


def penta(idx, base=72):
    return base + 12 * (idx // 5) + PENTA[idx % 5]


def build_audio(total):
    n = int((total + 0.5) * SR)
    L = np.zeros(n); Rch = np.zeros(n)

    def put(t, snd, pan=0.0):
        add(L, t, snd * math.sqrt(0.5 * (1 - pan)) * 1.41)
        add(Rch, t, snd * math.sqrt(0.5 * (1 + pan)) * 1.41)

    # intro: soft appear tone
    put(0.05, bell(midi(72), 1.2, 0.30), 0)
    put(0.05, bell(midi(79), 1.2, 0.12), 0)
    put(INTRO, bell(midi(67), 0.8, 0.22, 0.8), 0)
    chord_roots = [60, 62, 64, 67, 69, 72, 74, 76]
    for tr in TRIPS_TL:
        k, nb = tr["k"], tr["n"]
        amp = 0.30 / math.sqrt(nb) * (1 + 0.5 * min(nb, 8) / 8)
        for s in tr["segs"]:
            ang = math.atan2(s["P"][1] - CY, s["P"][0] - CX)
            idx = int(((ang + math.pi) / (2 * math.pi)) * 10) % 10
            pan = float(np.clip((s["P"][0] - CX) / B_AX, -1, 1)) * 0.6
            put(s["t_wall"], bell(midi(penta(idx, 72 + (2 if k % 2 else 0))), 0.55, amp, 0.8), pan)
        ta = tr["t0"] + tr["T"]
        final = tr is TRIPS_TL[-1]
        if not final:
            r = chord_roots[k]
            for iv, a in ((0, 0.24), (4, 0.17), (7, 0.17), (12, 0.12)):
                put(ta, bell(midi(r + iv), 1.6, a, 1.2), 0)
            # low soft thump
            m = int(0.25 * SR); tt = np.arange(m) / SR
            put(ta, np.sin(2 * np.pi * (90 * np.exp(-tt * 8) + 45) * tt) * np.exp(-tt * 14) * 0.35, 0)
            # spawn shimmer (tiny upward sweep)
            m = int(0.35 * SR); tt = np.arange(m) / SR
            sw = np.sin(2 * np.pi * np.cumsum(900 + 1800 * tt / 0.35) / SR) * np.exp(-tt * 9) * 0.05
            sw[:200] *= np.linspace(0, 1, 200)
            put(ta + 0.02, sw, 0)
        else:
            # riser across the final trip
            t0, T = tr["t0"], tr["T"]
            m = int(T * SR); tt = np.arange(m) / SR
            freq = 220 * 2 ** (tt / T * 2)
            rng = np.random.default_rng(1)
            noise = np.convolve(rng.standard_normal(m), np.ones(40) / 40, "same")
            riser = (np.sin(2 * np.pi * np.cumsum(freq) / SR) * 0.10 + noise * 0.6) * (tt / T) ** 2.2
            riser[-int(0.02 * SR):] *= np.linspace(1, 0, int(0.02 * SR))
            put(t0, riser, 0)
            # payoff: big C major across octaves + sub boom + sparkle arpeggio
            for iv, a in ((-12, 0.30), (0, 0.30), (4, 0.22), (7, 0.22), (12, 0.18), (16, 0.12), (19, 0.10), (24, 0.08)):
                put(ta, bell(midi(60 + iv), 5.0, a, 1.3), 0)
            m = int(1.2 * SR); tt = np.arange(m) / SR
            boom = np.sin(2 * np.pi * (70 * np.exp(-tt * 5) + 38) * tt) * np.exp(-tt * 3.5) * 0.6
            boom[:100] *= np.linspace(0, 1, 100)
            put(ta, boom, 0)
            for i, iv in enumerate((24, 28, 31, 36, 40, 43)):
                put(ta + 0.12 + i * 0.07, bell(midi(60 + iv), 0.9, 0.06, 0.6), (-0.5 + i * 0.2))
    # soft pad under everything: one chord per trip, slow crossfades, swells toward the payoff
    tt = np.arange(n) / SR
    pad = np.zeros(n)
    edges = [0.0] + [tr["t0"] for tr in TRIPS_TL[1:]] + [T_PAYOFF]
    for k, tr in enumerate(TRIPS_TL):
        a0, a1 = edges[k], edges[k + 1]
        win = np.clip((tt - a0 + 0.4) / 0.8, 0, 1) * np.clip((a1 - tt + 0.4) / 0.8, 0, 1)
        r = chord_roots[k] - 12
        lvl = 0.035 + 0.03 * k / len(TRIPS_TL)
        for iv in (0, 7, 12, 16):
            pad += np.sin(2 * np.pi * midi(r + iv) * tt + iv) * win * lvl / (1 + iv / 12)
    win = np.clip((tt - T_PAYOFF + 0.2) / 0.4, 0, 1) * np.clip((total - tt) / 3.0, 0, 1)
    for iv in (0, 7, 12, 16, 19):
        pad += np.sin(2 * np.pi * midi(48 + iv) * tt + iv) * win * 0.07 / (1 + iv / 12)
    vib = 1 + 0.15 * np.sin(2 * np.pi * 0.25 * tt)
    L += pad * vib; Rch += pad * (2 - vib)
    st = np.stack([reverb(L, seed=3), reverb(Rch, seed=4)], 1)
    st = st[:int(total * SR)]
    fade = int(0.25 * SR)
    st[-fade:] *= np.linspace(1, 0, fade)[:, None]
    st *= 10 ** (-1 / 20) / np.max(np.abs(st))
    return st


def write_wav(path, st):
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767).astype("<i2").tobytes())


# ---------------------------------------------------------------- main
def render_chunk(args):
    i0, i1 = args
    r = Renderer()
    if i0 > 0:
        draw_trails(r.trail_draw, 0.0, i0 / FPS)
        r.trail_t = i0 / FPS
    return [r.render(i / FPS).tobytes() for i in range(i0, i1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--frames", default="")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--out", default="")
    ap.add_argument("--wav", default="")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    a = ap.parse_args()
    nframes = int(T_TOTAL * FPS)
    if a.sim:
        walls = sum(len(tr["segs"]) for tr in TRIPS_TL)
        print(f"duration {T_TOTAL:.2f}s frames {nframes} payoff at {T_PAYOFF:.2f}s wall hits {walls}")
        for tr in TRIPS_TL:
            ts = sorted(s["t_wall"] for s in tr["segs"])
            print(f" trip {tr['k']} n={tr['n']:4d} t0={tr['t0']:.2f} T={tr['T']:.2f} walls {ts[0]:.2f}..{ts[-1]:.2f}")
        return
    if a.wav:
        write_wav(a.wav, build_audio(nframes / FPS))
        return
    if a.frames:
        os.makedirs(a.outdir, exist_ok=True)
        r = Renderer()
        for fr in a.frames.split(","):
            t = float(fr) * T_TOTAL if float(fr) <= 1 else float(fr)
            r.render(t).save(os.path.join(a.outdir, f"key_{t:06.2f}.png"))
        return
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        write_wav(wav, build_audio(nframes / FPS))
        ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                               "-s", f"{W}x{H}", "-framerate", str(FPS), "-i", "-", "-i", wav,
                               "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", a.out],
                              stdin=subprocess.PIPE)
        step = 24
        bounds = [(i, min(i + step, nframes)) for i in range(0, nframes, step)]
        with Pool(a.jobs) as p:
            for frames in p.imap(render_chunk, bounds):
                for fr in frames:
                    ff.stdin.write(fr)
        ff.stdin.close()
        assert ff.wait() == 0

if __name__ == "__main__":
    main()
