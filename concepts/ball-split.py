#!/usr/bin/env python3
"""Ball Split — a ball splits in two on every wall bounce until the circle is full, then BOOM.

Autonomous: numpy + pillow + scipy + ffmpeg. 1080x1920, 60 fps, H.264 + AAC.
Audio: public-domain melody (published before 1929) played note by note on bounces
+ original synthesized effects (pop, riser, impact, whoosh, ding). No third-party sound.

    python3 ball-split.py --seed 7 --melody ode --out out.mp4
"""
import argparse, os, subprocess, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter

W, H, FPS = 1080, 1920, 60
CX, CY, R = 540, 1010, 420          # arena
BR = 15.0                           # ball radius
CAP = 400
SPEED = 720.0
SR = 44100

PALETTE = np.array([(255, 122, 0), (180, 76, 255), (125, 255, 58), (255, 60, 170), (60, 220, 255)], np.float32)

# MIDI notes — Ode to Joy (Beethoven, 1824) and Twinkle Twinkle (trad., 18th c.): public domain
MELODIES = {
    "ode": [64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64, 64, 62, 62,
            64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64, 62, 60, 60,
            62, 62, 64, 60, 62, 64, 65, 64, 60, 62, 64, 65, 64, 62, 60, 62, 55,
            64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64, 62, 60, 60],
    "twinkle": [60, 60, 67, 67, 69, 69, 67, 65, 65, 64, 64, 62, 62, 60,
                67, 67, 65, 65, 64, 64, 62, 67, 67, 65, 65, 64, 64, 62,
                60, 60, 67, 67, 69, 69, 67, 65, 65, 64, 64, 62, 62, 60],
}


def font(size):
    for p in ("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def text_mask(txt, size, stroke=0):
    f = font(size)
    tmp = Image.new("L", (10, 10))
    b = ImageDraw.Draw(tmp).textbbox((0, 0), txt, font=f, stroke_width=stroke)
    im = Image.new("L", (b[2] - b[0] + 8, b[3] - b[1] + 8), 0)
    ImageDraw.Draw(im).text((4 - b[0], 4 - b[1]), txt, font=f, fill=255, stroke_width=stroke)
    return np.asarray(im, np.float32) / 255.0


def blit_text(img, mask, cx, cy, color, gain=1.0):
    h, w = mask.shape
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if xa >= xb or ya >= yb:
        return
    m = mask[ya - y0:yb - y0, xa - x0:xb - x0, None] * gain
    img[ya:yb, xa:xb] = img[ya:yb, xa:xb] * (1 - m) + np.asarray(color, np.float32) * m


def wrap_title(t):
    words = t.split()
    if len(t) <= 22 or len(words) < 3:
        return [t]
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def make_bg(args, rng):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # dark violet gradient + vignette
    g = (yy / H)[..., None]
    bg = np.array([14, 8, 26], np.float32) * (1 - g) + np.array([6, 6, 16], np.float32) * g
    v = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)[..., None]
    bg = bg * np.clip(1.25 - v, 0.25, 1.1)
    # faint dot grid texture + film grain
    dots = ((xx % 54 < 3) & (yy % 54 < 3)).astype(np.float32)[..., None]
    bg = bg + dots * np.array([14, 8, 24], np.float32)
    bg = bg + rng.normal(0, 2.2, (H, W, 1)).astype(np.float32)
    # arena interior
    d = np.sqrt((xx - CX) ** 2 + (yy - CY) ** 2)
    inside = np.clip(R + 1 - d, 0, 1)[..., None]
    bg = bg * (1 - inside) + (bg * 0.5 + np.array([10, 5, 22], np.float32) * (1.2 - d[..., None] / R * 0.7)) * inside
    bg = np.clip(bg, 0, 255)
    # static texts: title (2 lines), watermark
    lines = wrap_title(args.title)
    for i, ln in enumerate(lines):
        size = 74 if len(ln) <= 20 else 62
        blit_text(bg, text_mask(ln, size, 3), W / 2, 250 + i * 96, (255, 255, 255))
    blit_text(bg, text_mask(args.handle, 52, 2), W / 2, 1670, (255, 255, 255), 0.7)
    return bg.astype(np.float32), d


def ring_pixels():
    y0, y1, x0, x1 = CY - R - 30, CY + R + 30, CX - R - 30, CX + R + 30
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.sqrt((xx - CX) ** 2 + (yy - CY) ** 2)
    a = np.clip(6.5 - np.abs(d - (R + 7)), 0, 1)
    m = a > 0
    ys, xs, al = yy[m], xx[m], a[m].astype(np.float32)
    sector = (((np.arctan2(ys - CY, xs - CX) + np.pi) / (2 * np.pi)) * 16).astype(int) % 16
    # low-res blurred glow of the ring
    low = np.zeros((H // 4, W // 4), np.float32)
    np.add.at(low, (ys // 4, xs // 4), al)
    low = gaussian_filter(low, 5) * 0.9
    return ys, xs, al, sector, low


def simulate_and_render(args, bg, dist, tmp_video):
    rng = np.random.default_rng(args.seed)
    ys, xs, ral, rsec, rglow = ring_pixels()
    sec_ang = (np.arange(16) + 0.5) / 16 * 2 * np.pi - np.pi
    sec_dir = np.stack([np.cos(sec_ang), np.sin(sec_ang)], 1)

    pos = np.zeros((CAP, 2), np.float32)
    vel = np.zeros((CAP, 2), np.float32)
    last = np.full(CAP, -9.0, np.float32)
    born = np.zeros(CAP, np.float32)
    col = np.zeros(CAP, int)
    n = 1
    pos[0] = (CX, CY - 150)
    a0 = rng.uniform(0, 2 * np.pi)
    vel[0] = SPEED * np.array([np.cos(a0), np.sin(a0)])
    col[0] = 0
    events = []                       # (t, kind, x)
    hits = 0
    T = None
    pulse = 0.0
    num_cache, ex_cache = {}, {}
    lab = text_mask("BALLS", 56, 2)

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
         "-pix_fmt", "yuv420p", "-an", tmp_video], stdin=subprocess.PIPE)

    dt = 1.0 / FPS
    frame = 0
    end_after = 3.4
    while True:
        t = frame * dt
        tt = None if T is None else t - T
        if tt is not None and tt > end_after:
            break

        # ---- physics ----
        if T is None:
            pos[:n] += vel[:n] * dt
            rel = pos[:n] - (CX, CY)
            d = np.sqrt((rel ** 2).sum(1))
            hit = np.nonzero(d > R - BR)[0]
            for i in hit:
                nrm = rel[i] / max(d[i], 1e-6)
                vel[i] -= 2 * np.dot(vel[i], nrm) * nrm
                pos[i] = (CX, CY) + nrm * (R - BR)
                hits += 1
                pulse = 1.0
                events.append((t, "hit", float(pos[i][0])))
                if n < CAP and t - last[i] > 0.22 and (hits <= 5 or rng.random() < args.p):
                    ang = rng.uniform(0.35, 0.9) * rng.choice([-1, 1])
                    c, s = np.cos(ang), np.sin(ang)
                    v = vel[i].copy()
                    vel[n] = (c * v[0] - s * v[1], s * v[0] + c * v[1])
                    vel[i] = (c * v[0] + s * v[1], -s * v[0] + c * v[1])
                    pos[n] = pos[i]
                    last[n] = last[i] = t
                    born[n] = t
                    col[n] = (col[i] + rng.integers(1, 3)) % len(PALETTE)
                    n += 1
                    events.append((t, "split", float(pos[i][0])))
            if n >= CAP:
                T = t
                events.append((t, "boom", 0.0))
                rel = pos[:n] - (CX, CY)
                dd = np.maximum(np.sqrt((rel ** 2).sum(1)), 1e-6)[:, None]
                vel[:n] = rel / dd * rng.uniform(500, 1300, (n, 1)) + rng.normal(0, 60, (n, 2))
        else:
            pos[:n] += vel[:n] * dt
        pulse *= 0.9

        # ---- render ----
        img = bg.copy()
        frac = n / CAP
        low = np.zeros((H // 4, W // 4, 3), np.float32)
        ring_fade = 1.0 if tt is None else max(0.0, 1 - tt * 2.2)
        ring_col = (np.array([150, 70, 255], np.float32) * (1 - frac ** 2) +
                    np.array([255, 60, 40], np.float32) * frac ** 2) * (0.6 + 0.4 * pulse)
        ring_col = ring_col + 90 * pulse
        if tt is None:
            img[ys, xs] += ring_col * ral[:, None]
        elif ring_fade > 0:
            dist_off = (0.5 * 1900 * tt ** 1.3)
            ox = np.rint(sec_dir[rsec, 0] * dist_off).astype(int)
            oy = np.rint(sec_dir[rsec, 1] * dist_off).astype(int)
            yy2, xx2 = ys + oy, xs + ox
            ok = (yy2 >= 0) & (yy2 < H) & (xx2 >= 0) & (xx2 < W)
            img[yy2[ok], xx2[ok]] += (ring_col * ral[:, None] * ring_fade)[ok] + 120 * ring_fade * ral[ok, None]
        low += rglow[..., None] * ring_col * (0.5 * ring_fade / 255.0)

        # balls (+ glow splats)
        ball_fade = 1.0 if tt is None else float(np.clip(1 - (tt - 0.5) / 1.3, 0, 1))
        if ball_fade > 0:
            glow_pts = np.zeros((H // 4, W // 4, 3), np.float32)
            for i in range(n):
                x, y = float(pos[i, 0]), float(pos[i, 1])
                age = t - born[i]
                sc = 1.0 + 0.9 * max(0.0, 1 - age / 0.25) if i else 1.0
                rr = BR * sc
                if tt is not None:
                    rr *= 1 + 0.2 * min(tt, 1)
                ix, iy, m = int(x), int(y), int(rr) + 3
                xa, ya, xb, yb = max(ix - m, 0), max(iy - m, 0), min(ix + m + 1, W), min(iy + m + 1, H)
                if xa >= xb or ya >= yb:
                    continue
                gx, gy = np.meshgrid(np.arange(xa, xb), np.arange(ya, yb))
                sd = np.sqrt((gx - x) ** 2 + (gy - y) ** 2)
                a = np.clip(rr + 0.5 - sd, 0, 1)
                core = np.clip((rr * 0.55 - sd) / (rr * 0.4), 0, 1) * 0.55
                c = PALETTE[col[i]] * 0.85
                img[ya:yb, xa:xb] += (a[..., None] * c + (a * core)[..., None] * 255) * ball_fade
                gxl, gyl = min(max(int(x) // 4, 0), W // 4 - 1), min(max(int(y) // 4, 0), H // 4 - 1)
                glow_pts[gyl, gxl] += c * (0.12 * ball_fade * sc)
            low += gaussian_filter(glow_pts, (4, 4, 0)) * 28

        # shockwave + flash
        if tt is not None:
            if tt < 1.0:
                sr_ = tt * 1900
                sw = np.clip(1 - np.abs(dist - sr_) / 26, 0, 1)[..., None] * (1 - tt) ** 1.5
                img += sw * np.array([255, 190, 120], np.float32) * 0.9
            fl = np.exp(-tt * 7.0)
            img += 190 * fl

        glow = Image.fromarray(np.clip(low * 255 / 255.0, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
        img += np.asarray(glow, np.float32) * 0.9

        # counter, bar, texts
        shown = n
        key = shown
        if key not in num_cache:
            num_cache[key] = text_mask(f"{shown}", 190, 4)
        pop = 1.0
        blit_text(img, num_cache[key], W / 2 - 110, 520, (255, 255, 255) if tt is None else (255, 200, 90))
        blit_text(img, lab, W / 2 + 230, 548, PALETTE[1] * 0.4 + 150)
        bx0, bx1, by = 160, 920, 1530
        img[by - 14:by + 14, bx0 - 4:bx1 + 4] = img[by - 14:by + 14, bx0 - 4:bx1 + 4] * 0.4 + 30
        fw = int((bx1 - bx0) * frac)
        barc = np.array([125, 255, 58], np.float32) * (1 - frac) + np.array([255, 60, 40], np.float32) * frac
        if fw > 0:
            img[by - 10:by + 10, bx0:bx0 + fw] = barc * 0.95 + 25
        blit_text(img, text_mask(f"MAX {CAP}", 40, 2), bx1 - 70, by + 52, (255, 255, 255), 0.6)

        if tt is not None:
            if "boom" not in ex_cache:
                ex_cache["boom"] = text_mask("BOOM!", 250, 5)
                ex_cache["end"] = text_mask(f"{CAP} BALLS", 150, 4)
            if tt < 1.6:
                s = min(1, tt * 8) * (1 - max(0, tt - 1.2) / 0.4)
                blit_text(img, ex_cache["boom"], W / 2, CY - 20, (255, 150, 40), s)
            else:
                s = min(1, (tt - 1.6) * 4)
                blit_text(img, ex_cache["end"], W / 2, CY - 20, (255, 255, 255), s)

        out = np.clip(img, 0, 255).astype(np.uint8)
        if tt is not None and tt < 0.7:
            sh = int(22 * np.exp(-tt * 6))
            out = np.roll(out, (sh * (1 if frame % 2 else -1), -sh * (1 if frame % 3 else -1)), (0, 1))
        ff.stdin.write(out.tobytes())
        frame += 1
        if T is None and t > 75:         # safety: never loop forever
            raise SystemExit("simulation too slow to fill; lower --p seed/params")
    ff.stdin.close()
    ff.wait()
    return events, T, frame * dt


# ---------------------------------------------------------------- audio ----
def synth(events, T, total, melody, seed):
    rng = np.random.default_rng(seed + 1)
    N = int((total + 1.0) * SR)
    L = np.zeros(N, np.float32)
    Rr = np.zeros(N, np.float32)

    def add(sig, t0, pan=0.5, gain=1.0):
        i0 = int(t0 * SR)
        if i0 >= N:
            return
        seg = sig[:N - i0]
        L[i0:i0 + len(seg)] += seg * gain * (1 - pan) ** 0.5
        Rr[i0:i0 + len(seg)] += seg * gain * pan ** 0.5

    def tone(f, dur=0.5, decay=6.5):
        t = np.arange(int(dur * SR)) / SR
        env = np.exp(-t * decay) * np.minimum(t / 0.004, 1)
        s = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) * np.exp(-t * 9) +
             0.15 * np.sin(6 * np.pi * f * t) * np.exp(-t * 14))
        return (s * env).astype(np.float32)

    midi = lambda m: 440.0 * 2 ** ((m - 69) / 12)
    mel = MELODIES[melody]
    k, last_note, pops = 0, -1, 0
    for (t, kind, x) in events:
        pan = float(np.clip(x / W, 0.1, 0.9))
        if kind == "hit" and t - last_note >= 0.075:
            last_note = t
            oct_shift = (k // len(mel)) * 2
            add(tone(midi(mel[k % len(mel)] + oct_shift), 0.5), t, pan, 0.33)
            k += 1
        elif kind == "split" and pops < 90:
            pops += 1
            d = int(0.09 * SR)
            tt_ = np.arange(d) / SR
            f = 380 + 900 * tt_ / 0.09
            s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt_ * 38)
            add(s.astype(np.float32), t, pan, 0.16)
    # riser into the boom
    rd = 3.0
    n_r = int(rd * SR)
    tr = np.arange(n_r) / SR
    f = 180 * (2200 / 180) ** (tr / rd)
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = (tr / rd) ** 2
    noise = rng.normal(0, 1, n_r).astype(np.float32)
    riser = (0.5 * np.sin(ph) + 0.25 * np.sign(np.sin(ph * 1.5)) + 0.3 * noise * env) * env
    add(riser.astype(np.float32), max(T - rd, 0), 0.5, 0.35)
    # impact + whoosh + ding
    n_i = int(1.2 * SR)
    ti = np.arange(n_i) / SR
    f = 40 + 150 * np.exp(-ti * 9)
    imp = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-ti * 3.2)
    burst = rng.normal(0, 1, n_i) * np.exp(-ti * 12)
    imp = np.tanh(3.0 * (imp + 0.6 * burst))
    add(imp.astype(np.float32), T, 0.5, 0.75)
    n_w = int(1.4 * SR)
    tw = np.arange(n_w) / SR
    wn = rng.normal(0, 1, n_w)
    for _ in range(14):                       # crude low-pass -> airy whoosh
        wn = (wn + np.roll(wn, 1)) * 0.5
    wh = wn * 9 * np.sin(np.pi * np.clip(tw / 1.4, 0, 1)) ** 1.5
    add(wh.astype(np.float32), T, 0.5, 0.5)
    add(tone(1318.5, 1.4, 2.6), T + 1.55, 0.5, 0.35)
    add(tone(1975.5, 1.4, 3.0), T + 1.65, 0.5, 0.2)

    st = np.stack([L, Rr], 1)
    st = np.tanh(1.3 * st)
    st *= 0.92 / max(np.abs(st).max(), 1e-6)
    return (st * 32767).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--title", default="Every bounce splits the ball. How many before it explodes?")
    ap.add_argument("--handle", default="@novalabs.hq")
    ap.add_argument("--melody", default="ode", choices=list(MELODIES))
    ap.add_argument("--p", type=float, default=0.15, help="split probability per bounce (pacing)")
    ap.add_argument("--out", default="ball-split.mp4")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    bg, dist = make_bg(args, rng)
    with tempfile.TemporaryDirectory() as td:
        vid, wav = os.path.join(td, "v.mp4"), os.path.join(td, "a.wav")
        events, T, total = simulate_and_render(args, bg, dist, vid)
        pcm = synth(events, T, total, args.melody, args.seed)
        with wave.open(wav, "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-i", wav, "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart",
                        args.out], check=True)
    print(f"done: {args.out}  boom at {T:.1f}s, total {total:.1f}s")


if __name__ == "__main__":
    main()
