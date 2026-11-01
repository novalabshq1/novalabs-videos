#!/usr/bin/env python3
"""Pendulum Wave — 15 pendulums of slightly different lengths, released together.
Pendulum i makes exactly 18+i swings in 30 s, so the row breaks into waves, snakes, 2-3-4 rows,
apparent chaos... and lines up again perfectly every 30 s. The video IS one full cycle:
the last frame flows into the first (seamless loop).

Lengths are real: L = g / (2 pi f)^2, f_i = (18+i)/30 Hz  ->  69.0 cm ... 21.8 cm.
Sound: one glass / wood / crystal tick each time a bob reaches its right turning point,
pitch from its length (long = low), pan from its position in the row. No melody:
the order of the ticks is pure physics (glissandi before the alignment, chords at 15 s and 30 s).

numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS to 1080x1920, 60 fps.

    python3.13 pendulum-wave.py --frames 0,0.25,0.5,0.75,0.95 --outdir keys/
    python3.13 pendulum-wave.py --out video.mp4
"""
import argparse, math, os, subprocess, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

W, H, FPS, S = 1080, 1920, 60, 2
SR = 44100
G = 9.81

N, K, T = 15, 18, 30.0                       # pendulum i: K+i swings per T seconds
FREQ = np.array([(K + i) / T for i in range(N)])
LEN = G / (2 * math.pi * FREQ) ** 2          # metres
S0 = 1.6                                     # video starts 1.6 s into the cycle (already a wave)
TOTAL = T                                    # one full cycle -> perfect loop
V_ALIGN = T - S0                             # video time of the alignment
DZ = 0.062                                   # spacing along the beam (m)
BOB = 0.029                                  # bob radius (m)
AMP = 0.13 + 0.12 * (LEN - LEN.min()) / (LEN.max() - LEN.min())   # horizontal swing (m)
THETA = np.arcsin(AMP / LEN)

FONT_PATHS = ("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
WHITE = (242, 240, 250)
GOLD = (255, 204, 92)
# palette along the row: cyan -> violet -> pink
PAL = [(70, 225, 255), (122, 132, 255), (190, 96, 255), (255, 92, 190)]


def row_col(i):
    x = i / (N - 1) * (len(PAL) - 1)
    k = min(int(x), len(PAL) - 2)
    f = x - k
    return tuple(int(PAL[k][c] * (1 - f) + PAL[k + 1][c] * f) for c in range(3))


COLS = [row_col(i) for i in range(N)]


def font(px):
    for p in FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, int(px))
    return ImageFont.load_default()


def clamp(x, a=0.0, b=1.0):
    return min(max(x, a), b)


# ---------------------------------------------------------------- camera
EYE = np.array([float(v) for v in os.environ.get("PW_EYE", "-0.9,0.5,-0.9").split(",")])
TGT = np.array([0.0, -0.40, 7 * DZ])
BOX = (90, 660, 930, 1430)                   # where the pendulums live on screen (1080x1920 px)
FOCAL = 1000.0 * S
SCX, SCY = 0.0, 0.0


def _basis():
    f = TGT - EYE
    f /= np.linalg.norm(f)
    r = np.cross(np.array([0.0, 1.0, 0.0]), f)
    r /= np.linalg.norm(r)
    u = np.cross(f, r)
    return r, u, f


CR, CU, CF = _basis()


def _fit():
    """choose focal + centre so every reachable position fits BOX."""
    global FOCAL, SCX, SCY
    pts = np.concatenate([bob_pos(ct) for ct in np.linspace(0, T, 900)] +
                         [np.array([[0.0, 0.0, zpos(i)] for i in range(N)])])
    d = pts - EYE
    u, v = (d @ CR) / (d @ CF), -(d @ CU) / (d @ CF)
    k = min((BOX[2] - BOX[0]) / (u.max() - u.min()), (BOX[3] - BOX[1]) / (v.max() - v.min()))
    FOCAL = k * S
    SCX = ((BOX[0] + BOX[2]) / 2 - k * (u.max() + u.min()) / 2) * S
    SCY = ((BOX[1] + BOX[3]) / 2 - k * (v.max() + v.min()) / 2) * S


def proj(p):
    """p (...,3) world -> (...,2) screen px at S res, and depth."""
    d = p - EYE
    x, y, z = d @ CR, d @ CU, d @ CF
    return np.stack([SCX + FOCAL * x / z, SCY - FOCAL * y / z], -1), z


def zpos(i):
    return i * DZ


def bob_pos(ct):
    """world positions (N,3) at cycle time ct. x = A cos(2 pi f t): all start at the right."""
    th = THETA * np.cos(2 * math.pi * FREQ * ct)
    x = LEN * np.sin(th)
    y = -LEN * np.cos(th)
    z = np.array([zpos(i) for i in range(N)])
    return np.stack([x, y, z], 1)


def phase_spread(ct):
    """0 when perfectly aligned."""
    ph = (FREQ * ct) % 1.0
    ph = np.minimum(ph, 1 - ph)
    return float(np.max(ph))


# ---------------------------------------------------------------- sprites
_cache = {}


def ball_sprite(i, R, glow):
    """shaded glossy bob, R in px (S res). glow 0..1 brightens towards white-gold."""
    R = max(4, int(round(R)))
    g = round(glow, 2)
    key = (i, R, g)
    if key in _cache:
        return _cache[key]
    n = int(2 * R + 6)
    c = n / 2
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    dx, dy = (xx - c) / R, (yy - c) / R
    d = np.sqrt(dx ** 2 + dy ** 2)
    nz = np.sqrt(np.clip(1 - d ** 2, 0, 1))
    lam = np.clip(dx * -0.45 + dy * -0.62 + nz * 0.64, 0, 1)
    spec = np.exp(-(((dx + 0.33) ** 2 + (dy + 0.40) ** 2) / 0.025))
    rim = np.clip((d - 0.70) / 0.30, 0, 1) ** 2
    base = np.array(COLS[i], np.float32)
    base = base * (1 - 0.55 * g) + np.array([255, 236, 190], np.float32) * 0.55 * g
    body = base * (0.30 + 0.78 * lam)[:, :, None]
    body += base * (rim * 0.45)[:, :, None]
    body += 255 * (spec * 0.9)[:, :, None]
    a = np.clip((1 - d) * R + 0.5, 0, 1)
    rgb = Image.fromarray(np.clip(body, 0, 255).astype(np.uint8))
    al = Image.fromarray((a * 255).astype(np.uint8))
    if len(_cache) > 4000:
        _cache.clear()
    _cache[key] = (rgb, al, n)
    return _cache[key]


def text_img(txt, px, fill, tracking=0):
    f = font(px * S)
    bb = f.getbbox(txt)
    w, h = bb[2] - bb[0] + 60 + tracking * len(txt), bb[3] - bb[1] + 60
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((30 - bb[0], 30 - bb[1]), txt, font=f, fill=fill)
    return im


def with_shadow(im, blur=14, alpha=0.7, dy=8):
    a = np.asarray(im)[:, :, 3].astype(np.float32) * alpha
    sh = Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", (im.width, im.height + dy), (0, 0, 0, 0))
    blk = Image.new("RGBA", im.size, (0, 0, 0, 255))
    blk.putalpha(sh)
    out.alpha_composite(blk, (0, dy))
    out.alpha_composite(im, (0, 0))
    return out


STATIC = {}


def make_bg():
    w, h = W * S, H * S
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    v = yy / h
    top = np.array([6, 8, 18], np.float32)
    bot = np.array([12, 10, 30], np.float32)
    bg = top * (1 - v[:, :, None]) + bot * v[:, :, None]
    # soft spotlight behind the pendulums
    cx, cy = SCX, SCY - 60 * S
    r = np.sqrt(((xx - cx) / (620 * S)) ** 2 + ((yy - cy) / (760 * S)) ** 2)
    spot = np.exp(-r ** 2 * 1.6)
    bg += np.array([20, 22, 52], np.float32) * spot[:, :, None]
    # vignette
    rv = np.sqrt(((xx - w / 2) / (w * 0.75)) ** 2 + ((yy - h / 2) / (h * 0.70)) ** 2)
    bg *= np.clip(1.15 - 0.55 * rv ** 2, 0.35, 1)[:, :, None]
    return Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))


def init_static():
    _fit()
    STATIC["bg"] = make_bg()
    t1 = with_shadow(text_img("Will they ever", 92, WHITE))
    t2 = with_shadow(text_img("line up again?", 92, WHITE))
    STATIC["title"] = (t1, t2)
    # digit cells for the countdown
    f = font(150 * S)
    STATIC["cell_w"] = max(f.getbbox(d)[2] - f.getbbox(d)[0] for d in "0123456789") + 6 * S
    STATIC["beam"] = None
    # pivot points
    piv = np.array([[0.0, 0.0, zpos(i)] for i in range(N)])
    STATIC["piv"], _ = proj(piv)
    # floor light pools: plane y = -0.80
    STATIC["ticks"] = tick_times()


def tick_times():
    """all right-turning-point times inside one cycle [S0, S0+T), as video times, per pendulum."""
    out = []
    for i in range(N):
        per = 1 / FREQ[i]
        k0 = math.ceil(S0 / per - 1e-9)
        k = k0
        while k * per < S0 + T - 1e-9:
            out.append(((k * per - S0), i, k))
            k += 1
    out.sort()
    return out


def last_tick(i, ct):
    """time since bob i last touched its right turning point."""
    per = 1 / FREQ[i]
    return ct - math.floor(ct / per + 1e-9) * per


def counter_img(vt):
    rem = V_ALIGN - vt
    if rem > 0:
        s = f"{rem:4.1f}".strip()
        warm = clamp(1 - rem / 6.0)
        col = tuple(int(WHITE[c] * (1 - warm) + GOLD[c] * warm) for c in range(3))
        f = font(150 * S)
        cw = STATIC["cell_w"]
        dot_w = int(cw * 0.45)
        suffix = "s"
        fs = font(96 * S)
        widths = [dot_w if ch == "." else cw for ch in s]
        sw = fs.getbbox(suffix)[2] + 10 * S
        tw = sum(widths) + sw
        im = Image.new("RGBA", (tw + 60, 230 * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        x = 30
        base_y = 30 + f.getbbox("0")[3]
        for ch, cwid in zip(s, widths):
            bb = f.getbbox(ch)
            d.text((x + (cwid - (bb[2] - bb[0])) / 2 - bb[0], 30), ch, font=f, fill=col)
            x += cwid
        bbs = fs.getbbox(suffix)
        d.text((x + 8 * S, base_y - bbs[3]), suffix, font=fs, fill=col)
        im = im.crop(im.getbbox())
        pad = Image.new("RGBA", (im.width + 60, im.height + 60), (0, 0, 0, 0))
        pad.alpha_composite(im, (30, 30))
        # pulse each whole second in the last 5 s
        pulse = 0.0
        if rem < 5.0:
            fr = rem - math.floor(rem)
            pulse = math.exp(-((1 - fr) / 0.10)) * 0.10 * (1 - rem / 5.0 + 0.3)
        return with_shadow(pad), 1.0 + pulse, col
    a = vt - V_ALIGN
    im = text_img("ALIGNED", 138, GOLD, 0)
    pop = 1.0 + 0.22 * math.exp(-a / 0.12) * (a < 0.6)
    return with_shadow(im), pop, GOLD


def catmull(pts, n=14):
    out = []
    P = [pts[0]] + list(pts) + [pts[-1]]
    for k in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[k - 1], P[k], P[k + 1], P[k + 2]
        for s in range(n):
            t = s / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2])
    return np.array(out)


def align_k(ct):
    """flash envelope of the alignment at ct = T: rises with the line, decays after."""
    d = ct - T
    if d < 0:
        return math.exp(-(d / 0.22) ** 2)
    return math.exp(-d / 0.38)


def render_frame(vt):
    ct = vt + S0
    img = STATIC["bg"].copy()
    w, h = W * S, H * S
    add = Image.new("RGB", (w, h), (0, 0, 0))       # additive neon layer
    da = ImageDraw.Draw(add)
    glow = Image.new("RGB", (W // 4, H // 4), (0, 0, 0))
    dg = ImageDraw.Draw(glow)
    q = 4 * S
    d = ImageDraw.Draw(img, "RGBA")

    spread = phase_spread(ct)
    line_k = clamp(1 - spread / 0.06) ** 2          # how straight the row is (0..1)
    ak = align_k(ct)

    pos = bob_pos(ct)
    scr, depth = proj(pos)
    piv = STATIC["piv"]

    # ---- beam (metal bar along the pivots)
    p_near = proj(np.array([0.0, 0.012, -0.05]))[0]
    p_far = proj(np.array([0.0, 0.012, zpos(N - 1) + 0.05]))[0]
    bw0, bw1 = 0.022 * FOCAL / depth[0] * 0.9, 0.022 * FOCAL / depth[-1] * 0.9
    poly = [(p_near[0] - bw0, p_near[1]), (p_far[0] - bw1, p_far[1]), (p_far[0] + bw1, p_far[1]),
            (p_near[0] + bw0, p_near[1])]
    d.polygon(poly, fill=(52, 56, 84, 255))
    d.line([(p_near[0], p_near[1] - 2 * S), (p_far[0], p_far[1] - 1 * S)], fill=(150, 156, 196, 255), width=2 * S)

    # ---- strings
    for i in range(N - 1, -1, -1):
        d.line([tuple(piv[i]), tuple(scr[i])], fill=(210, 214, 240, 120), width=max(2, int(1.6 * S)))
        r = 0.006 * FOCAL / depth[i]
        d.ellipse([piv[i][0] - r, piv[i][1] - r, piv[i][0] + r, piv[i][1] + r], fill=(170, 176, 210, 255))

    # ---- motion trails (additive), last 0.16 s
    for i in range(N):
        ts = np.linspace(ct - 0.16, ct, 12)
        tp = np.array([bob_pos(t)[i] for t in ts])
        ps, _ = proj(tp)
        for k in range(len(ps) - 1):
            a = (k + 1) / len(ps)
            col = tuple(int(c * 0.28 * a) for c in COLS[i])
            da.line([tuple(ps[k]), tuple(ps[k + 1])], fill=col, width=int(0.030 * FOCAL / depth[i] * a) + 1)

    # ---- the snake: a neon curve through the bobs
    curve = catmull(scr)
    nseg = len(curve) - 1
    for k in range(nseg):
        f = k / nseg
        ci = f * (N - 1)
        c0 = COLS[min(int(ci), N - 1)]
        c1 = COLS[min(int(ci) + 1, N - 1)]
        fr = ci - int(ci)
        col = [c0[c] * (1 - fr) + c1[c] * fr for c in range(3)]
        gk = max(line_k * 0.6, ak)
        col = [col[c] * (1 - gk) + GOLD[c] * gk for c in range(3)]
        bright = 0.55 + 0.35 * line_k + 0.25 * ak
        cc = tuple(int(min(255, x * bright)) for x in col)
        da.line([tuple(curve[k]), tuple(curve[k + 1])], fill=cc, width=int(3 * S + 2 * S * ak))
        gc = tuple(int(min(255, x * (0.30 + 0.25 * ak))) for x in col)
        dg.line([tuple(curve[k] / q), tuple(curve[k + 1] / q)], fill=gc, width=3)

    # ---- bobs, far to near
    order = np.argsort(-depth)
    for i in order:
        R = BOB * FOCAL / depth[i]
        lt = last_tick(i, ct)
        ping = math.exp(-lt / 0.16) if lt < 0.8 else 0.0
        gl = clamp(max(ping * 0.45, ak * 0.5))
        rgb, al, n = ball_sprite(int(i), R, gl)
        x0, y0 = int(scr[i][0] - n / 2), int(scr[i][1] - n / 2)
        img.paste(rgb, (x0, y0), al)
        # glow
        cx, cy = scr[i] / q
        rg = R / q * (1.7 + 0.5 * ping + 0.5 * ak)
        gcol = COLS[i] if ak < 0.5 else GOLD
        gi = 0.22 + 0.22 * ping + 0.18 * ak
        dg.ellipse([cx - rg, cy - rg, cx + rg, cy + rg], fill=tuple(int(c * gi) for c in gcol))
        # ping ring
        if lt < 0.45:
            u = lt / 0.45
            rr = R * (1.15 + 1.4 * u)
            a = (1 - u) ** 2
            col = tuple(int(c * 0.65 * a) for c in COLS[i])
            da.ellipse([scr[i][0] - rr, scr[i][1] - rr, scr[i][0] + rr, scr[i][1] + rr], outline=col,
                       width=max(2, int(2 * S * (1 - u) + 1)))

    # ---- alignment shockwave along the straight line
    if 0 <= ct - T < 1.2:
        u = (ct - T) / 1.2
        for i in range(N):
            R = BOB * FOCAL / depth[i]
            rr = R * (1.3 + 5.0 * (1 - (1 - u) ** 3))
            a = (1 - u) ** 2
            col = tuple(int(c * 0.55 * a) for c in GOLD)
            da.ellipse([scr[i][0] - rr, scr[i][1] - rr, scr[i][0] + rr, scr[i][1] + rr], outline=col,
                       width=max(2, int(3 * S * (1 - u)) + 1))

    img = ImageChops.add(img, add)
    img = img.resize((W, H), Image.LANCZOS)

    # glow composite
    gb = glow.filter(ImageFilter.GaussianBlur(9)).resize((W, H), Image.BILINEAR)
    gb2 = glow.filter(ImageFilter.GaussianBlur(3)).resize((W, H), Image.BILINEAR)
    img = ImageChops.add(img, gb)
    img = ImageChops.add(img, gb2)
    if ak > 0.02 and ct >= T - 0.3:
        fl = Image.new("RGB", (W, H), tuple(int(c * 0.05 * ak) for c in GOLD))
        img = ImageChops.add(img, fl)

    # ---- text
    img = img.convert("RGBA")
    t1, t2 = STATIC["title"]
    for k, t in enumerate((t1, t2)):
        tw = t.resize((t.width // S, t.height // S), Image.LANCZOS)
        img.alpha_composite(tw, (int(500 - tw.width / 2), 262 + k * 104))
    cim, sc, col = counter_img(vt)
    cw, ch = int(cim.width / S * sc), int(cim.height / S * sc)
    cim = cim.resize((cw, ch), Image.LANCZOS)
    img.alpha_composite(cim, (int(500 - cw / 2), int(560 - ch / 2)))
    # watermark
    wm = STATIC.get("wm")
    if wm is None:
        wm = text_img("@novalabs.hq", 30, (255, 255, 255, 90))
        wm = wm.resize((wm.width // S, wm.height // S), Image.LANCZOS)
        STATIC["wm"] = wm
    img.alpha_composite(wm, (int(500 - wm.width / 2), 1468))
    return img.convert("RGB")


# ---------------------------------------------------------------- audio (stereo, seamless loop)
PENTA = [0, 2, 4, 7, 9]


def pitch(i):
    o, s = divmod(i, 5)
    return 220.0 * 2 ** ((12 * o + PENTA[s]) / 12)


def env(n, a, r):
    e = np.exp(-np.arange(n) / (r * SR))
    na = max(1, int(a * SR))
    e[:na] *= np.linspace(0, 1, na)
    return e


def band(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))


def partials(freq, dur, parts, a=0.0015):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    s = np.zeros(n)
    for m, g, r in parts:
        s += g * np.sin(2 * math.pi * freq * m * tt) * np.exp(-tt / r)
    na = max(1, int(a * SR))
    s[:na] *= np.linspace(0, 1, na)
    return s


def voice(i, rng):
    """three timbres in rotation along the row: glass tink, wood tok, crystal."""
    f = pitch(i)
    kind = i % 3
    if kind == 0:      # glass
        s = partials(f, 0.6, ((1, 1.0, 0.16), (2.32, 0.35, 0.07), (4.25, 0.16, 0.035)))
    elif kind == 1:    # wood (marimba-like, very short)
        s = partials(f, 0.4, ((1, 1.0, 0.09), (3.93, 0.22, 0.02)))
        nz = int(0.012 * SR)
        click = band(rng.normal(0, 1, 1024), 1500, 6000)[:nz] * np.exp(-np.arange(nz) / (0.003 * SR))
        s[:nz] += click * 0.25
    else:              # crystal
        s = partials(f, 0.7, ((1, 1.0, 0.20), (2.0, 0.25, 0.10), (3.0, 0.10, 0.06), (5.4, 0.05, 0.02)))
    # gentle low-pass for the highest notes (never shrill)
    if f > 900:
        s *= 0.75
    return s


def synth_audio(path):
    rng = np.random.default_rng(7)
    n = int(TOTAL * SR)
    L = np.zeros(n)
    R = np.zeros(n)
    voices = [voice(i, rng) for i in range(N)]

    def add_wrap(buf, t, sig, gain):
        k = int(round(t * SR)) % n
        j = k + len(sig)
        if j <= n:
            buf[k:j] += sig * gain
        else:
            buf[k:] += sig[: n - k] * gain
            buf[: j - n] += sig[n - k:] * gain

    def add_lin(buf, t, sig, gain):
        k = int(round(t * SR))
        j = min(n, k + len(sig))
        if k < n:
            buf[k:j] += sig[: j - k] * gain

    ticks = tick_times()
    for vt, i, k in ticks:
        ct = vt + S0
        # simultaneous hits are a little softer each so the chords stay round
        g = 0.20 * (0.85 + 0.15 * rng.random()) * (1.0 - 0.25 * (pitch(i) > 700))
        pan = -0.55 + 1.1 * i / (N - 1)
        gl, gr = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
        add_wrap(L, vt, voices[i], g * gl * 1.41)
        add_wrap(R, vt, voices[i], g * gr * 1.41)

    # ---- the alignment: deep felt thump + low warm bloom + soft shimmer, with an airy rise before
    va = V_ALIGN
    rd = 3.2
    rn = int(rd * SR)
    x = np.linspace(0, 1, rn)
    air = band(rng.normal(0, 1, rn), 300, 5000) * x ** 2.6 * 0.035
    add_lin(L, va - rd, air, 1.0)
    add_lin(R, va - rd, band(rng.normal(0, 1, rn), 300, 5000) * x ** 2.6 * 0.035, 1.0)
    thn = int(1.2 * SR)
    tt = np.arange(thn) / SR
    fsw = 70 * np.exp(-tt * 3) + 42
    thump = np.sin(2 * math.pi * np.cumsum(fsw) / SR) * np.exp(-tt / 0.32)
    thump[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
    for b in (L, R):
        add_lin(b, va, thump, 0.55)
    bloom = sum(partials(f, 1.4, ((1, 1.0, 0.45), (2, 0.2, 0.2)), a=0.01) for f in (110.0, 164.81, 220.0))
    add_lin(L, va, bloom, 0.10)
    add_lin(R, va, bloom, 0.10)
    shn = int(1.3 * SR)
    sh = band(rng.normal(0, 1, shn), 6000, 13000) * env(shn, 0.01, 0.30)
    add_lin(L, va + 0.02, sh, 0.025)
    add_lin(R, va + 0.03, band(rng.normal(0, 1, shn), 6000, 13000) * env(shn, 0.01, 0.30), 0.025)

    # ---- light room reverb (circular so the loop stays seamless)
    irn = int(1.1 * SR)
    outs = []
    for b, sd in ((L, 1), (R, 2)):
        r2 = np.random.default_rng(sd)
        ir = r2.normal(0, 1, irn) * np.exp(-np.arange(irn) / (0.22 * SR))
        ir = band(ir, 250, 8000)
        ir /= np.sqrt(np.sum(ir ** 2))
        irp = np.zeros(n)
        irp[:irn] = ir
        wet = np.fft.irfft(np.fft.rfft(b) * np.fft.rfft(irp), n)
        outs.append(b + 0.20 * wet)
    st = np.stack(outs, 1)
    st = np.tanh(st * 1.6) / 1.6
    st *= 10 ** (-3 / 20) / np.max(np.abs(st))
    pcm = (st * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    dens = np.histogram([t for t, _, _ in ticks], bins=int(TOTAL), range=(0, TOTAL))[0]
    print("ticks", len(ticks), "per s: mean", round(len(ticks) / TOTAL, 1), "max", dens.max(), flush=True)


def worker_init():
    init_static()


def render_bytes(fi):
    return render_frame(fi / FPS).tobytes()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", default="")
    ap.add_argument("--outdir", default="keys")
    ap.add_argument("--out", default="")
    ap.add_argument("--audio", default="")
    a = ap.parse_args()
    print("lengths cm", np.round(LEN * 100, 1), "theta deg", np.round(np.degrees(THETA), 1))
    if a.audio:
        synth_audio(a.audio)
    elif a.frames:
        init_static()
        os.makedirs(a.outdir, exist_ok=True)
        for tok in a.frames.split(","):
            v = float(tok)
            vt = v * TOTAL if v <= 1 else v
            render_frame(vt).save(os.path.join(a.outdir, f"k_{vt:06.2f}.png"))
            print("frame", round(vt, 2), flush=True)
    elif a.out:
        init_static()
        nfr = int(round(TOTAL * FPS))
        wav = a.out + ".wav"
        synth_audio(wav)
        # loudness: -14 LUFS, true peak <= -1.5 dBTP
        norm = a.out + ".norm.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af",
                        "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR), norm], check=True)
        proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                 "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", norm,
                                 "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", a.out],
                                stdin=subprocess.PIPE)
        with Pool(4, initializer=worker_init) as p:
            for k, b in enumerate(p.imap(render_bytes, range(nfr), chunksize=4)):
                proc.stdin.write(b)
                if k % 300 == 0:
                    print("frame", k, "/", nfr, flush=True)
        proc.stdin.close()
        proc.wait()
        os.remove(wav)
        os.remove(norm)
