#!/usr/bin/env python3
"""String Circle — 3 neon balls in a thin white circle, each tied to the rim by a fan of 120 strings.
Balls bounce off the rim and off each other. A ball passes straight THROUGH the strings of the other
balls and cuts them (never its own). Cut strings split in two halves that snap back to their ends.
A ball with no strings left explodes. Last ball with strings wins.

Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS down to 1080x1920, 60 fps.
Audio fully synthesized (ASMR snips, felt knocks, no music), stereo, loudness-normalized by ffmpeg.

    python3.13 string-circle.py --search 64            (seed search)
    python3.13 string-circle.py --seed N               (simulation summary / logs)
    python3.13 string-circle.py --frames 0,0.25,0.5,0.75,0.97 --outdir keys/ --seed N
    python3.13 string-circle.py --out video.mp4 --seed N
"""
import argparse, math, os, subprocess, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

W, H, FPS, S = 1080, 1920, 60, 2
SR = 48000
SUB = 8
DT = 1.0 / (FPS * SUB)

CX, CY, RA = 540.0, 1100.0, 395.0          # arena (right edge 935 < 940: clear of the app UI band)
NB = 3
BR = 30.0                                   # ball radius
NS = 120                                    # strings per ball
FAN = 2 * math.pi                           # rim arc covered by a ball's anchors
FAN_OFF = 0.0                               # fan centre relative to the spawn angle
SLACK = 60.0                                # rope length = spawn distance + SLACK: taut ropes hold the ball
K_ROPE = 900.0                              # rope stiffness (1/s^2 per taut rope)
CREEP0, CREEP1 = 6.0, 20.0                  # ropes slowly pay out (px/s), faster and faster: the leash loosens
RETRACT = 0.20                              # cut halves snap back in this time
HOLD = 3.6                                  # seconds after the winner is decided
SEED = 16

COLS = [(40, 220, 255), (255, 60, 170), (255, 196, 40)]
NAMES = ["CYAN", "PINK", "GOLD"]
WHITE = (244, 244, 250)


V_MIN, V_MAX = 260.0, 480.0


def target_speed(t, frac):
    """Slow escalation over time."""
    return V_MIN + (V_MAX - V_MIN) * min(1.0, t / 40.0)


def simulate(seed, tmax=80.0):
    rng = np.random.default_rng(seed)
    a0 = rng.random() * 2 * math.pi
    pos = np.zeros((NB, 2))
    anchors = []
    for b in range(NB):
        a = a0 + 2 * math.pi * b / NB
        pos[b] = (CX + 0.42 * RA * math.cos(a), CY + 0.42 * RA * math.sin(a))
    for b in range(NB):
        # sunburst: NS anchors evenly spread over the rim, skipping the directions where the string
        # would already pass through another ball (nothing is cut before the first frame)
        a = a0 + 2 * math.pi * b / NB
        g = a + FAN_OFF + np.linspace(-FAN / 2, FAN / 2, 4000, endpoint=False)
        R = np.stack([CX + RA * np.cos(g), CY + RA * np.sin(g)], 1)
        seg = pos[b] - R
        L2 = np.sum(seg ** 2, 1)
        free = np.ones(len(g), bool)
        for o in range(NB):
            if o != b:
                u = np.clip(np.sum((pos[o] - R) * seg, 1) / L2, 0, 1)
                free &= np.hypot(*(R + seg * u[:, None] - pos[o]).T) > BR + 10
        fg = g[free]
        ang = fg[((np.arange(NS) + 0.5) / NS * len(fg)).astype(int)]
        anchors.append(np.stack([CX + RA * np.cos(ang), CY + RA * np.sin(ang)], 1))
    anchors = np.array(anchors)                                  # (NB, NS, 2)
    rope = np.hypot(*(anchors - pos[:, None, :]).transpose(2, 0, 1)) + SLACK
    dirs = rng.random(NB) * 2 * math.pi
    vel = np.stack([np.cos(dirs), np.sin(dirs)], 1) * V_MIN
    active = np.ones((NB, NS), bool)
    alive = np.ones(NB, bool)
    events = []                                                  # (t, kind, data)
    frames = [pos.copy()]
    dead_t = np.full(NB, np.inf)
    t, end_t, winner = 0.0, None, None
    for step in range(int(tmax / DT)):
        t = (step + 1) * DT
        tc = t if end_t is None else end_t
        rope += (CREEP0 + (CREEP1 - CREEP0) * min(1.0, tc / 40.0)) * DT
        # ropes: a taut rope pulls its ball back (spring), slack ropes do nothing
        for i in range(NB):
            if not alive[i]:
                continue
            dvec = pos[i] - anchors[i]
            dist = np.hypot(dvec[:, 0], dvec[:, 1]) + 1e-9
            ex = (dist - rope[i]) * active[i]
            taut = ex > 0
            if taut.any():
                vel[i] -= K_ROPE * DT * np.sum((ex[taut] / dist[taut])[:, None] * dvec[taut], 0)
        pos += vel * DT
        # rim: elastic bounce
        d = pos - (CX, CY)
        r = np.hypot(d[:, 0], d[:, 1])
        for i in np.nonzero(r > RA - BR)[0]:
            n = d[i] / r[i]
            vn = vel[i] @ n
            if vn > 0:
                vel[i] -= 2 * vn * n
                if alive[i]:
                    events.append((t, "wall", (i, float(abs(vn)))))
            pos[i] = (CX, CY) + n * (RA - BR - 0.01)
        # ball-ball: elastic, equal masses, with separation
        for i in range(NB):
            for j in range(i + 1, NB):
                if not (alive[i] and alive[j]):
                    continue
                dv = pos[i] - pos[j]
                dist = math.hypot(*dv)
                if dist >= 2 * BR or dist < 1e-9:
                    continue
                n = dv / dist
                ov = 2 * BR - dist
                pos[i] += n * ov / 2
                pos[j] -= n * ov / 2
                rel = (vel[i] - vel[j]) @ n
                if rel < 0:
                    vel[i] -= rel * n
                    vel[j] += rel * n
                    events.append((t, "bump", (i, j, float(-rel), tuple((pos[i] + pos[j]) / 2))))
        # strings: ball j cuts every string of ball i whose segment comes within BR of its centre.
        # Per substep a ball (and any point of a string) moves < 1.6 px << BR, so the sampled distance
        # test covers both the ball's swept capsule and the string's own sweep: no tunnelling.
        for i in range(NB):
            if not alive[i]:
                continue
            idx = np.nonzero(active[i])[0]
            if len(idx) == 0:
                continue
            A = anchors[i, idx]
            seg = pos[i] - A
            L2 = np.sum(seg ** 2, 1) + 1e-9
            for j in range(NB):
                if j == i or not alive[j]:
                    continue
                u = np.clip(np.sum((pos[j] - A) * seg, 1) / L2, 0, 1)
                P = A + seg * u[:, None]
                dd = np.hypot(*(P - pos[j]).T)
                hit = np.nonzero(dd < BR)[0]
                if len(hit):
                    for h in hit:
                        k = idx[h]
                        if not active[i, k]:
                            continue
                        active[i, k] = False
                        events.append((t, "cut", (i, int(k), j, tuple(P[h]), float(u[h]))))
        # elimination
        for i in range(NB):
            if alive[i] and not active[i].any():
                alive[i] = False
                dead_t[i] = t
                events.append((t, "boom", (i, tuple(pos[i]))))
                vel[i] = 0
        if end_t is None and alive.sum() <= 1:
            end_t = t
            winner = int(np.argmax(alive)) if alive.any() else None
        # speed regulation (keeps the dance lively and slowly faster); winner glides to a stop at the end
        sp = np.hypot(vel[:, 0], vel[:, 1]) + 1e-9
        if end_t is None:
            tgt = target_speed(tc, active.sum() / (NB * NS))
            vel *= (1 + (tgt / sp - 1) * min(1.0, 2.0 * DT))[:, None]
        elif t > end_t + 0.5:
            vel *= math.exp(-1.6 * DT)
        vel[~alive] = 0
        if (step + 1) % SUB == 0:
            frames.append(pos.copy())
        if end_t is not None and t > end_t + HOLD + 3:
            break
    return dict(frames=np.array(frames), events=events, anchors=anchors, rope=rope, end_t=end_t, winner=winner,
                dead_t=dead_t, active=active)


def summary(sim):
    ev = sim["events"]
    cuts = [e for e in ev if e[1] == "cut"]
    bumps = [e for e in ev if e[1] == "bump"]
    e = sim["end_t"]
    out = {"end": e and round(e, 1), "winner": sim["winner"], "left": int(sim["active"][sim["winner"]].sum())
           if sim["winner"] is not None else None, "bumps": len(bumps), "cuts": len(cuts),
           "deaths": [round(float(x), 1) for x in sorted(sim["dead_t"]) if np.isfinite(x)],
           "first_cut": cuts and round(cuts[0][0], 2)}
    if e:
        tot = NB * NS
        rem = []
        for q in (0.25, 0.5, 0.75):
            rem.append(tot - sum(1 for c in cuts if c[0] <= q * e))
        out["remaining@25/50/75%"] = rem
    return out


# ---------------------------------------------------------------- helpers
FONT_PATHS = ("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


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


def neon_ball(col, R):
    """Glassy neon ball: saturated rim, hot white-ish core, small specular highlight."""
    n = int(2 * R + 6)
    c = n / 2
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    dx, dy = (xx - c) / R, (yy - c) / R
    d = np.sqrt(dx ** 2 + dy ** 2)
    nz = np.sqrt(np.clip(1 - d ** 2, 0, 1))
    lam = np.clip(dx * -0.45 + dy * -0.6 + nz * 0.66, 0, 1)
    col = np.array(col, np.float32)
    core = np.exp(-(d ** 2) / 0.30)
    body = col * (0.50 + 0.45 * lam)[:, :, None] + (255 - col) * (core * 0.55)[:, :, None]
    spec = np.exp(-(((dx + 0.33) ** 2 + (dy + 0.38) ** 2) / 0.025))
    body += 255 * (spec * 0.75)[:, :, None]
    rim = np.clip((d - 0.80) / 0.2, 0, 1)
    body = body * (1 - 0.35 * rim[:, :, None]) + col * (0.35 * rim)[:, :, None]
    alpha = np.clip((1 - d) * R + 0.5, 0, 1)
    rgb = Image.fromarray(np.clip(body, 0, 255).astype(np.uint8))
    return rgb, Image.fromarray((alpha * 255).astype(np.uint8))


def text_img(txt, px, fill, track=0):
    f = font(px * S)
    bb = f.getbbox(txt)
    w, h = bb[2] - bb[0] + 60 + track * len(txt), bb[3] - bb[1] + 60
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((30 - bb[0], 30 - bb[1]), txt, font=f, fill=fill)
    return im


def with_shadow(im, blur=12, alpha=0.7, dy=8):
    a = np.asarray(im)[:, :, 3].astype(np.float32) * alpha
    sh = Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", (im.width, im.height + dy), (0, 0, 0, 0))
    blk = Image.new("RGBA", im.size, (0, 0, 0, 255))
    blk.putalpha(sh)
    out.alpha_composite(blk, (0, dy))
    out.alpha_composite(im, (0, 0))
    return out


def hash01(*k):
    h = 1469598103934665603
    for v in k:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return (h >> 11) / float(1 << 53)


# ---------------------------------------------------------------- timeline (slow motion on the final cut)
SLOW = 0.30


def build_timeline(sim):
    e = sim["end_t"]
    s0, s1 = e - 0.40, e + 0.15

    def st_of(vt):
        if vt <= s0:
            return vt
        v1 = s0 + (s1 - s0) / SLOW
        if vt <= v1:
            return s0 + (vt - s0) * SLOW
        return s1 + (vt - v1)

    def vt_of(st):
        if st <= s0:
            return st
        if st <= s1:
            return s0 + (st - s0) / SLOW
        return s0 + (s1 - s0) / SLOW + (st - s1)

    v_end = vt_of(e)
    return st_of, vt_of, v_end, v_end + HOLD


# ---------------------------------------------------------------- static layers
SIM = None
STATIC = {}


def make_bg():
    Hs, Ws = H * S, W * S
    py = (np.arange(Hs, dtype=np.float32)[:, None] + 0.5) / S
    px = (np.arange(Ws, dtype=np.float32)[None, :] + 0.5) / S
    r = np.sqrt((px - CX) ** 2 + (py - CY) ** 2)
    base = np.array([6, 6, 11.], np.float32)
    img = base * (1.0 + 0.9 * np.exp(-(r / (RA * 1.3)) ** 2))[:, :, None] * np.ones((1, Ws, 1), np.float32)
    ring = np.exp(-((r - RA) / 1.7) ** 2)                # ~3 px thin white ring
    halo = np.exp(-((r - RA) / 14) ** 2) * 0.10
    img += np.array([235, 238, 255.], np.float32)[None, None, :] * (ring * 0.95 + halo)[:, :, None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def init_static():
    STATIC["bg"] = make_bg()
    m = Image.new("L", (W * S, H * S), 0)
    ImageDraw.Draw(m).ellipse([(CX - RA + 2) * S, (CY - RA + 2) * S, (CX + RA - 2) * S, (CY + RA - 2) * S], fill=255)
    STATIC["mask"] = m
    STATIC["hook"] = with_shadow(text_img("WHICH ONE WINS?", 86, (250, 250, 255, 255)))
    wm = text_img("@novalabs.hq", 30, (255, 255, 255, 255))
    a = np.asarray(wm).copy()
    a[:, :, 3] = (a[:, :, 3] * 0.35).astype(np.uint8)
    STATIC["wm"] = Image.fromarray(a)
    STATIC["ball"] = [neon_ball(c, BR * S) for c in COLS]
    STATIC["fnum"] = font(112 * S)
    STATIC["num"] = {}
    STATIC["wins"] = [with_shadow(text_img(f"{NAMES[b]} WINS", 112, COLS[b] + (255,))) for b in range(NB)]
    # per-string colour: slight per-string brightness jitter makes the fan read as threads
    STATIC["scol"] = [[tuple(int(c * (0.50 + 0.14 * hash01(b, k, 7))) for c in COLS[b]) for k in range(NS)]
                      for b in range(NB)]
    cuts = [[] for _ in range(NB)]          # per ball: (t, k, cutter, P, u)
    cut_t = np.full((NB, NS), np.inf)
    for te, kind, d in SIM["events"]:
        if kind == "cut":
            cuts[d[0]].append((te, d[1], d[2], d[3], d[4]))
            cut_t[d[0], d[1]] = te
    STATIC["cuts"] = cuts
    STATIC["cut_t"] = cut_t
    STATIC["cut_times"] = [np.array([c[0] for c in cuts[b]]) for b in range(NB)]


def num_img(n, col):
    key = (n, col)
    if key not in STATIC["num"]:
        f = STATIC["fnum"]
        dw = max(f.getbbox(str(k))[2] - f.getbbox(str(k))[0] for k in range(10)) + 4 * S
        b0 = f.getbbox("0")
        s = str(n)
        im = Image.new("RGBA", (int(dw * 3 + 60), int(b0[3] - b0[1] + 60)), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        x0 = 30 + (3 - len(s)) * dw / 2
        for k, ch in enumerate(s):
            gb = f.getbbox(ch)
            d.text((x0 + k * dw + (dw - (gb[2] - gb[0])) / 2 - gb[0], 30 - b0[1]), ch, font=f, fill=col + (255,))
        STATIC["num"][key] = with_shadow(im)
    return STATIC["num"][key]


def positions(st):
    fr = SIM["frames"]
    k = st * FPS
    i0 = max(0, min(len(fr) - 1, int(math.floor(k))))
    i1 = min(len(fr) - 1, i0 + 1)
    f = clamp(k - i0)
    return fr[i0] * (1 - f) + fr[i1] * f


# ---------------------------------------------------------------- per-frame
def render_frame(vt):
    sim = SIM
    st_of, vt_of, v_end, total = STATIC["tl"]
    e, win = sim["end_t"], sim["winner"]
    st = st_of(max(vt, 0.0))
    after = vt - v_end
    pos = positions(st)
    anchors, cut_t = sim["anchors"], STATIC["cut_t"]
    dead = sim["dead_t"]

    img = STATIC["bg"].copy()
    lines = Image.new("RGB", img.size, (0, 0, 0))
    ld = ImageDraw.Draw(lines)
    glow = Image.new("RGB", (W * S // 4, H * S // 4), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    lw = 3                                      # 1.5 px at output size

    # ---- intact strings
    win_k = ease_io(after / 0.8) if after > 0 else 0.0
    for b in range(NB):
        if dead[b] <= st:
            continue
        x, y = pos[b] * S
        live = np.nonzero(cut_t[b] > st)[0]
        cols = STATIC["scol"][b]
        boost = 1.0 + 0.6 * win_k * (b == win)
        for k in live:
            ax, ay = anchors[b, k] * S
            c = cols[k] if boost == 1.0 else tuple(min(255, int(v * boost)) for v in cols[k])
            ld.line([(ax, ay), (x, y)], fill=c, width=lw)
    # ---- cut strings: two halves snap back to their ends, fading; spark at the cut point
    sparks = []
    for b in range(NB):
        for te, k, cutter, P, u in STATIC["cuts"][b]:
            age = st - te
            if age < 0:
                break
            if age > RETRACT + 0.15:
                continue
            ax, ay = anchors[b, k]
            px_, py_ = P
            if age < RETRACT:
                g = ease_out(age / RETRACT)
                fade = (1 - age / RETRACT) ** 1.2
                c = tuple(int(v * (0.9 * fade + 0.1)) for v in COLS[b])
                c = tuple(int(c[i] * (0.65 + 0.35 * (1 - g))) for i in range(3))
                # anchor half
                ex, ey = px_ + (ax - px_) * g, py_ + (ay - py_) * g
                ld.line([(ax * S, ay * S), (ex * S, ey * S)], fill=c, width=lw)
                # ball half (follows the ball, unless the ball is gone)
                if dead[b] > st:
                    bx, by = pos[b]
                    qx, qy = px_ + (bx - px_) * g, py_ + (by - py_) * g
                    ld.line([(bx * S, by * S), (qx * S, qy * S)], fill=c, width=lw)
            sparks.append((age, px_, py_, b, k))
    for age, px_, py_, b, k in sparks:
        if age < 0.07:
            fl = 1 - age / 0.07
            rr = (5 + 6 * fl) * S
            c = tuple(int(min(255, 140 + v * 0.5) * fl) for v in COLS[b])
            ld.ellipse([px_ * S - rr, py_ * S - rr, px_ * S + rr, py_ * S + rr], fill=c)
        for m in range(4):
            a = 2 * math.pi * hash01(b, k, m)
            sp = 140 + 160 * hash01(b, k, m + 9)
            life = 0.22 + 0.12 * hash01(b, k, m + 3)
            if age > life:
                continue
            d0 = sp * age * (1 - 0.5 * age / life)
            sx, sy = px_ + math.cos(a) * d0, py_ + math.sin(a) * d0
            f = (1 - age / life) ** 1.5
            c = tuple(int(min(255, 90 + v * 0.7) * f) for v in COLS[b])
            l2 = 7 * f
            ld.line([(sx * S, sy * S), ((sx - math.cos(a) * l2) * S, (sy - math.sin(a) * l2) * S)], fill=c, width=3)

    # ---- explosions (shock ring on its own layer, clipped to the arena)
    xl = None
    for b in range(NB):
        age = st - dead[b] if np.isfinite(dead[b]) else -1
        if age < 0 or age > 1.4:
            continue
        if xl is None:
            xl = Image.new("RGB", img.size, (0, 0, 0))
        x, y = sim["frames"][min(len(sim["frames"]) - 1, int(dead[b] * FPS))][b]
        col = COLS[b]
        # shock ring
        rr = (BR + 260 * ease_out(age / 0.7)) * S
        a = (1 - clamp(age / 0.7)) ** 1.5
        if a > 0.01:
            xd = ImageDraw.Draw(xl)
            xd.ellipse([x * S - rr, y * S - rr, x * S + rr, y * S + rr], outline=tuple(int(v * a) for v in col),
                       width=int(4 * S))
        # flash
        if age < 0.18:
            fl = 1 - age / 0.18
            rg = BR * 3.2 * S / 4
            gd.ellipse([x * S / 4 - rg, y * S / 4 - rg, x * S / 4 + rg, y * S / 4 + rg],
                       fill=tuple(int(min(255, 120 + v) * fl) for v in col))
        # particles (drag, gravity-free, clipped to the arena)
        for m in range(70):
            ang = 2 * math.pi * hash01(b, m, 1)
            v0 = 220 + 520 * hash01(b, m, 2) ** 1.5
            life = 0.6 + 0.8 * hash01(b, m, 3)
            if age > life:
                continue
            tau = 0.35
            dd = v0 * tau * (1 - math.exp(-age / tau))
            sx, sy = x + math.cos(ang) * dd, y + math.sin(ang) * dd
            if math.hypot(sx - CX, sy - CY) > RA - 3:
                continue
            f = (1 - age / life) ** 1.3
            sz = (2.0 + 3.5 * hash01(b, m, 4)) * (0.5 + 0.5 * f) * S
            c = tuple(int(min(255, 60 + v * 0.9) * f) for v in col)
            ld.ellipse([sx * S - sz, sy * S - sz, sx * S + sz, sy * S + sz], fill=c)

    # ---- ball glow (quarter res)
    for b in range(NB):
        if dead[b] <= st:
            continue
        x, y = pos[b] * S / 4
        rg = BR * S / 4 * 1.9
        inten = 0.42 + (0.3 * win_k if b == win else 0)
        gd.ellipse([x - rg, y - rg, x + rg, y + rg], fill=tuple(int(v * inten) for v in COLS[b]))
    glow = glow.filter(ImageFilter.GaussianBlur(10)).resize(img.size, Image.BILINEAR)
    if xl is not None:
        lines = ImageChops.add(lines, Image.composite(xl, Image.new("RGB", img.size, (0, 0, 0)), STATIC["mask"]))
    img = ImageChops.add(img, lines)
    img = ImageChops.add(img, glow)

    # ---- balls (bump squash: none; ball pops briefly larger right before it explodes)
    for b in range(NB):
        if dead[b] <= st:
            continue
        rgb, m = STATIC["ball"][b]
        x, y = pos[b] * S
        img.paste(rgb, (int(round(x - rgb.width / 2)), int(round(y - rgb.height / 2))), m)

    # ---- winner zoom
    if after > 0 and win is not None:
        z = 1 + 0.07 * ease_io(after / 1.6)
        wx, wy = pos[win]
        fx = CX + (wx - CX) * 0.5
        fy = CY + (wy - CY) * 0.5
        Ws, Hs = img.size
        cw, ch = Ws / z, Hs / z
        x0 = clamp(fx * S - cw * (fx * S / Ws), 0, Ws - cw)
        y0 = clamp(fy * S - ch * (fy * S / Hs), 0, Hs - ch)
        img = img.resize((Ws, Hs), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))

    # ---- text
    hook = STATIC["hook"]
    hk = 1.0 if after <= 0 else 1 - ease_io(after / 0.35)
    if hk > 0.01:
        if hk < 1:
            hook = hook.copy()
            hook.putalpha(Image.fromarray((np.asarray(hook)[:, :, 3] * hk).astype(np.uint8)))
        img.paste(hook, (int(500 * S - hook.width / 2), int(272 * S)), hook)
    if after > 0.15 and win is not None:
        k = ease_out((after - 0.15) / 0.35)
        wi = STATIC["wins"][win]
        sc = 0.6 + 0.4 * k + 0.08 * math.sin(clamp((after - 0.15) / 0.5) * math.pi)
        wi2 = wi.resize((int(wi.width * sc), int(wi.height * sc)), Image.BICUBIC)
        if k < 1:
            wi2.putalpha(Image.fromarray((np.asarray(wi2)[:, :, 3] * k).astype(np.uint8)))
        img.paste(wi2, (int(500 * S - wi2.width / 2), int(318 * S - wi2.height / 2 + 32 * S)), wi2)
    # counters
    xs = (230, 500, 770)
    for b in range(NB):
        n = int(np.sum(STATIC["cut_t"][b] > st))
        col = COLS[b] if n > 0 else (90, 90, 100)
        ni = num_img(n, col)
        ct = STATIC["cut_times"][b]
        kk = np.searchsorted(ct, st, side="right")
        pop = 0.0
        if kk > 0:
            pop = 0.16 * math.exp(-(st - ct[kk - 1]) / 0.08)
        if after > 0 and b == win:
            pop += 0.12 * ease_io(after / 0.6)
        if pop > 0.004:
            ni = ni.resize((int(ni.width * (1 + pop)), int(ni.height * (1 + pop))), Image.BICUBIC)
        img.paste(ni, (int(xs[b] * S - ni.width / 2), int(520 * S - ni.height / 2)), ni)
        # small colour dot under each counter
        d = ImageDraw.Draw(img)
        rr = 9 * S
        dc = COLS[b] if n > 0 else (70, 70, 80)
        d.ellipse([xs[b] * S - rr, 600 * S - rr, xs[b] * S + rr, 600 * S + rr], fill=dc)
    wm = STATIC["wm"]
    img.paste(wm, (int(W * S / 2 - wm.width / 2), int(1545 * S)), wm)
    return img.resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- audio
def env(n, a, r):
    e = np.exp(-np.arange(n) / (r * SR))
    na = max(1, int(a * SR))
    e[:na] *= np.linspace(0, 1, na)
    return e


def band(x, lo, hi, soft=0.0):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    if soft <= 0:
        X[(f < lo) | (f > hi)] = 0
    else:
        X *= 1 / (1 + (lo / np.maximum(f, 1)) ** 4) / (1 + (f / hi) ** 4)
    return np.fft.irfft(X, len(x))


def add(buf, t, sig, gain=1.0, pan=0.0):
    k = int(round(t * SR))
    if k < 0 or k >= buf.shape[1]:
        return
    j = min(buf.shape[1], k + len(sig))
    gl = gain * math.cos((pan + 1) * math.pi / 4) * math.sqrt(2)
    gr = gain * math.sin((pan + 1) * math.pi / 4) * math.sqrt(2)
    buf[0, k:j] += sig[:j - k] * gl
    buf[1, k:j] += sig[:j - k] * gr


def snip(rng, pitch=1.0, var=0, big=0.0):
    """Short dry 'snip' (fine thread / scissors): band-passed noise click + tiny damped tick."""
    n = int(0.09 * SR)
    tt = np.arange(n) / SR
    noise = rng.normal(0, 1, n)
    lo, hi = [(2200, 5200), (2600, 6200), (1800, 4600), (3000, 6800)][var]
    lo, hi = lo * pitch, min(hi * pitch, 8500)
    click = band(noise, lo, hi, soft=1) * np.exp(-tt / (0.0065 + 0.004 * big))
    click[: int(0.0008 * SR)] *= np.linspace(0, 1, int(0.0008 * SR))
    f0 = [1700, 2000, 1500, 2250][var] * pitch
    tick = np.sin(2 * math.pi * f0 * tt + 0.3) * np.exp(-tt / 0.010) * 0.22
    body = 0.0
    if big > 0:
        body = band(noise, 500 * pitch, 2200 * pitch, soft=1) * np.exp(-tt / 0.022) * 0.9 * big
        body += np.sin(2 * math.pi * 320 * pitch * tt) * np.exp(-tt / 0.03) * 0.35 * big
    s = click / (np.max(np.abs(click)) + 1e-9) + tick + body
    return s


def knock(rng, pitch=1.0):
    """Felt / soft wood knock for ball-ball contact."""
    n = int(0.16 * SR)
    tt = np.arange(n) / SR
    f = 190 * pitch * (1 + 0.6 * np.exp(-tt / 0.01))
    ph = 2 * math.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-tt / 0.045)
    s += 0.35 * np.sin(2 * math.pi * 560 * pitch * tt) * np.exp(-tt / 0.018)
    s += 0.25 * band(rng.normal(0, 1, n), 300, 1800, soft=1) * np.exp(-tt / 0.008)
    s[: int(0.001 * SR)] *= np.linspace(0, 1, int(0.001 * SR))
    return s


def tick_wall(rng, pitch=1.0):
    n = int(0.06 * SR)
    tt = np.arange(n) / SR
    s = np.sin(2 * math.pi * 1250 * pitch * tt) * np.exp(-tt / 0.010)
    s += 0.5 * band(rng.normal(0, 1, n), 1500, 4500, soft=1) * np.exp(-tt / 0.004)
    return s


def boom(rng):
    n = int(1.4 * SR)
    tt = np.arange(n) / SR
    f = 46 + 70 * np.exp(-tt / 0.08)
    s = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.35)
    s += 0.55 * band(rng.normal(0, 1, n), 60, 900, soft=1) * np.exp(-tt / 0.12)
    # glassy crystal burst (inharmonic partials, quick decays)
    for fr, g, dcy in ((1320, 0.20, 0.25), (1990, 0.15, 0.18), (2730, 0.10, 0.14), (3510, 0.07, 0.10)):
        s += g * np.sin(2 * math.pi * fr * tt + fr) * np.exp(-tt / dcy)
    s += 0.25 * band(rng.normal(0, 1, n), 2500, 7000, soft=1) * np.exp(-tt / 0.06)
    s[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return s


def chime(freqs, dur=2.6):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    s = np.zeros(n)
    for k, f in enumerate(freqs):
        d0 = int(k * 0.07 * SR)
        x = tt[: n - d0]
        s[d0:] += (np.sin(2 * math.pi * f * x) + 0.25 * np.sin(2 * math.pi * f * 2.76 * x) * np.exp(-x / 0.2)) \
            * np.exp(-x / 0.7) * (1 - np.exp(-x / 0.002))
    return s


def synth_audio(sim, path):
    st_of, vt_of, v_end, total = build_timeline(sim)
    n = int(total * SR) + SR
    dry = np.zeros((2, n))
    rng = np.random.default_rng(11)
    stats = {"snips": 0, "events": 0, "knocks": 0, "walls": 0}
    # --- group cuts: 40 ms windows -> one sound event (a short zip if several), events >= 70 ms apart
    cuts = [(vt_of(te), d) for te, kind, d in sim["events"] if kind == "cut"]
    groups = []
    for vt, d in cuts:
        if groups and vt - groups[-1][0] < 0.07:
            groups[-1][1].append(d)
        else:
            groups.append([vt, [d]])
    dens = []                                      # recent density -> gentle ducking
    var = 0
    for vt, ds in groups:
        dens = [x for x in dens if vt - x < 0.6]
        duck = 1 / (1 + 0.12 * len(dens))
        dens.append(vt)
        m = len(ds)
        xm = np.mean([d[3][0] for d in ds])
        pan = clamp((xm - CX) / RA, -1, 1) * 0.5
        nz = min(m, 5)
        big = clamp((m - 4) / 6)
        for q in range(nz):
            var = (var + 1 + int(rng.random() * 2)) % 4
            p = 2 ** ((rng.random() * 6 - 3) / 12) * (1 + 0.04 * q)
            g = (0.6 + 0.4 * rng.random()) * (0.80 ** q) * duck
            add(dry, vt + q * 0.016, snip(rng, p, var, big if q == 0 else 0), 0.30 * g * (1 + 0.5 * big), pan)
            stats["snips"] += 1
        stats["events"] += 1
    last_k = -1
    for te, kind, d in sim["events"]:
        vt = vt_of(te)
        if kind == "bump":
            if vt - last_k < 0.08:
                continue
            last_k = vt
            sp = clamp(d[2] / 900, 0.3, 1)
            pan = clamp((d[3][0] - CX) / RA, -1, 1) * 0.5
            add(dry, vt, knock(rng, 2 ** ((rng.random() * 4 - 2) / 12)), 0.55 * sp, pan)
            stats["knocks"] += 1
        elif kind == "boom":
            pan = clamp((d[1][0] - CX) / RA, -1, 1) * 0.4
            add(dry, vt, boom(rng), 0.85, pan)
    # wall ticks: very soft, rate-limited (texture only)
    last_w = -1
    for te, kind, d in sim["events"]:
        if kind == "wall":
            vt = vt_of(te)
            if vt - last_w < 0.12:
                continue
            last_w = vt
            add(dry, vt, tick_wall(rng, 2 ** ((rng.random() * 4 - 2) / 12)), 0.05)
            stats["walls"] += 1
    # winner: soft glass chime (G major, airy), slightly after the last boom
    add(dry, v_end + 0.25, chime((392.0, 493.88, 587.33, 783.99, 987.77)), 0.20)
    # small room reverb
    irn = int(0.9 * SR)
    wet = np.zeros_like(dry)
    for c in range(2):
        ir = rng.normal(0, 1, irn) * np.exp(-np.arange(irn) / (0.16 * SR))
        ir = band(ir, 250, 6000, soft=1)
        ir /= np.sqrt(np.sum(ir ** 2))
        L = 1 << int(math.ceil(math.log2(n + irn)))
        wet[c] = np.fft.irfft(np.fft.rfft(dry[c], L) * np.fft.rfft(ir, L), L)[:n]
    mix = dry + 0.16 * wet
    # very quiet room tone so the gaps between snips are never digital silence
    air = np.stack([band(rng.normal(0, 1, n), 90, 1400, soft=1) for _ in range(2)])
    mix += air / np.std(air) * 0.0035 * np.max(np.abs(dry))
    # gentle high shelf: soften everything above ~7 kHz
    for c in range(2):
        X = np.fft.rfft(mix[c])
        f = np.fft.rfftfreq(n, 1 / SR)
        X *= 1 / np.sqrt(1 + (f / 7500) ** 4)
        mix[c] = np.fft.irfft(X, n)
    mix = mix[:, : int(total * SR)]
    fo = int(0.5 * SR)
    mix[:, -fo:] *= np.linspace(1, 0, fo) ** 1.5
    pk = np.max(np.abs(mix))
    mix = np.tanh(mix / pk * 1.3) / math.tanh(1.3) * 0.5
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.T.copy().tobytes())
    stats["max_events_per_s"] = int(max(np.bincount([int(g[0]) for g in groups])) if groups else 0)
    print("audio", stats, flush=True)


def master(raw, out, target=-14.3):
    """Gentle compression + peak limiting, then a measured linear gain to ~-14 LUFS.
    (loudnorm alone left sharp snips at 0 dBFS after AAC; 256k AAC keeps true peaks near -2 dBTP)"""
    lim = out + ".lim.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af",
                    "acompressor=threshold=-30dB:ratio=4:attack=1:release=80:makeup=4,"
                    "alimiter=limit=0.15:attack=0.5:release=30:level=false,lowpass=f=12000",
                    "-ar", str(SR), lim], check=True)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", lim, "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    i_lufs = float(r.split("Summary:")[1].split("I:")[1].split("LUFS")[0])
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", lim, "-af", f"volume={target - i_lufs:.2f}dB", out],
                   check=True)
    os.remove(lim)


def worker_init(seed):
    global SIM
    SIM = simulate(seed)
    init_static()
    STATIC["tl"] = build_timeline(SIM)


def render_bytes(fi):
    return render_frame(fi / FPS).tobytes()


def _job(sd):
    return sd, summary(simulate(sd))


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
            for sd, sm in p.imap(_job, range(a.search)):
                print(sd, sm, flush=True)
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
        raw = a.out + ".raw.wav"
        wav = a.out + ".wav"
        synth_audio(SIM, raw)
        master(raw, wav)
        os.remove(raw)
        proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                 "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                                 "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                                 "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", a.out],
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
        print(summary(s), "video", round(tl[3], 2), "s")
