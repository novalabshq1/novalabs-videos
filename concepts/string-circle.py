#!/usr/bin/env python3
"""String Circle — 4 neon balls, each tied to the arena edge by 160 strings (fan from the ball to fixed
anchors on an arc). Balls bounce only on the circle edge. A ball that crosses another ball's string
snaps it (no bounce, no slowdown). No strings left = out. Last ball with strings wins.

Autonomous: numpy + pillow + pycairo + ffmpeg. 1080x1920, 60 fps, cairo antialiasing.
Audio fully synthesized (Karplus-Strong string snaps, varied), -1 dBFS.

    python3.13 string-circle.py --search 0-200
    python3.13 string-circle.py --sim --seed N
    python3.13 string-circle.py --frames 0,0.3,0.6,0.97 --outdir keys/
    python3.13 string-circle.py --out video.mp4
"""
import argparse, math, os, subprocess, tempfile, wave
from multiprocessing import Pool
import numpy as np
import cairo
from PIL import Image, ImageFilter

W, H, FPS = 1080, 1920, 60
SR = 44100
SUB = 8
DT = 1.0 / (FPS * SUB)

CX, CY, RA = 540.0, 1040.0, 405.0          # arena
BR = 26.0                                   # ball radius
K = 140                                     # strings per ball
ARC = math.radians(78)                      # anchor arc span per ball
V0 = 430.0
P0, T_WEAK = 0.018, 40.0
HOLD = 3.6                                  # payoff seconds after the win
RETRACT = 0.22

TEAMS = [  # name, colour
    ("RED", (255, 58, 92)),
    ("BLUE", (64, 150, 255)),
    ("GREEN", (52, 236, 138)),
    ("YELLOW", (255, 206, 56)),
]
N = len(TEAMS)
SEED = 52


def snap_p(t):
    # strings get weaker over time: few snaps early, whole fans by the end
    return min(1.0, P0 + (1 - P0) * (t / T_WEAK) ** 2)


def speed_mult(t):
    return 1.0 + 0.7 * min(1.0, t / 40.0)


def setup(seed):
    rng = np.random.default_rng(seed)
    a0 = rng.random() * 2 * math.pi
    anchors = np.zeros((N, K, 2))
    pos = np.zeros((N, 2))
    vel = np.zeros((N, 2))
    for i in range(N):
        c = a0 + i * 2 * math.pi / N
        ang = c + np.linspace(-ARC / 2, ARC / 2, K)
        anchors[i, :, 0] = CX + RA * np.cos(ang)
        anchors[i, :, 1] = CY + RA * np.sin(ang)
        # ball starts on the far side of the centre, so its fan crosses the arena
        pc = c + math.pi + rng.normal(0, 0.35)
        pr = RA * (0.25 + 0.2 * rng.random())
        pos[i] = (CX + pr * math.cos(pc), CY + pr * math.sin(pc))
        d = rng.random() * 2 * math.pi
        vel[i] = (math.cos(d) * V0, math.sin(d) * V0)
    return rng, anchors, pos, vel


def simulate(seed, tmax=75.0):
    rng, anchors, pos, vel = setup(seed)
    alive_s = np.ones((N, K), bool)
    alive = [True] * N
    C = np.array((CX, CY))
    events = []          # (t, kind, data)
    frames = []
    t = 0.0
    end_t = None
    winner = None

    def sides(p):
        # s[a, b, k] = cross(anchor_bk - P_b, P_a - P_b)
        d = anchors - p[:, None, :]                      # (N,K,2)
        rel = p[:, None, :] - p[None, :, :]              # rel[a,b] = P_a - P_b
        return d[None, :, :, 0] * rel[:, :, None, 1] - d[None, :, :, 1] * rel[:, :, None, 0]

    prev = sides(pos)
    eye = np.eye(N, dtype=bool)
    while True:
        for _ in range(SUB):
            sp = V0 * speed_mult(t)
            for i in range(N):
                if alive[i]:
                    vel[i] *= sp / max(np.linalg.norm(vel[i]), 1e-6)
            am = np.array(alive, float)[:, None]
            pos += vel * DT * am
            for i in range(N):
                if not alive[i]:
                    continue
                d = pos[i] - C
                r = np.linalg.norm(d)
                if r > RA - BR:
                    nrm = d / r
                    pos[i] = C + nrm * (RA - BR)
                    vn = np.dot(vel[i], nrm)
                    if vn > 0:
                        vel[i] -= 2 * vn * nrm
                        th = rng.normal(0, 0.06)
                        c, s_ = math.cos(th), math.sin(th)
                        vel[i] = np.array([c * vel[i, 0] - s_ * vel[i, 1], s_ * vel[i, 0] + c * vel[i, 1]])
                        events.append((t, "wall", (i, *(C + nrm * RA))))
            cur = sides(pos)
            flip = (np.sign(cur) != np.sign(prev)) & (np.sign(prev) != 0)
            flip &= ~eye[:, :, None]
            flip &= alive_s[None, :, :]
            al = np.array(alive)
            flip &= al[:, None, None] & al[None, :, None]
            if flip.any():
                for a, b, k in zip(*np.nonzero(flip)):
                    if not alive_s[b, k]:
                        continue
                    d = anchors[b, k] - pos[b]
                    rel = pos[a] - pos[b]
                    u = float(np.dot(rel, d) / max(np.dot(d, d), 1e-9))
                    if 0.0 < u < 1.0 and rng.random() < snap_p(t):
                        alive_s[b, k] = False
                        q = pos[b] + d * u
                        events.append((t, "cut", (b, a, int(k), u, float(q[0]), float(q[1]))))
                for b in range(N):
                    if alive[b] and not alive_s[b].any():
                        alive[b] = False
                        events.append((t, "out", (b, *pos[b])))
                        if sum(alive) == 1 and end_t is None:
                            end_t = t
                            winner = alive.index(True)
                        elif sum(alive) == 0 and end_t is None:
                            end_t = t
                            winner = b
            prev = cur
            t += DT
        frames.append(dict(t=t, pos=pos.copy(), alive=list(alive)))
        if end_t is not None and t >= end_t + HOLD:
            break
        if t > tmax:
            break
    return dict(frames=frames, anchors=anchors, events=events, end_t=end_t, winner=winner, seed=seed)


def summary(sim):
    outs = [round(e[0], 1) for e in sim["events"] if e[1] == "out"]
    cuts = [e[0] for e in sim["events"] if e[1] == "cut"]
    left = [N * K - sum(1 for c in cuts if c < tt) for tt in (5, 10, 15, 20, 25)]
    return outs, left


def _score(seed):
    s = simulate(seed)
    outs, n_cut = summary(s)
    return seed, outs, n_cut, s["winner"]


# ---------------------------------------------------------------- rendering
GOLD = (255, 204, 84)


def clamp(x, a=0.0, b=1.0):
    return min(max(x, a), b)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def setc(ctx, c, a=1.0, mul=1.0):
    ctx.set_source_rgba(min(1, c[0] / 255 * mul), min(1, c[1] / 255 * mul), min(1, c[2] / 255 * mul), a)


SIM = None
CUTS = None        # per ball: list of (t, k, u, qx, qy)
CUT_T = None       # (N,K) cut time or inf
OUT_T = None
SPARKS = []        # (t, x, y, vx, vy, col, life)
BURSTS = []        # elimination particles
T_END = 0.0


def prepare(sim):
    global SIM, CUT_T, OUT_T, SPARKS, BURSTS, T_END, CUTS
    SIM = sim
    CUT_T = np.full((N, K), np.inf)
    CUTS = np.zeros((N, K, 3))      # u, qx, qy
    OUT_T = [math.inf] * N
    rng = np.random.default_rng(7)
    SPARKS = []
    BURSTS = []
    for t, kind, d in sim["events"]:
        if kind == "cut":
            b, a, k, u, qx, qy = d
            CUT_T[b, k] = t
            CUTS[b, k] = (u, qx, qy)
            if rng.random() < 0.6:
                for _ in range(3):
                    ang = rng.random() * 2 * math.pi
                    v = 120 + 260 * rng.random()
                    SPARKS.append((t, qx, qy, v * math.cos(ang), v * math.sin(ang),
                                   TEAMS[b][1] if rng.random() < 0.6 else (255, 255, 255), 0.25 + 0.3 * rng.random()))
        elif kind == "out":
            b, x, y = d
            OUT_T[b] = t
            for _ in range(140):
                ang = rng.random() * 2 * math.pi
                v = 80 + 620 * rng.random() ** 1.5
                BURSTS.append((t, x, y, v * math.cos(ang), v * math.sin(ang), TEAMS[b][1],
                               0.5 + 0.9 * rng.random(), 1.5 + 3.5 * rng.random()))
    if sim["end_t"] is not None:
        w = sim["winner"]
        te = sim["end_t"] + 0.25
        fw = min(len(sim["frames"]) - 1, int(te * FPS))
        x, y = sim["frames"][fw]["pos"][w]
        for _ in range(180):
            ang = rng.random() * 2 * math.pi
            v = 150 + 500 * rng.random()
            col = TEAMS[w][1] if rng.random() < 0.7 else (255, 255, 255)
            BURSTS.append((te, x, y, v * math.cos(ang), v * math.sin(ang), col,
                           0.8 + 1.2 * rng.random(), 1.2 + 2.5 * rng.random()))
    T_END = sim["frames"][-1]["t"]
    global SP_ARR, BU_ARR
    SP_ARR = np.array([(s[0], s[1], s[2], s[3], s[4], *s[5], s[6]) for s in SPARKS]) if SPARKS else np.zeros((0, 10))
    BU_ARR = np.array([(s[0], s[1], s[2], s[3], s[4], *s[5], s[6], s[7]) for s in BURSTS]) if BURSTS else np.zeros((0, 11))


def frame_at(t):
    fr = SIM["frames"]
    i = int(clamp(round(t * FPS) - 1, 0, len(fr) - 1))
    return fr[i]


def text_center(ctx, txt, x, y, size, face="Inter Black"):
    ctx.select_font_face(face, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    xb, yb, tw, th, xa, ya = ctx.text_extents(txt)
    ctx.move_to(x - tw / 2 - xb, y - th / 2 - yb)
    return tw


def show_text(ctx, txt, x, y, size, col, a=1.0, face="Inter Black", shadow=True):
    if shadow:
        text_center(ctx, txt, x, y + 6, size, face)
        ctx.set_source_rgba(0, 0, 0, 0.6 * a)
        ctx.show_text(txt)
    text_center(ctx, txt, x, y, size, face)
    setc(ctx, col, a)
    ctx.show_text(txt)


def draw_ball(ctx, x, y, r, col, a=1.0, glow=1.0):
    # outer glow
    g = cairo.RadialGradient(x, y, r * 0.6, x, y, r * 3.2)
    g.add_color_stop_rgba(0, col[0] / 255, col[1] / 255, col[2] / 255, 0.42 * a * glow)
    g.add_color_stop_rgba(1, col[0] / 255, col[1] / 255, col[2] / 255, 0)
    ctx.set_source(g)
    ctx.arc(x, y, r * 3.2, 0, 2 * math.pi)
    ctx.fill()
    # sphere body
    g = cairo.RadialGradient(x - r * 0.35, y - r * 0.4, r * 0.08, x, y, r)
    lc = [min(1, c / 255 * 0.45 + 0.6) for c in col]
    g.add_color_stop_rgba(0, lc[0], lc[1], lc[2], a)
    g.add_color_stop_rgba(0.45, col[0] / 255, col[1] / 255, col[2] / 255, a)
    g.add_color_stop_rgba(1, col[0] / 255 * 0.45, col[1] / 255 * 0.45, col[2] / 255 * 0.45, a)
    ctx.set_source(g)
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.fill()
    # rim light
    ctx.set_line_width(2.0)
    setc(ctx, col, 0.9 * a, 1.25)
    ctx.arc(x, y, r - 1, 0, 2 * math.pi)
    ctx.stroke()
    # specular
    g = cairo.RadialGradient(x - r * 0.38, y - r * 0.42, 0, x - r * 0.38, y - r * 0.42, r * 0.42)
    g.add_color_stop_rgba(0, 1, 1, 1, 0.85 * a)
    g.add_color_stop_rgba(1, 1, 1, 1, 0)
    ctx.set_source(g)
    ctx.arc(x - r * 0.38, y - r * 0.42, r * 0.42, 0, 2 * math.pi)
    ctx.fill()


def counters(ctx, t, winner_t, winner):
    # 4 counters under the title
    xs = [240, 440, 640, 840]
    y = 405
    for b in range(N):
        col = TEAMS[b][1]
        n_left = int(np.sum(CUT_T[b] > t))
        out = t >= OUT_T[b]
        # pulse when counter changes recently
        recent = CUT_T[b][CUT_T[b] <= t]
        dtc = t - recent.max() if recent.size else 9
        pop = 1 + 0.16 * max(0, 1 - dtc / 0.18)
        x = xs[b]
        if out:
            fade = clamp((t - OUT_T[b]) / 0.4)
            setc(ctx, col, 0.18 + 0.5 * (1 - fade))
            text_center(ctx, "0", x, y, 92)
            ctx.show_text("0")
            # strike
            ctx.set_line_width(7)
            ctx.set_line_cap(cairo.LINE_CAP_ROUND)
            setc(ctx, (255, 255, 255), 0.75 * ease_out(fade * 2))
            L = 46 * ease_out(fade * 2)
            ctx.move_to(x - L, y + L * 0.55)
            ctx.line_to(x + L, y - L * 0.55)
            ctx.stroke()
            # small dot below
            setc(ctx, col, 0.25)
            ctx.arc(x, y + 72, 9, 0, 2 * math.pi)
            ctx.fill()
            continue
        win = winner is not None and t >= winner_t and b == winner
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(pop, pop)
        show_text(ctx, str(n_left), 0, 0, 92, col if not win else col)
        ctx.restore()
        draw_ball(ctx, x, y + 72, 11, col, glow=0.6)


BG = None


def make_bg():
    s = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    c = cairo.Context(s)
    g = cairo.RadialGradient(CX, CY, 50, CX, CY, 1250)
    g.add_color_stop_rgb(0, 0.055, 0.045, 0.085)
    g.add_color_stop_rgb(1, 0.012, 0.010, 0.020)
    c.set_source(g)
    c.paint()
    return s


def render_frame(t):
    global BG
    if BG is None:
        BG = make_bg()
    fr = frame_at(t)
    pos = fr["pos"]
    end_t = SIM["end_t"]
    winner = SIM["winner"]
    anchors = SIM["anchors"]

    # ---------- string layer (additive glow source)
    sl = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    c = cairo.Context(sl)
    c.set_source_rgb(0, 0, 0)
    c.paint()
    zoom = 1.0
    if end_t is not None and t > end_t:
        zoom = 1 + 0.07 * ease_io((t - end_t) / 1.0)
    wx = pos[winner] if (winner is not None and end_t is not None and t > end_t) else np.array((CX, CY))
    zc = np.array((CX, CY)) + (wx - np.array((CX, CY))) * 0.25 * ease_io((t - end_t) / 1.0 if end_t else 0)

    def world(cc):
        cc.translate(zc[0], zc[1])
        cc.scale(zoom, zoom)
        cc.translate(-zc[0], -zc[1])

    c.save()
    world(c)
    c.set_operator(cairo.OPERATOR_ADD)
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    for b in range(N):
        col = TEAMS[b][1]
        p = pos[b]
        live = CUT_T[b] > t
        n_live = int(live.sum())
        if n_live:
            # dimmer when crowded so the fan stays readable
            al = 0.8 if n_live < 30 else 0.8 * (30 / n_live) ** 0.3
            c.set_line_width(1.05)
            setc(c, col, al)
            for k in np.nonzero(live)[0]:
                c.move_to(p[0], p[1])
                c.line_to(anchors[b, k, 0], anchors[b, k, 1])
            c.stroke()
        # retracting halves
        rec = np.nonzero((CUT_T[b] <= t) & (CUT_T[b] > t - RETRACT))[0]
        if rec.size:
            c.set_line_width(1.6)
            for k in rec:
                tau = (t - CUT_T[b, k]) / RETRACT
                e = ease_out(tau)
                u = CUTS[b, k, 0]
                a = anchors[b, k]
                d = a - p
                setc(c, col, 0.95 * (1 - tau * 0.6), 1.15)
                # ball-side half shrinks toward the ball (+ slight curl)
                l1 = u * (1 - e)
                c.move_to(p[0], p[1])
                c.line_to(p[0] + d[0] * l1, p[1] + d[1] * l1)
                # anchor-side half shrinks toward the anchor
                l2 = (1 - u) * (1 - e)
                c.move_to(a[0], a[1])
                c.line_to(a[0] - d[0] * l2, a[1] - d[1] * l2)
                c.stroke()
        # anchors: tiny dots on the rim
        if n_live:
            setc(c, col, 0.9)
            for k in np.nonzero(live)[0][::2]:
                c.arc(anchors[b, k, 0], anchors[b, k, 1], 1.6, 0, 2 * math.pi)
                c.fill()
    c.restore()
    sl.flush()
    sarr = np.ndarray((H, W, 4), np.uint8, sl.get_data()).copy()
    rgb = sarr[:, :, [2, 1, 0]]
    small = Image.fromarray(rgb).resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3.5))
    glow = np.asarray(small.resize((W, H), Image.BILINEAR)).astype(np.uint16)

    # ---------- main composition
    base = np.ndarray((H, W, 4), np.uint8, BG.get_data())[:, :, [2, 1, 0]].astype(np.uint16)
    comp = base + rgb.astype(np.uint16) + (glow * 0.9).astype(np.uint16)
    comp = np.clip(comp, 0, 255).astype(np.uint8)
    # back to a cairo surface for the overlays
    arr = np.zeros((H, W, 4), np.uint8)
    arr[:, :, 0] = comp[:, :, 2]
    arr[:, :, 1] = comp[:, :, 1]
    arr[:, :, 2] = comp[:, :, 0]
    s = cairo.ImageSurface.create_for_data(arr, cairo.FORMAT_RGB24, W, H)
    c = cairo.Context(s)

    c.save()
    world(c)
    # arena ring
    c.set_line_width(4)
    c.set_source_rgba(1, 1, 1, 0.92)
    c.arc(CX, CY, RA + 2, 0, 2 * math.pi)
    c.stroke()
    c.set_line_width(14)
    c.set_source_rgba(1, 1, 1, 0.06)
    c.arc(CX, CY, RA + 2, 0, 2 * math.pi)
    c.stroke()
    # sparks
    if len(SP_ARR):
        m = (SP_ARR[:, 0] <= t) & (SP_ARR[:, 0] + SP_ARR[:, 8] > t)
        c.set_operator(cairo.OPERATOR_ADD)
        c.set_line_cap(cairo.LINE_CAP_ROUND)
        c.set_line_width(2.2)
        for row in SP_ARR[m]:
            age = t - row[0]
            f = age / row[8]
            x = row[1] + row[3] * age * (1 - 0.5 * f)
            y = row[2] + row[4] * age * (1 - 0.5 * f)
            c.set_source_rgba(row[5] / 255, row[6] / 255, row[7] / 255, 1 - f)
            c.move_to(x, y)
            c.line_to(x - row[3] * 0.025, y - row[4] * 0.025)
            c.stroke()
        c.set_operator(cairo.OPERATOR_OVER)
    # elimination bursts
    if len(BU_ARR):
        m = (BU_ARR[:, 0] <= t) & (BU_ARR[:, 0] + BU_ARR[:, 8] > t)
        c.set_operator(cairo.OPERATOR_ADD)
        for row in BU_ARR[m]:
            age = t - row[0]
            f = age / row[8]
            k = 1 - math.exp(-age * 3.2)
            x = row[1] + row[3] / 3.2 * k
            y = row[2] + row[4] / 3.2 * k
            c.set_source_rgba(row[5] / 255, row[6] / 255, row[7] / 255, (1 - f) ** 1.3)
            c.arc(x, y, row[9] * (1 - 0.5 * f), 0, 2 * math.pi)
            c.fill()
        c.set_operator(cairo.OPERATOR_OVER)
    # shockwave rings + balls
    for b in range(N):
        col = TEAMS[b][1]
        if t >= OUT_T[b]:
            age = t - OUT_T[b]
            if age < 0.6:
                ox, oy = [e[2][1:] for e in SIM["events"] if e[1] == "out" and e[2][0] == b][0]
                c.set_line_width(6 * (1 - age / 0.6) + 1)
                setc(c, col, 0.8 * (1 - age / 0.6), 1.2)
                c.arc(ox, oy, BR + 220 * ease_out(age / 0.6), 0, 2 * math.pi)
                c.stroke()
                if age < 0.12:
                    draw_ball(c, ox, oy, BR * (1 + 1.5 * age / 0.12), (255, 255, 255), a=1 - age / 0.12)
            continue
        p = pos[b]
        draw_ball(c, p[0], p[1], BR, col)
    # winner halo
    if end_t is not None and t > end_t and winner is not None:
        age = t - end_t
        p = pos[winner]
        pul = 0.5 + 0.5 * math.sin(age * 6)
        c.set_line_width(3)
        setc(c, TEAMS[winner][1], 0.55 * ease_out(age / 0.5) * (0.6 + 0.4 * pul))
        c.arc(p[0], p[1], BR + 14 + 6 * pul, 0, 2 * math.pi)
        c.stroke()
    c.restore()

    # ---------- UI
    show_text(c, "WHICH ONE WINS?", W / 2 - 40 + 40, 245, 76, (255, 255, 255))
    counters(c, t, end_t if end_t else math.inf, winner)
    # winner banner
    if end_t is not None and t > end_t + 0.25 and winner is not None:
        age = t - end_t - 0.25
        e = ease_out(age / 0.45)
        col = TEAMS[winner][1]
        c.save()
        c.translate(W / 2, 1580)
        sc = 0.6 + 0.4 * e + 0.05 * math.sin(clamp(age / 0.45) * math.pi)
        c.scale(sc, sc)
        show_text(c, f"{TEAMS[winner][0]} WINS", 0, 0, 104, col, a=e)
        c.restore()
    # flash at each elimination
    for b in range(N):
        age = t - OUT_T[b]
        if 0 <= age < 0.18:
            final = SIM["end_t"] is not None and abs(OUT_T[b] - SIM["end_t"]) < 1e-9
            setc(c, TEAMS[b][1], (0.09 if final else 0.06) * (1 - age / 0.18))
            c.set_operator(cairo.OPERATOR_ADD)
            c.paint()
            c.set_operator(cairo.OPERATOR_OVER)
    # watermark
    c.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    text_center(c, "@novalabs.hq", W / 2, 1745, 30, "Inter")
    c.set_source_rgba(1, 1, 1, 0.32)
    c.show_text("@novalabs.hq")
    s.flush()
    out = arr[:, :, [2, 1, 0]]
    # fade in/out
    if t < 0.12:
        out = (out * (0.4 + 0.6 * t / 0.12)).astype(np.uint8)
    if t > T_END - 0.35:
        out = (out * clamp((T_END - t) / 0.35)).astype(np.uint8)
    return np.ascontiguousarray(out)


# ---------------------------------------------------------------- audio
def env(n, a, r):
    e = np.exp(-np.arange(n) / (r * SR))
    na = max(1, int(a * SR))
    e[:na] *= np.linspace(0, 1, na)
    return e


def add(buf, t, sig, gain=1.0, pan=0.0):
    k = int(round(t * SR))
    if k < 0 or k >= buf.shape[1]:
        return
    j = min(buf.shape[1], k + len(sig))
    gl = math.cos((pan + 1) * math.pi / 4)
    gr = math.sin((pan + 1) * math.pi / 4)
    buf[0, k:j] += sig[:j - k] * gain * gl
    buf[1, k:j] += sig[:j - k] * gain * gr


def band(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))


def karplus(freq, dur, rng, decay=0.996, bright=0.5, pluck_pos=0.18):
    """Karplus-Strong string with a noise burst excitation; bright in [0,1] sets the damping filter."""
    n = int(dur * SR)
    p = max(2, int(round(SR / freq)))
    exc = rng.uniform(-1, 1, p)
    # pluck position comb -> harmonic colour
    sh = max(1, int(p * pluck_pos))
    exc = exc - np.roll(exc, sh)
    out = np.zeros(n)
    buf = exc.copy()
    a = 0.5 + 0.5 * bright
    idx = 0
    # vectorised by period blocks
    full = np.zeros(n + p)
    full[:p] = buf
    for s in range(p, n + p, p):
        blk = full[s - p:s]
        nxt = decay * (a * blk + (1 - a) * np.roll(blk, 1))
        e = min(n + p, s + p)
        full[s:e] = nxt[:e - s]
    out = full[:n]
    return out / (np.abs(out).max() + 1e-9)


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
    total = T_END
    n = int(total * SR) + SR
    dry = np.zeros((2, n))
    rng = np.random.default_rng(5)
    base = [329.63, 392.0, 440.0, 293.66]          # each ball's string family (E4, G4, A4, D4)
    timbres = [dict(decay=0.994, bright=0.35, pluck_pos=0.12),   # twang
               dict(decay=0.990, bright=0.75, pluck_pos=0.22),   # bright snap
               dict(decay=0.997, bright=0.20, pluck_pos=0.08),   # dull thick
               dict(decay=0.985, bright=0.95, pluck_pos=0.30),   # wiry
               dict(decay=0.992, bright=0.55, pluck_pos=0.40)]   # hollow
    cache = {}
    last_t = -1.0
    active = []
    for te, kind, d in sim["events"]:
        if kind == "cut":
            b, a, k, u, qx, qy = d
            # at most ~4 overlapping snaps, spread a few ms apart
            active = [x for x in active if x > te - 0.06]
            if len(active) >= 4 or te - last_t < 0.018:
                continue
            tt = max(te, last_t + 0.008)
            last_t = tt
            active.append(tt)
            semi = rng.integers(-5, 6)
            f = base[b] * 2 ** (semi / 12) * (1.0 + 0.5 * (rng.random() < 0.25))
            tb = int(rng.integers(0, len(timbres)))
            key = (round(f, 1), tb)
            if key not in cache:
                cache[key] = karplus(f, 0.55 + 0.25 * rng.random(), rng, **timbres[tb])
            sig = cache[key].copy()
            sig *= env(len(sig), 0.0005, 0.08 + 0.18 * rng.random())
            # snap transient
            tn = int(0.012 * SR)
            click = band(rng.normal(0, 1, tn), 2500, 12000) * env(tn, 0.0002, 0.003)
            pan = clamp((qx - CX) / RA, -1, 1) * 0.8
            g = 0.7 + 0.3 * rng.random()
            add(dry, tt, sig, 0.30 * g, pan)
            add(dry, tt, click, 0.20 * g, pan)
        elif kind == "wall":
            b, x, y = d
            pan = clamp((x - CX) / RA, -1, 1) * 0.8
            add(dry, te, tone(170 + 40 * rng.random(), 0.08, a=0.001, r=0.02, parts=((1, 1), (2.3, 0.3))), 0.10, pan)
        elif kind == "out":
            b, x, y = d
            final = sim["end_t"] is not None and abs(te - sim["end_t"]) < 1e-9
            g = 0.55 if final else 0.4
            pan = clamp((x - CX) / RA, -1, 1) * 0.6
            add(dry, te, sweep(90, 34, 1.3, a=0.003, r=0.45 if final else 0.3), 0.9 * g, pan * 0.3)
            nzn = int(0.7 * SR)
            add(dry, te, band(rng.normal(0, 1, nzn), 60, 1600) * env(nzn, 0.002, 0.14), 0.42 * g, pan)
            add(dry, te, band(rng.normal(0, 1, nzn), 3000, 12000) * env(nzn, 0.001, 0.07), 0.14 * g, pan)
            # low string chord, all strings of this ball let go
            for m, semi in enumerate((-12, -5, 0, 7)):
                sig = karplus(base[b] / 2 * 2 ** (semi / 12), 1.6, rng, decay=0.998, bright=0.3)
                add(dry, te + 0.012 * m, sig, 0.16 * g, pan * 0.5)
    if sim["end_t"] is not None:
        te = sim["end_t"] + 0.25
        w = sim["winner"]
        for m, semi in enumerate((0, 4, 7, 12, 16, 19, 24)):
            sig = karplus(base[w] * 2 ** (semi / 12), 2.4, rng, decay=0.9985, bright=0.5)
            add(dry, te + 0.07 * m, sig, 0.17, (m - 3) / 4)
        tt = np.arange(int(3 * SR)) / SR
        shimmer = sum(np.sin(2 * math.pi * base[w] * 4 * h * tt) * 0.3 / h for h in (1, 1.5, 2)) * env(len(tt), 0.3, 0.9)
        add(dry, te, shimmer, 0.05)
    # soft low drone that rises with the speed, and a riser into the final knock-out
    tt = np.arange(n) / SR
    drone = (np.sin(2 * math.pi * 55 * tt) + 0.5 * np.sin(2 * math.pi * 82.5 * tt + 1) +
             0.3 * np.sin(2 * math.pi * 110.4 * tt)) * 0.035
    drone *= np.clip(tt / 1.0, 0, 1)
    if sim["end_t"] is not None:
        drone *= np.clip((sim["end_t"] + 1.5 - tt) / 1.5, 0, 1)
        r0 = sim["end_t"] - 3.5
        rn = int(3.5 * SR)
        x = np.linspace(0, 1, rn)
        riser = band(rng.normal(0, 1, rn), 800, 9000) * x ** 2.5 * 0.08
        riser += np.sin(2 * math.pi * np.cumsum(200 + 600 * x ** 2) / SR) * x ** 3 * 0.04
        add(dry, r0, riser, 1.0)
    dry += drone[None, :]
    # tiny stereo room
    wet = np.zeros_like(dry)
    for dl, gg in ((0.031, 0.22), (0.047, 0.17), (0.071, 0.12), (0.113, 0.08)):
        k = int(dl * SR)
        wet[0, k:] += dry[1, :-k] * gg
        wet[1, k:] += dry[0, :-k] * gg
    mix = dry + wet
    mix *= 1.0 / (np.percentile(np.abs(mix), 99.9) + 1e-9)
    mix = np.tanh(mix * 0.9)
    mix *= 10 ** (-3 / 20) / (np.abs(mix).max() + 1e-9)    # -3 dBFS: AAC overshoots on dense snaps
    n_out = int(T_END * SR)
    mix = mix[:, :n_out]
    fo = int(0.35 * SR)
    mix[:, -fo:] *= np.linspace(1, 0, fo)
    pcm = (mix.T * 32767).astype("<i2")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- main
def worker_init(seed):
    prepare(simulate(seed))


def render_bytes(fi):
    return render_frame((fi + 1) / FPS).tobytes()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--search")
    ap.add_argument("--frames")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.search:
        a, b = map(int, args.search.split("-"))
        with Pool(os.cpu_count()) as p:
            for seed, outs, n_cut, w in p.imap_unordered(_score, range(a, b)):
                print(seed, outs, n_cut, w, flush=True)
    elif args.sim:
        s = simulate(args.seed)
        print(summary(s), s["winner"], s["end_t"])
    elif args.frames:
        prepare(simulate(args.seed))
        os.makedirs(args.outdir, exist_ok=True)
        for f in args.frames.split(","):
            tt = float(f) * T_END if float(f) <= 1 else float(f)
            Image.fromarray(render_frame(tt)).save(os.path.join(args.outdir, f"f_{tt:05.2f}.png"))
    elif args.out:
        sim = simulate(args.seed)
        prepare(sim)
        nfr = int(T_END * FPS) - 1
        with tempfile.TemporaryDirectory() as td:
            wav = os.path.join(td, "a.wav")
            synth_audio(sim, wav)
            proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                     "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                                     "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                                     "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", args.out],
                                    stdin=subprocess.PIPE)
            with Pool(os.cpu_count(), initializer=worker_init, initargs=(args.seed,)) as p:
                for i, buf in enumerate(p.imap(render_bytes, range(nfr), chunksize=8)):
                    proc.stdin.write(buf)
                    if i % 300 == 0:
                        print(f"frame {i}/{nfr}", flush=True)
            proc.stdin.close()
            proc.wait()
        print("done", args.out)
