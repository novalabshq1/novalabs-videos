#!/usr/bin/env python3
"""Patient Zero — 1 infected green ball among 49 healthy white ones, bouncing in a circle.
Every touch from an infected ball fills a healthy ball one third with green; at 3/3 it is infected
and contagious too. Counter: HEALTHY 49 -> 0.
The last healthy ball gets an orange halo; its capture is shown in slow motion, then a green wave.

Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS down to 1080x1920, 60 fps.
Audio fully synthesized, -1 dBFS.

    python3.13 patient-zero.py --search 64            (seed search)
    python3.13 patient-zero.py --seed N               (simulation summary)
    python3.13 patient-zero.py --frames 0,0.2,0.4,0.6,0.8,0.97 --outdir keys/ --seed N
    python3.13 patient-zero.py --out video.mp4 --seed N
"""
import argparse, math, os, subprocess, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

W, H, FPS, S = 1080, 1920, 60, 2
SR = 44100
SUB = 8
DT = 1.0 / (FPS * SUB)

CX, CY, RA = 540.0, 1110.0, 400.0        # arena
N = 50
BR = 26.0                                 # ball radius (52 px)
V_H, V_I = 150.0, 50.0                    # target speeds: healthy / infected (slow, zombie-like)
INCUB = 0.60                              # a fresh infection becomes contagious after this
HITS = 3                                  # bites needed to turn a healthy ball
TURN = 0.32                               # duration of the green "spread" over a ball
HOLD = 4.2                                # seconds after the last infection
SEED = 6


def speed_boost(t):
    return 1.0 + 0.45 * min(1.0, max(0.0, t - 8.0) / 22.0)


def simulate(seed, tmax=75.0):
    rng = np.random.default_rng(seed)
    pos = []
    while len(pos) < N:
        a, r = rng.random() * 2 * math.pi, math.sqrt(rng.random()) * (RA - BR - 4)
        p = np.array([CX + r * math.cos(a), CY + r * math.sin(a)])
        if all(np.hypot(*(p - q)) > 2 * BR + 6 for q in pos):
            pos.append(p)
    pos = np.array(pos)
    # patient zero: the ball closest to the centre
    p0 = int(np.argmin(np.hypot(pos[:, 0] - CX, pos[:, 1] - CY)))
    dirs = rng.random(N) * 2 * math.pi
    vel = np.stack([np.cos(dirs), np.sin(dirs)], 1) * V_H
    inf_t = np.full(N, np.inf)
    inf_t[p0] = -10.0
    inf_ang = np.zeros(N)
    bites = np.zeros(N, int)
    last_bite = np.full(N, -9.0)
    events = []                    # (t, kind, data)
    frames = []
    t, end_t = 0.0, None
    nsteps = int(tmax / DT)
    iu = np.triu_indices(N, 1)
    for step in range(nsteps):
        t = (step + 1) * DT
        boost = speed_boost(min(t, end_t if end_t else t))
        pos += vel * DT
        # walls
        d = pos - np.array([CX, CY])
        r = np.hypot(d[:, 0], d[:, 1])
        out = r > RA - BR
        if out.any():
            for i in np.nonzero(out)[0]:
                n = d[i] / r[i]
                vn = np.dot(vel[i], n)
                if vn > 0:
                    vel[i] -= 2 * vn * n
                    events.append((t, "wall", (i,)))
                pos[i] = np.array([CX, CY]) + n * (RA - BR - 0.01)
        # ball-ball
        dx = pos[:, None, 0] - pos[None, :, 0]
        dy = pos[:, None, 1] - pos[None, :, 1]
        dd = dx[iu] ** 2 + dy[iu] ** 2
        hit = np.nonzero(dd < (2 * BR) ** 2)[0]
        for h in hit:
            i, j = iu[0][h], iu[1][h]
            dv = pos[i] - pos[j]
            dist = math.hypot(*dv)
            if dist < 1e-6:
                continue
            n = dv / dist
            rel = np.dot(vel[i] - vel[j], n)
            ov = 2 * BR - dist
            pos[i] += n * ov / 2
            pos[j] -= n * ov / 2
            if rel < 0:
                vel[i] -= rel * n
                vel[j] += rel * n
                ci = t - inf_t[i] >= INCUB
                cj = t - inf_t[j] >= INCUB
                victim = j if (ci and inf_t[j] == np.inf) else (i if (cj and inf_t[i] == np.inf) else None)
                if victim is not None and t - last_bite[victim] > 0.25:
                    last_bite[victim] = t
                    bites[victim] += 1
                    other = i if victim == j else j
                    if bites[victim] >= HITS:
                        inf_t[victim] = t
                        events.append((t, "infect", (victim, other)))
                    else:
                        events.append((t, "bite", (victim, other, int(bites[victim]))))
                else:
                    events.append((t, "bump", (i, j)))
        # speed regulation toward the target (keeps the gas lively, infected a bit faster)
        sp = np.hypot(vel[:, 0], vel[:, 1]) + 1e-9
        tgt = np.where(np.isfinite(inf_t), V_I, V_H) * boost
        vel *= (1 + (tgt / sp - 1) * min(1.0, 2.5 * DT))[:, None]
        if (step + 1) % SUB == 0:
            frames.append(pos.copy())
        if end_t is None and np.all(np.isfinite(inf_t)):
            end_t = t
        if end_t is not None and t > end_t + HOLD + 2:
            break
    return dict(frames=frames, events=events, inf_t=inf_t, inf_ang=inf_ang, p0=p0, end_t=end_t,
                last=int(np.argmax(np.where(np.isfinite(inf_t), inf_t, -1))))


def summary(sim):
    it = np.sort(sim["inf_t"][np.isfinite(sim["inf_t"])])
    marks = {}
    marks["first"] = round(float(it[1]), 1) if len(it) > 1 else None
    for q in (10, 25, 50, 75, 90):
        k = int(round(q / 100 * (len(it) - 1)))
        marks[q] = round(float(it[k]), 1)
    marks["n-2"] = round(float(it[-2]), 1)
    return marks


# ---------------------------------------------------------------- helpers
FONT_PATHS = ("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
GREEN = (126, 255, 92)
WHITE = (240, 238, 248)
ORANGE = (255, 150, 46)


def font(px):
    for p in FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, int(px))
    return ImageFont.load_default()


def clamp(x, a=0.0, b=1.0):
    return min(max(x, a), b)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def soft_disc(r, power=2.0):
    n = int(2 * r) + 2
    yy, xx = np.mgrid[0:n, 0:n] - n / 2
    d = np.sqrt(xx ** 2 + yy ** 2) / r
    return np.clip(1 - d, 0, 1) ** power


def ball_arrays(kind, R):
    """Float RGB (n,n,3) + alpha (n,n) of a shaded ball. kind: 'healthy' (pearl) or 'infected' (toxic glow)."""
    n = int(2 * R + 6)
    c = n / 2
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    dx, dy = (xx - c) / R, (yy - c) / R
    d = np.sqrt(dx ** 2 + dy ** 2)
    nz = np.sqrt(np.clip(1 - d ** 2, 0, 1))
    lx, ly, lz = -0.45, -0.6, 0.66
    lam = np.clip(dx * lx + dy * ly + nz * lz, 0, 1)
    spec = np.exp(-(((dx + 0.34) ** 2 + (dy + 0.40) ** 2) / 0.03))
    rim = np.clip((d - 0.72) / 0.28, 0, 1) ** 2
    if kind == "healthy":
        base = np.array([226, 222, 238], np.float32)
        body = base * (0.42 + 0.62 * lam)[:, :, None]
        body += np.array([120, 110, 170], np.float32) * (rim * 0.35)[:, :, None]   # cool violet bounce light
        body += 255 * (spec * 0.85)[:, :, None]
    else:
        base = np.array([110, 245, 80], np.float32)
        core = np.exp(-(d ** 2) / 0.55)                                                # emissive core
        body = base * (0.55 + 0.35 * lam + 0.25 * core)[:, :, None]
        body += np.array([210, 255, 170], np.float32) * (core * 0.25)[:, :, None]
        body += np.array([40, 170, 60], np.float32) * (rim * 0.30)[:, :, None]
        body += 255 * (spec * 0.70)[:, :, None]
    alpha = np.clip((1 - d) * R + 0.5, 0, 1)
    return np.clip(body, 0, 255), alpha


_cache = {}


def sprite(kind, R):
    key = (kind, R)
    if key not in _cache:
        rgb, a = ball_arrays(kind, R)
        _cache[key] = (Image.fromarray(rgb.astype(np.uint8)), Image.fromarray((a * 255).astype(np.uint8)), rgb, a)
    return _cache[key]


def fill_sprite(R, level, phase, glow_k):
    """Healthy ball with green liquid filling it from the bottom (level 0..1); glow_k blends to the
    fully infected look once it turns."""
    _, _, h_rgb, a = sprite("healthy", R)
    _, _, i_rgb, _ = sprite("infected", R)
    n = h_rgb.shape[0]
    c = n / 2
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    ux = (xx - c) / R
    surf = c + R * (1 - 2 * level) + R * 0.07 * np.sin(ux * 3.2 + phase) * (1 - level) * min(1, level * 6)
    m = np.clip((yy - surf) / 1.6 + 0.5, 0, 1)
    liquid = i_rgb * 0.82
    line = np.exp(-((yy - surf) / (0.07 * R)) ** 2) * 0.7 * (level < 0.999)
    rgb = h_rgb * (1 - m[:, :, None]) + liquid * m[:, :, None] + np.array(GREEN, np.float32) * line[:, :, None]
    if glow_k > 0:
        rgb = rgb * (1 - glow_k) + i_rgb * glow_k
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)), Image.fromarray((a * 255).astype(np.uint8))


def text_img(txt, px, fill):
    f = font(px * S)
    bb = f.getbbox(txt)
    w, h = bb[2] - bb[0] + 60, bb[3] - bb[1] + 60
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((30 - bb[0], 30 - bb[1]), txt, font=f, fill=fill)
    return im


def with_shadow(im, blur=12, alpha=0.6, dy=8):
    a = np.asarray(im)[:, :, 3].astype(np.float32) * alpha
    sh = Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", (im.width, im.height + dy), (0, 0, 0, 0))
    blk = Image.new("RGBA", im.size, (0, 0, 0, 255))
    blk.putalpha(sh)
    out.alpha_composite(blk, (0, dy))
    out.alpha_composite(im, (0, 0))
    return out


# ---------------------------------------------------------------- timeline (slow motion around the last infection)
SLOW = 0.28
T_SKIP = 1.5                               # start mid-action: first bites already landed


def build_timeline(sim):
    e = sim["end_t"]
    s0, s1 = e - 0.45, e + 0.12

    def st_of(vt):
        vt += T_SKIP
        if vt <= s0:
            return vt
        v1 = s0 + (s1 - s0) / SLOW
        if vt <= v1:
            return s0 + (vt - s0) * SLOW
        return s1 + (vt - v1)

    def vt_of(st):
        if st <= s0:
            return st - T_SKIP
        if st <= s1:
            return s0 + (st - s0) / SLOW - T_SKIP
        return s0 + (s1 - s0) / SLOW + (st - s1) - T_SKIP

    v_end = vt_of(e)
    total = v_end + HOLD
    return st_of, vt_of, v_end, total


# ---------------------------------------------------------------- static layers
SIM = None
STATIC = {}
BAR_W, BAR_Y = 560, 628


def make_bg():
    Hs, Ws = H * S, W * S
    y = np.linspace(0, 1, Hs, dtype=np.float32)[:, None]
    x = np.linspace(-1, 1, Ws, dtype=np.float32)[None, :]
    top, bot = np.array([20, 13, 32.], np.float32), np.array([7, 5, 12.], np.float32)
    img = top[None, None, :] * (1 - y[:, :, None]) + bot[None, None, :] * y[:, :, None]
    yy = (y * 2 - 1)
    vig = 1 - 0.30 * np.clip(x ** 2 * 0.7 + yy ** 2 * 0.45, 0, 1)
    img = img * vig[:, :, None]
    py = (np.arange(Hs, dtype=np.float32)[:, None] + 0.5) / S
    px = (np.arange(Ws, dtype=np.float32)[None, :] + 0.5) / S
    r = np.sqrt((px - CX) ** 2 + (py - CY) ** 2)
    inside = np.clip((RA - r) * S / 2 + 0.5, 0, 1)
    floor = np.array([22, 16, 38.], np.float32) * (0.72 + 0.28 * np.exp(-(r / RA) ** 2 * 1.3))[:, :, None]
    img = img * (1 - inside[:, :, None]) + floor * inside[:, :, None]
    ring = np.exp(-((r - RA) / 3.0) ** 2)
    halo = np.exp(-((r - RA) / 22) ** 2) * 0.20
    img += np.array([168, 150, 220.], np.float32)[None, None, :] * (ring * 0.85 + halo)[:, :, None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def init_static():
    STATIC["bg"] = make_bg()
    STATIC["q1"] = with_shadow(text_img("Can anyone", 96, (246, 244, 252, 255)))
    STATIC["q2"] = with_shadow(text_img("survive?", 96, (246, 244, 252, 255)))
    wm = text_img("@novalabs.hq", 30, (255, 255, 255, 255))
    a = np.asarray(wm).copy()
    a[:, :, 3] = (a[:, :, 3] * 0.35).astype(np.uint8)
    STATIC["wm"] = Image.fromarray(a)
    STATIC["fnum"] = font(156 * S)
    STATIC["flab"] = font(64 * S)
    STATIC["counters"] = {}
    STATIC["shadow"] = Image.fromarray((soft_disc(BR * S * 1.25, 1.5) * 255 * 0.55).astype(np.uint8))
    STATIC["glowdot"] = soft_disc(BR * 0.25 * 2.6, 1.7)


def counter_img(n, col):
    """'99 HEALTHY' with fixed-width digit cells so the number never jumps."""
    key = (n, col)
    if key in STATIC["counters"]:
        return STATIC["counters"][key]
    fnum, flab = STATIC["fnum"], STATIC["flab"]
    s = str(n)
    dw = max(fnum.getbbox(str(k))[2] - fnum.getbbox(str(k))[0] for k in range(10)) + 6 * S
    b1 = fnum.getbbox("0")
    lab = "HEALTHY"
    lb = flab.getbbox(lab)
    numw = dw * 2
    gap = 26 * S
    w = numw + gap + (lb[2] - lb[0])
    h = b1[3] - b1[1]
    im = Image.new("RGBA", (int(w + 60), int(h + 60)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0 = 30 + numw - dw * len(s)
    for k, ch in enumerate(s):
        gb = fnum.getbbox(ch)
        d.text((x0 + k * dw + (dw - (gb[2] - gb[0])) / 2 - gb[0], 30 - b1[1]), ch, font=fnum, fill=col + (255,))
    d.text((30 + numw + gap - lb[0], 30 + h - lb[3]), lab, font=flab, fill=(196, 188, 220, 255))
    out = with_shadow(im)
    STATIC["counters"][key] = out
    return out


# ---------------------------------------------------------------- per-frame
def positions(sim, st):
    fr = sim["frames"]
    k = st * FPS - 1
    if k < 0:
        return fr[0]
    i0 = max(0, min(len(fr) - 1, int(math.floor(k))))
    i1 = min(len(fr) - 1, i0 + 1)
    f = clamp(k - i0)
    return fr[i0] * (1 - f) + fr[i1] * f


def phys_clock(se, e):
    """After the end the physics slows down smoothly to a still image."""
    if se <= e + 0.6:
        return se
    x = se - (e + 0.6)
    T = 2.2
    if x >= T:
        return e + 0.6 + T / 2
    return e + 0.6 + x - x * x / (2 * T)


def lerp_col(a, b, f):
    return tuple(int(a[k] + (b[k] - a[k]) * f) for k in range(3))


def render_frame(vt):
    sim = SIM
    st_of, vt_of, v_end, total = STATIC["tl"]
    e = sim["end_t"]
    vt = max(vt, 0.0)
    se = st_of(vt)                      # effect clock
    st = phys_clock(se, e)              # physics clock (slows to a stop after the end)
    after = se - e                      # >0 once everyone is infected
    inf_t, inf_ang = sim["inf_t"], sim["inf_ang"]
    pos = positions(sim, st)
    img = STATIC["bg"].copy()
    glow = Image.new("RGB", (W * S // 4, H * S // 4), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    lines = Image.new("RGB", img.size, (0, 0, 0))
    ld = ImageDraw.Draw(lines)
    healthy = int(np.sum(inf_t > se))
    last = sim["last"]
    lx, ly = pos[last]

    # ---- shadows
    sh = STATIC["shadow"]
    blk = Image.new("RGB", sh.size, (0, 0, 0))
    for i in range(N):
        x, y = pos[i]
        img.paste(blk, (int(x * S - sh.width / 2 + 3 * S), int(y * S - sh.height / 2 + 7 * S)), sh)

    # ---- final wave: brightness pulse travelling outward from the last contact
    wave_r = None
    if after > 0:
        wave_r = ease_out(after / 1.5) * 2.1 * RA

    # ---- glow for infected balls (quarter-res, additive)
    g = 0.25
    for i in range(N):
        if inf_t[i] > se:
            continue
        k = clamp((se - inf_t[i]) / TURN)
        x, y = pos[i]
        inten = 0.22 + 0.14 * k
        if i == sim["p0"] and se < 2.0:
            inten += 0.35 * (0.5 + 0.5 * math.sin(se * 9))
        if wave_r is not None:
            dd = math.hypot(x - lx, y - ly)
            inten += 0.9 * math.exp(-((dd - wave_r) / 70) ** 2) + 0.15 * ease_io(after / 1.2)
        col = tuple(int(c * min(inten, 1.3) * 0.55) for c in GREEN)
        rr = BR * S * g * 2.0
        gd.ellipse([x * S * g - rr, y * S * g - rr, x * S * g + rr, y * S * g + rr], fill=col)

    # ---- rings: infection ripples, last-survivor halo, final shockwave
    for te, kind, data in sim["events"]:
        if kind not in ("infect", "bite") or te > se or se - te > 0.6:
            continue
        j = data[0]
        k = (se - te) / 0.6
        x, y = pos[j]
        big = kind == "infect"
        rr = BR * (1.12 + (1.5 if big else 0.6) * ease_out(k)) * S
        a = (1 - k) ** 1.5 * (1.0 if big else 0.55)
        if j == last:
            a *= 1.6
        col = tuple(int(c * a * 0.8) for c in GREEN)
        ld.ellipse([x * S - rr, y * S - rr, x * S + rr, y * S + rr], outline=col, width=int(3 * S))
    if healthy == 1:
        t_last1 = sorted(inf_t)[-2]
        k_in = ease_out((se - t_last1) / 0.5)
        pul = 0.75 + 0.25 * math.sin(se * 10)
        rr = BR * (1.55 + 0.12 * math.sin(se * 10)) * S
        col = tuple(int(c * k_in * pul) for c in ORANGE)
        ld.ellipse([lx * S - rr, ly * S - rr, lx * S + rr, ly * S + rr], outline=col, width=int(3.4 * S))
        rg = BR * S * g * 2.3
        gd.ellipse([lx * S * g - rg, ly * S * g - rg, lx * S * g + rg, ly * S * g + rg],
                   fill=tuple(int(c * 0.30 * k_in) for c in ORANGE))
    if wave_r is not None and after < 1.6:
        a = (1 - after / 1.6) ** 1.3
        rr = wave_r * S
        col = tuple(int(c * a) for c in GREEN)
        ld.ellipse([lx * S - rr, ly * S - rr, lx * S + rr, ly * S + rr], outline=col, width=int(5 * S))
    if wave_r is not None and after < 1.6:
        m = Image.new("L", img.size, 0)
        ImageDraw.Draw(m).ellipse([(CX - RA + 2) * S, (CY - RA + 2) * S, (CX + RA - 2) * S, (CY + RA - 2) * S], fill=255)
        lines = Image.composite(lines, Image.new("RGB", img.size, (0, 0, 0)), m)

    glow = glow.filter(ImageFilter.GaussianBlur(9)).resize(img.size, Image.BILINEAR)
    img = ImageChops.add(img, glow)

    # ---- balls
    bites = STATIC["bites"]
    for i in range(N):
        x, y = pos[i]
        R = BR * S
        lv = sum(ease_out((se - tb) / 0.22) for tb in bites[i] if tb <= se) / HITS
        if inf_t[i] <= se:
            k = (se - inf_t[i]) / TURN
            if k < 1 and inf_t[i] > 0:
                rgb, m = fill_sprite(R, min(1.0, lv), se * 7 + i, ease_io(k))
            else:
                rgb, m, _, _ = sprite("infected", R)
        elif lv > 0.002:
            rgb, m = fill_sprite(R, lv, se * 7 + i, 0.0)
        else:
            rgb, m, _, _ = sprite("healthy", R)
        img.paste(rgb, (int(round(x * S - rgb.width / 2)), int(round(y * S - rgb.height / 2))), m)
    img = ImageChops.add(img, lines)

    # ---- final flash
    if after > 0:
        fl = math.exp(-after / 0.22)
        if fl > 0.02:
            img = ImageChops.add(img, Image.new("RGB", img.size, (int(14 * fl), int(46 * fl), int(16 * fl))))

    # ---- text
    for key, yq in (("q1", 150), ("q2", 262)):
        q = STATIC[key]
        img.paste(q, (int(W * S / 2 - q.width / 2), int(yq * S)), q)
    if healthy == 0:
        col = lerp_col(ORANGE, GREEN, ease_io(after / 0.3))
    elif healthy == 1:
        col = ORANGE
    else:
        col = WHITE
    ci = counter_img(healthy, col)
    # pop when the number changes
    past = [te for te, kd, _ in sim["events"] if kd == "infect" and te <= se]
    pop = 0.0
    if past:
        dtc = se - past[-1]
        pop = 0.10 * math.exp(-dtc / 0.09) * (2.2 if healthy == 0 else 1.0)
    if pop > 0.004:
        ci = ci.resize((int(ci.width * (1 + pop)), int(ci.height * (1 + pop))), Image.BICUBIC)
    cy_c = 500 * S
    img.paste(ci, (int(W * S / 2 - ci.width / 2), int(cy_c - ci.height / 2)), ci)
    # progress bar (share infected)
    d = ImageDraw.Draw(img)
    bx0, by = (W - BAR_W) / 2 * S, BAR_Y * S
    bh = 12 * S
    d.rounded_rectangle([bx0, by, bx0 + BAR_W * S, by + bh], radius=bh / 2, fill=(44, 34, 64))
    frac = (N - healthy) / N
    if frac > 0:
        d.rounded_rectangle([bx0, by, bx0 + max(bh, BAR_W * S * frac), by + bh], radius=bh / 2, fill=GREEN)
    wm = STATIC["wm"]
    img.paste(wm, (int(W * S / 2 - wm.width / 2), int(1600 * S)), wm)
    return img.resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- audio
PENTA = [0, 2, 4, 7, 9]


def note_freq(step, base=196.0):
    o, s = divmod(step, 5)
    return base * 2 ** ((12 * o + PENTA[s]) / 12)


def env(n, a, r):
    e = np.exp(-np.arange(n) / (r * SR))
    na = max(1, int(a * SR))
    e[:na] *= np.linspace(0, 1, na)
    return e


def add(buf, t, sig, gain=1.0):
    k = int(round(t * SR))
    if k < 0 or k >= len(buf):
        return
    j = min(len(buf), k + len(sig))
    buf[k:j] += sig[:j - k] * gain


def band(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))


def tone(freq, dur, a=0.004, r=0.3, parts=((1, 1.0), (2, 0.35), (3, 0.12))):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    s = sum(g * np.sin(2 * math.pi * freq * m * tt) * np.exp(-tt * (m - 1) * 3) for m, g in parts)
    return s * env(n, a, r)


def sweep(f0, f1, dur, a=0.002, r=0.05, curve=2.0):
    n = int(dur * SR)
    x = np.linspace(0, 1, n)
    f = f0 + (f1 - f0) * x ** (1 / curve)
    ph = 2 * math.pi * np.cumsum(f) / SR
    return np.sin(ph) * env(n, a, r)


def synth_audio(sim, path):
    st_of, vt_of, v_end, total = build_timeline(sim)
    n = int(total * SR) + SR
    dry = np.zeros(n)
    rng = np.random.default_rng(5)
    e = sim["end_t"]
    last_t = {}
    count = 0
    pend = []                                  # infections grouped by 30 ms windows
    for te, kind, data in sim["events"]:
        if te > e + 0.7:
            break
        vt = vt_of(te)
        if kind == "infect":
            count += 1
            pend.append((vt, count, data[0] == sim["last"]))
        elif kind == "bite":
            if vt - last_t.get("bite", -1) < 0.03:
                continue
            last_t["bite"] = vt
            lvl = data[2]
            f = note_freq(2 + 2 * lvl + int(round(8 * count / (N - 1))))
            add(dry, vt, tone(f, 0.35, a=0.002, r=0.10, parts=((1, 1), (3, 0.2))), 0.11)
            add(dry, vt, sweep(320, 160, 0.06, a=0.002, r=0.02), 0.07)
        elif kind in ("bump", "wall"):
            if vt - last_t.get("tick", -1) < 0.045:
                continue
            last_t["tick"] = vt
            f = 1500 + 500 * rng.random() if kind == "bump" else 900
            add(dry, vt, tone(f, 0.05, a=0.001, r=0.012, parts=((1, 1), (2.4, 0.3))), 0.035)
    groups = []
    for vt, c, is_last in pend:
        if groups and vt - groups[-1][0] < 0.03:
            groups[-1][1] = c
            groups[-1][2] += 1
            groups[-1][3] |= is_last
        else:
            groups.append([vt, c, 1, is_last])
    for vt, c, m, is_last in groups:
        step = int(round(16 * c / (N - 1)))
        f = note_freq(step)
        g = 0.20 * (1 + 0.25 * min(m - 1, 2))
        if is_last:
            continue
        add(dry, vt, tone(f, 0.9, a=0.003, r=0.30, parts=((1, 1), (2, 0.3), (4, 0.10))), g)
        add(dry, vt, sweep(380, 150, 0.09, a=0.002, r=0.03), 0.10)                 # soft "bloop"
    # dark-to-bright pad (C major, low) that thickens with the infection share
    tt = np.arange(n) / SR
    share = np.zeros(n)
    for vt, c, m, _ in groups:
        share[int(max(0, vt) * SR):] = c / (N - 1)
    share = np.convolve(share, np.ones(8820) / 8820, mode="same")
    pad = np.zeros(n)
    for f, gg in ((65.41, 1.0), (98.0, 0.7), (130.81, 0.6), (196.0, 0.35), (261.63, 0.25)):
        pad += gg * (np.sin(2 * math.pi * f * tt) + 0.5 * np.sin(2 * math.pi * f * 1.004 * tt + 1.0))
    pad *= (0.8 + 0.2 * np.sin(2 * math.pi * 0.21 * tt))
    pad = pad / 3.0 * (0.05 + 0.07 * share)
    pad *= np.clip(tt / 0.4, 0, 1)
    # heartbeat while 3 or fewer are left
    it = np.sort(sim["inf_t"])
    t3 = vt_of(it[-3])
    t_h = t3 + 0.2
    while t_h < v_end - 0.2:
        prog = clamp((t_h - t3) / max(1e-3, v_end - t3))
        add(dry, t_h, sweep(95, 48, 0.18, a=0.003, r=0.06), 0.30 + 0.15 * prog)
        add(dry, t_h + 0.16, sweep(85, 45, 0.16, a=0.003, r=0.05), 0.20 + 0.1 * prog)
        t_h += 0.62 - 0.22 * prog
    # riser into the last infection
    rd = min(4.0, v_end - t3 + 0.5)
    r0 = v_end - rd
    rn = int(rd * SR)
    x = np.linspace(0, 1, rn)
    noise = rng.normal(0, 1, rn)
    riser = np.zeros(rn)
    for k in range(8):
        seg = slice(k * rn // 8, (k + 1) * rn // 8)
        lo = 400 + 600 * k
        riser[seg] = band(noise[seg], lo, lo * 3)[: (seg.stop - seg.start)]
    riser = riser * x ** 2.2 * 0.10 + sweep(196, 784, rd, a=1.0, r=99) * x ** 2 * 0.06
    add(dry, r0, riser, 1.0)
    # payoff: deep boom + major chord + bell arpeggio + shimmer
    add(dry, v_end, sweep(90, 36, 1.3, a=0.003, r=0.45), 0.85)
    nzn = int(0.7 * SR)
    add(dry, v_end, band(rng.normal(0, 1, nzn), 60, 1500) * env(nzn, 0.002, 0.16), 0.35)
    chord = sum(tone(f, 4.5, a=0.02, r=1.5, parts=((1, 1), (2, 0.4), (3, 0.15), (4, 0.06)))
                for f in (196.0, 246.94, 293.66, 392.0, 493.88, 587.33))
    add(dry, v_end + 0.02, chord, 0.20)
    for k, f in enumerate((783.99, 987.77, 1174.66, 1567.98, 1174.66, 1567.98, 1975.53)):
        add(dry, v_end + 0.08 + 0.09 * k, tone(f, 1.2, a=0.002, r=0.35, parts=((1, 1), (2.76, 0.25))), 0.10)
    sh = band(rng.normal(0, 1, int(2.5 * SR)), 5000, 14000) * env(int(2.5 * SR), 0.05, 0.6)
    add(dry, v_end + 0.1, sh, 0.05)
    # reverb
    irn = int(1.6 * SR)
    ir = rng.normal(0, 1, irn) * np.exp(-np.arange(irn) / (0.32 * SR))
    ir = band(ir, 200, 9000)
    ir /= np.sqrt(np.sum(ir ** 2))
    L = 1 << int(math.ceil(math.log2(n + irn)))
    wet = np.fft.irfft(np.fft.rfft(dry, L) * np.fft.rfft(ir, L), L)[:n]
    mix = dry + 0.22 * wet + pad
    mix = mix[: int(total * SR)]
    fo = int(0.6 * SR)
    mix[-fo:] *= np.linspace(1, 0.0, fo) ** 1.5
    mix = np.tanh(mix * 1.1) / 1.1
    mix *= 10 ** (-1 / 20) / np.max(np.abs(mix))
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def worker_init(seed):
    global SIM
    SIM = simulate(seed)
    init_static()
    STATIC["tl"] = build_timeline(SIM)
    STATIC["bites"] = [[] for _ in range(N)]
    for te, kind, data in SIM["events"]:
        if kind in ("bite", "infect"):
            STATIC["bites"][data[0]].append(te)


def render_bytes(fi):
    return render_frame(fi / FPS).tobytes()


def _job(sd):
    s = simulate(sd)
    return sd, s["end_t"], summary(s), s["events"][0][0] if s["events"] else None, \
        next((ev[0] for ev in s["events"] if ev[1] == "infect"), None)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--search", type=int, default=0)
    ap.add_argument("--frames", default="")
    ap.add_argument("--outdir", default="keys")
    ap.add_argument("--out", default="")
    ap.add_argument("--audio", default="")
    a = ap.parse_args()
    if a.search:
        with Pool(4) as p:
            for sd, end, marks, _, first in p.imap(_job, range(a.search)):
                print(sd, end and round(end, 1), "first", first and round(first, 2), marks, flush=True)
    elif a.audio:
        synth_audio(simulate(a.seed), a.audio)
    elif a.frames:
        worker_init(a.seed)
        total = STATIC["tl"][3]
        os.makedirs(a.outdir, exist_ok=True)
        for tok in a.frames.split(","):
            v = float(tok)
            vt = v * total if v <= 1 else v
            render_frame(vt).save(os.path.join(a.outdir, f"k_{vt:06.2f}.png"))
            print("frame", round(vt, 2), "/", round(total, 2), flush=True)
    elif a.out:
        worker_init(a.seed)
        total = STATIC["tl"][3]
        nfr = int(round(total * FPS))
        wav = a.out + ".wav"
        synth_audio(SIM, wav)
        proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                 "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                                 "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", a.out],
                                stdin=subprocess.PIPE)
        with Pool(4, initializer=worker_init, initargs=(a.seed,)) as p:
            for k, b in enumerate(p.imap(render_bytes, range(nfr), chunksize=4)):
                proc.stdin.write(b)
                if k % 300 == 0:
                    print("frame", k, "/", nfr, flush=True)
        proc.stdin.close()
        proc.wait()
        os.remove(wav)
    else:
        s = simulate(a.seed)
        tl = build_timeline(s)
        print("end", s["end_t"] and round(s["end_t"], 2), "marks", summary(s), "p0", s["p0"], "last", s["last"],
              "video", round(tl[3], 2), "s")
