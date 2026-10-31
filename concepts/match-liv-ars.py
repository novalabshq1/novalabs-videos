#!/usr/bin/env python3
"""Match Day — Liverpool vs Arsenal (minimal style).
A thin white ring spins slowly with a goal-shaped opening (posts + net). Two logo balls (LIV, ARS)
travel in straight lines at constant speed, bouncing elastically off the ring and off each other.
A ball that leaves through the goal scores for its team, rests in the net, fades, and respawns.
Clock 0' -> 90' (HT pause at 45'), FULL TIME, winner shown.

No trails, no glow, no flashes, no camera motion. Sound = synthesized foley only (no notes).

    python3.13 match-liv-ars.py --search 3000
    python3.13 match-liv-ars.py --seed N
    python3.13 match-liv-ars.py --seed N --frames 0,5,20,...  --outdir keys/
    python3.13 match-liv-ars.py --seed N --out video.mp4
"""
import argparse, math, os, subprocess, sys, wave, json
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

W, H, FPS, S = 1080, 1920, 60, 2
SR = 48000
SUB = 8
DT = 1.0 / (FPS * SUB)

CX, CY, R = 540.0, 990.0, 440.0        # arena (880 px wide)
BR = 40.0                               # ball radius
POST_R = 6.0
GA = 0.165                              # goal half-angle (rad)
ND = 68.0                               # net depth
V = 640.0                               # ball speed px/s
WROT = 0.50                             # ring angular speed rad/s

T_HALF = 21.0                           # seconds per half
T_HT = 1.0                              # clock pause at half-time
T_FT = 2 * T_HALF + T_HT                # 43 s : full time
HOLD = 4.0
T_END = T_FT + HOLD
NET_STAY = 0.75                         # ball rests in net
NET_FADE = 0.30
RESPAWN = 1.25                          # after goal

TEAMS = [
    dict(name="LIVERPOOL", code="LIV", logo="liverpool.png", ball=(200, 16, 46), rim=(255, 255, 255)),
    dict(name="ARSENAL", code="ARS", logo="arsenal.png", ball=(246, 246, 246), rim=(200, 200, 205)),
]
ACCENT = (255, 206, 84)
BG = (9, 9, 12)
FONT_B = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
FONT_SB = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"


def clamp(x, a=0.0, b=1.0):
    return min(max(x, a), b)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def minute(t):
    if t < T_HALF:
        return 45.0 * t / T_HALF
    if t < T_HALF + T_HT:
        return 45.0
    return min(90.0, 45.0 + 45.0 * (t - T_HALF - T_HT) / T_HALF)


# ---------------------------------------------------------------- simulation
def simulate(seed, record=False):
    rng = np.random.default_rng(seed)
    g0 = rng.random() * 2 * math.pi
    pos, vel = [], []
    for i, sx in enumerate((-1, 1)):
        p = [CX + sx * 0.38 * R, CY + (rng.random() - 0.5) * 0.3 * R]
        a = rng.random() * 2 * math.pi
        pos.append(p)
        vel.append([V * math.cos(a), V * math.sin(a)])
    mode = ["play", "play"]       # play | net | gone
    tmode = [0.0, 0.0]            # time mode started
    spawn_t = [-10.0, -10.0]
    netloc = [None, None]         # [a, b, va, vb]
    score = [0, 0]
    goals, events = [], []
    frames = []
    nsteps = int(round(T_FT * FPS * SUB))
    last_wall = [-1.0, -1.0]
    graze = 0
    overlap = 0
    stuck = 0
    for k in range(nsteps + 1):
        t = k * DT
        g = g0 + WROT * t
        cg, sg = math.cos(g), math.sin(g)
        if record and k % SUB == 0:
            fr = dict(t=t, g=g, score=list(score), balls=[])
            for i in range(2):
                b = dict(mode=mode[i], alpha=1.0, scale=1.0)
                if mode[i] == "play":
                    b["x"], b["y"] = pos[i]
                    s = clamp((t - spawn_t[i]) / 0.22)
                    b["alpha"], b["scale"] = s, 0.55 + 0.45 * ease_out(s)
                elif mode[i] == "net":
                    a_, b_ = netloc[i][0], netloc[i][1]
                    b["x"] = CX + a_ * cg - b_ * sg
                    b["y"] = CY + a_ * sg + b_ * cg
                    b["alpha"] = 1.0 - clamp((t - tmode[i] - NET_STAY) / NET_FADE)
                fr["balls"].append(b)
            frames.append(fr)
        if k == nsteps:
            break
        for i in range(2):
            if mode[i] == "play":
                pos[i][0] += vel[i][0] * DT
                pos[i][1] += vel[i][1] * DT
                dx, dy = pos[i][0] - CX, pos[i][1] - CY
                r = math.hypot(dx, dy)
                rel = wrap(math.atan2(dy, dx) - g)
                if abs(rel) > GA:
                    if r + BR > R:
                        nx, ny = dx / r, dy / r
                        vn = vel[i][0] * nx + vel[i][1] * ny
                        if vn > 0:
                            vel[i][0] -= 2 * vn * nx
                            vel[i][1] -= 2 * vn * ny
                            events.append(("wall", t, pos[i][0], vn / V, i))
                            if vn / V < 0.22:
                                graze += 1
                        pos[i][0] = CX + nx * (R - BR)
                        pos[i][1] = CY + ny * (R - BR)
                else:
                    for sgn in (-1, 1):
                        px = CX + R * math.cos(g + sgn * GA)
                        py = CY + R * math.sin(g + sgn * GA)
                        ex, ey = pos[i][0] - px, pos[i][1] - py
                        d = math.hypot(ex, ey)
                        if d < BR + POST_R and d > 1e-6:
                            nx, ny = ex / d, ey / d
                            vn = vel[i][0] * nx + vel[i][1] * ny
                            if vn < 0:
                                vel[i][0] -= 2 * vn * nx
                                vel[i][1] -= 2 * vn * ny
                                events.append(("post", t, pos[i][0], -vn / V, i))
                            pos[i][0] = px + nx * (BR + POST_R)
                            pos[i][1] = py + ny * (BR + POST_R)
                    dx, dy = pos[i][0] - CX, pos[i][1] - CY
                    r = math.hypot(dx, dy)
                    if r > R * math.cos(GA) + BR * 0.55:
                        # GOAL
                        mode[i] = "net"
                        tmode[i] = t
                        a_ = dx * cg + dy * sg
                        b_ = -dx * sg + dy * cg
                        va = vel[i][0] * cg + vel[i][1] * sg
                        vb = -vel[i][0] * sg + vel[i][1] * cg
                        netloc[i] = [a_, b_, va, vb]
                        score[i] += 1
                        goals.append((t, minute(t), i, list(score)))
                        events.append(("goal", t, pos[i][0], 1.0, i))
            elif mode[i] == "net":
                nl = netloc[i]
                nl[2] *= math.exp(-7.0 * DT)
                nl[3] *= math.exp(-9.0 * DT)
                nl[0] += nl[2] * DT
                nl[1] += nl[3] * DT
                amax = R * math.cos(GA) + ND - BR - 1
                if nl[0] > amax:
                    nl[0] = amax
                    nl[2] = 0.0
                bm = R * math.sin(GA) - BR + 2
                nl[1] = max(-bm, min(bm, nl[1]))
                if t - tmode[i] > NET_STAY + NET_FADE:
                    mode[i] = "gone"
            elif mode[i] == "gone":
                if t - tmode[i] > RESPAWN:
                    j = 1 - i
                    # respawn off-centre (never on a diameter), away from the other ball
                    ang = rng.random() * 2 * math.pi
                    best = None
                    for tries in range(12):
                        a2 = ang + tries * 0.52
                        px, py = CX + 0.30 * R * math.cos(a2), CY + 0.30 * R * math.sin(a2)
                        dd = math.hypot(px - pos[j][0], py - pos[j][1]) if mode[j] == "play" else 1e9
                        if best is None or dd > best[0]:
                            best = (dd, px, py, a2)
                    if best[0] > 3.2 * BR:
                        _, px, py, a2 = best
                        pos[i] = [px, py]
                        # direction roughly tangential to the spawn radius -> chord, not diameter
                        da = a2 + math.pi / 2 * (1 if rng.random() < 0.5 else -1) + (rng.random() - 0.5) * 1.0
                        vel[i] = [V * math.cos(da), V * math.sin(da)]
                        mode[i] = "play"
                        spawn_t[i] = t
        for i in range(2):
            j = 1 - i
            if mode[i] == "net" and mode[j] == "play":
                a_, b_ = netloc[i][0], netloc[i][1]
                nx_ = CX + a_ * cg - b_ * sg; ny_ = CY + a_ * sg + b_ * cg
                if math.hypot(nx_ - pos[j][0], ny_ - pos[j][1]) < 2 * BR + 4:
                    overlap += 1
        # ball-ball
        if mode[0] == "play" and mode[1] == "play":
            dx, dy = pos[1][0] - pos[0][0], pos[1][1] - pos[0][1]
            d = math.hypot(dx, dy)
            if d < 2 * BR and d > 1e-6:
                nx, ny = dx / d, dy / d
                rv = (vel[1][0] - vel[0][0]) * nx + (vel[1][1] - vel[0][1]) * ny
                if rv < 0:
                    v0n = vel[0][0] * nx + vel[0][1] * ny
                    v1n = vel[1][0] * nx + vel[1][1] * ny
                    vel[0][0] += (v1n - v0n) * nx; vel[0][1] += (v1n - v0n) * ny
                    vel[1][0] += (v0n - v1n) * nx; vel[1][1] += (v0n - v1n) * ny
                    for q in vel:
                        sp = math.hypot(q[0], q[1])
                        if sp < 1e-6:
                            q[0], q[1] = V, 0.0
                        else:
                            q[0] *= V / sp; q[1] *= V / sp
                    events.append(("ball", t, (pos[0][0] + pos[1][0]) / 2, min(1.0, -rv / (2 * V)), -1))
                ov = 2 * BR - d
                pos[0][0] -= nx * ov / 2; pos[0][1] -= ny * ov / 2
                pos[1][0] += nx * ov / 2; pos[1][1] += ny * ov / 2
    # balls absent at full time are put back at the centre (for the final card)
    res = dict(seed=seed, g0=g0, goals=goals, score=score, events=events, graze=graze, overlap=overlap,
               nwall=sum(1 for e in events if e[0] == "wall"),
               nball=sum(1 for e in events if e[0] == "ball"),
               npost=sum(1 for e in events if e[0] == "post"))
    if record:
        res["frames"] = frames
    return res


REALISTIC = {(1, 0), (2, 1), (1, 1), (2, 0), (2, 2), (3, 1), (0, 0), (3, 2)}


def rate(res):
    sc = res["score"]
    key = (max(sc), min(sc))
    if key not in REALISTIC:
        return -1e9, "unrealistic"
    goals = res["goals"]
    mins = [g[1] for g in goals]
    if any(T_HALF - 0.3 <= g[0] <= T_HALF + T_HT + 0.3 for g in goals):
        return -1e9, "goal at HT"
    if any(g[0] > T_FT - 0.4 for g in goals):
        return -1e9, "goal at whistle"
    if res["overlap"]:
        return -1e9, "net overlap"
    if res["nball"] > 22:
        return -1e9, "ball jam"
    if len(goals) < 3:
        return -1e8 + len(goals), "few goals"
    gaps = [b - a for a, b in zip(mins, mins[1:])]
    if mins[0] < 4 or min(gaps) < 9:
        return -1e7, "crowded"
    s = 0.0
    last = goals[-1]
    # late decisive goal
    if 78 <= last[1] <= 89:
        s += 30
        a, b = last[3]
        if a != b:
            prev = list(last[3]); prev[last[2]] -= 1
            if prev[0] == prev[1]:
                s += 25            # winner after being level
        else:
            s += 12               # late equaliser
    # equaliser / comeback somewhere
    lead_changes = 0
    for t, m, i, scr in goals:
        if scr[0] == scr[1]:
            lead_changes += 1
    s += 8 * lead_changes
    if sc[0] != sc[1]:
        s += 10
    if mins[0] < 30:
        s += 6
    if any(22 < m < 45 for m in mins) and any(45 < m < 75 for m in mins):
        s += 6
    s -= 0.5 * res["graze"]
    s += 0.2 * min(res["npost"], 10)
    return s, "ok"


def _search_one(seed):
    res = simulate(seed)
    sc, why = rate(res)
    return (sc, seed, res["score"], [(round(g[1]), g[2]) for g in res["goals"]], res["graze"], res["npost"], res["nball"], why)


def search(n):
    with Pool(os.cpu_count()) as p:
        out = p.map(_search_one, range(n), chunksize=8)
    from collections import Counter
    print("goal-count distribution:", sorted(Counter(sum(o[2]) for o in out).items()))
    out.sort(key=lambda o: -o[0])
    for o in out[:15]:
        print(o)


# ---------------------------------------------------------------- rendering
_FONTS = {}


def font(sz, bold=True):
    k = (sz, bold)
    if k not in _FONTS:
        _FONTS[k] = ImageFont.truetype(FONT_B if bold else FONT_SB, sz)
    return _FONTS[k]


_SPRITES = {}


def ball_sprite(i, rad_px):
    """Logo ball, rad_px = radius in canvas pixels (2x). Built at 4x then reduced."""
    key = (i, rad_px)
    if key in _SPRITES:
        return _SPRITES[key]
    tm = TEAMS[i]
    U = 4
    D = int(round(2 * rad_px)) + 2
    big = D * U
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    c = big / 2
    rr = rad_px * U
    dr.ellipse([c - rr, c - rr, c + rr, c + rr], fill=tm["ball"] + (255,))
    logo = Image.open(os.path.join(ROOT, "assets", "logos", tm["logo"])).convert("RGBA")
    logo = logo.crop(logo.getbbox())
    frac = 0.74 if i == 0 else 0.70
    lh = 2 * rr * frac
    lw = lh * logo.width / logo.height
    logo = logo.resize((int(lw), int(lh)), Image.LANCZOS)
    im.alpha_composite(logo, (int(c - lw / 2), int(c - lh / 2)))
    rimw = 2.4 * S * U / 2 * 1.0
    dr = ImageDraw.Draw(im)
    dr.ellipse([c - rr, c - rr, c + rr, c + rr], outline=tm["rim"] + (255,), width=int(round(2.2 * S * U / 2)))
    # clean circular mask
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse([c - rr, c - rr, c + rr, c + rr], fill=255)
    a = Image.fromarray(np.minimum(np.array(im.getchannel("A")), np.array(mask)))
    im.putalpha(a)
    im = im.resize((D, D), Image.LANCZOS)
    _SPRITES[key] = im
    return im


def paste_ball(canvas, i, x, y, rad, alpha=1.0):
    if alpha <= 0.01 or rad < 2:
        return
    sp = ball_sprite(i, int(round(rad * S)))
    if alpha < 0.999:
        sp = sp.copy()
        a = np.array(sp.getchannel("A"), dtype=np.float32) * alpha
        sp.putalpha(Image.fromarray(a.astype(np.uint8)))
    canvas.alpha_composite(sp, (int(round(x * S - sp.width / 2)), int(round(y * S - sp.height / 2))))


def text_c(dr, xy, s, sz, fill, bold=True, anchor="mm"):
    dr.text((xy[0] * S, xy[1] * S), s, font=font(int(sz * S), bold), fill=fill, anchor=anchor)


def text_alpha(canvas, xy, s, sz, col, alpha, bold=True):
    if alpha <= 0.01:
        return
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((xy[0] * S, xy[1] * S), s, font=font(int(sz * S), bold),
                               fill=col + (int(255 * alpha),), anchor="mm")
    canvas.alpha_composite(layer)


def loc2img(a, b, g):
    cg, sg = math.cos(g), math.sin(g)
    return ((CX + a * cg - b * sg) * S, (CY + a * sg + b * cg) * S)


def draw_net(dr, g, bulge):
    a0 = R * math.cos(GA)
    hw = R * math.sin(GA)
    a1 = a0 + ND

    def P(a, b):
        f = (a - a0) / ND
        a2 = a + bulge * f * (1 - (b / hw) ** 2)
        return loc2img(a2, b, g)

    grid = (120, 120, 132)
    frame = (205, 205, 212)
    nb = 24
    # lines parallel to the back (constant depth)
    for f in (1 / 3, 2 / 3):
        a = a0 + f * ND
        pts = [P(a, -hw + 2 * hw * k / nb) for k in range(nb + 1)]
        dr.line(pts, fill=grid, width=int(1.5 * S))
    # lines parallel to the sides
    for f in (-0.5, 0.0, 0.5):
        b = f * hw
        pts = [P(a0 + ND * k / 8, b) for k in range(9)]
        dr.line(pts, fill=grid, width=int(1.5 * S))
    # frame: sides + back
    for sgn in (-1, 1):
        dr.line([P(a0 + ND * k / 8, sgn * hw) for k in range(9)], fill=frame, width=int(2 * S))
    dr.line([P(a1, -hw + 2 * hw * k / nb) for k in range(nb + 1)], fill=frame, width=int(2 * S))


def draw_ring(dr, g):
    w = 3 * S               # 3 px final ring stroke
    rb = R * S + w / 2
    st = math.degrees(g + GA)
    en = math.degrees(g - GA) + 360
    dr.arc([CX * S - rb, CY * S - rb, CX * S + rb, CY * S + rb], st, en, fill=(240, 240, 240), width=w)
    for sgn in (-1, 1):
        px = (CX + R * math.cos(g + sgn * GA)) * S
        py = (CY + R * math.sin(g + sgn * GA)) * S
        pr = POST_R * S
        dr.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(255, 255, 255))


def draw_digits(dr, cx, cy, s, sz, fill, cell):
    n = len(s)
    x0 = cx - cell * n / 2
    for k, ch in enumerate(s):
        w = cell * (0.55 if ch == "'" else 1.0)
        text_c(dr, (x0 + cell * k + cell / 2, cy), ch, sz, fill)


def draw_hud(canvas, t, score, goals, ft):
    dr = ImageDraw.Draw(canvas)
    # hook
    text_c(dr, (540, 272), "LIVERPOOL vs ARSENAL", 66, (255, 255, 255))
    text_c(dr, (540, 346), "WHO WINS TOMORROW?", 46, ACCENT)
    # scoreboard pill
    y = 438
    x0, x1, hh = 186, 894, 40
    dr.rounded_rectangle([x0 * S, (y - hh) * S, x1 * S, (y + hh) * S], radius=hh * S, fill=(22, 22, 28),
                         outline=(58, 58, 68), width=int(2 * S))
    paste_ball(canvas, 0, 236, y, 22)
    paste_ball(canvas, 1, 684, y, 22)
    dr = ImageDraw.Draw(canvas)
    text_c(dr, (312, y + 1), "LIV", 38, (235, 235, 240))
    text_c(dr, (608, y + 1), "ARS", 38, (235, 235, 240))
    # digits with pop
    for i, cx in ((0, 410), (1, 510)):
        sc = 1.0
        for gt, gm, gi, gs in goals:
            if gi == i and 0 <= t - gt < 0.35:
                sc = 1.0 + 0.28 * (1 - (t - gt) / 0.35)
        text_c(dr, (cx, y + 1), str(score[i]), int(50 * sc), (255, 255, 255))
    text_c(dr, (460, y - 1), "-", 44, (150, 150, 160))
    dr.line([(736 * S, (y - 22) * S), (736 * S, (y + 22) * S)], fill=(70, 70, 82), width=int(2 * S))
    if ft:
        text_c(dr, (815, y + 1), "FT", 38, ACCENT)
    elif T_HALF <= t < T_HALF + T_HT:
        text_c(dr, (815, y + 1), "HT", 38, ACCENT)
    else:
        m = int(minute(t))
        s = f"{m}'"
        cell = 27
        xs = 815 - (len(s) - 1) * cell / 2 - 6
        for k, ch in enumerate(s[:-1]):
            text_c(dr, (xs + k * cell + 5, y + 1), ch, 40, (255, 255, 255))
        text_c(dr, (xs + (len(s) - 1) * cell - 2, y + 1), "'", 40, (255, 255, 255))


def render_frame(sim, t):
    frames = sim["frames"]
    fi = min(int(round(t * FPS)), len(frames) - 1)
    fr = frames[fi]
    ft = t >= T_FT - 1e-9
    canvas = Image.new("RGBA", (W * S, H * S), BG + (255,))
    goals = [g for g in sim["goals"] if g[0] <= t]
    # GOAL text (behind everything)
    for gt, gm, gi, gs in goals:
        dt = t - gt
        if 0 <= dt < 1.5:
            al = clamp(dt / 0.08) * (1 - clamp((dt - 1.05) / 0.45))
            text_alpha(canvas, (CX, CY - 24), "GOAL", 132, (255, 255, 255), al)
            text_alpha(canvas, (CX, CY + 66), TEAMS[gi]["name"], 44, ACCENT, al)
    g = fr["g"]
    # net bulge from last goal
    bulge = 0.0
    for gt, gm, gi, gs in goals:
        dt = t - gt
        if 0 <= dt < 1.2:
            bulge = 13.0 * math.exp(-3.5 * dt) * math.cos(9.0 * dt) * clamp(dt / 0.05)
    # balls resting in net (drawn under the net lines)
    fo = 1.0 - clamp((t - T_FT) / 0.35) if ft else 1.0
    for i, b in enumerate(fr["balls"]):
        if b["mode"] == "net":
            paste_ball(canvas, i, b["x"], b["y"], BR, b["alpha"] * fo)
    dr = ImageDraw.Draw(canvas)
    draw_net(dr, g, bulge)
    draw_ring(dr, g)
    for i, b in enumerate(fr["balls"]):
        if b["mode"] == "play":
            paste_ball(canvas, i, b["x"], b["y"], BR * b["scale"], b["alpha"] * fo)
    if ft:
        k = t - T_FT
        sc = fr["score"]
        al = clamp((k - 0.45) / 0.35)
        sz = 1.45 * (0.85 + 0.15 * ease_out((k - 0.45) / 0.4))
        if sc[0] != sc[1]:
            w = 0 if sc[0] > sc[1] else 1
            paste_ball(canvas, w, CX, CY - 60, BR * sz, al)
            text_alpha(canvas, (CX, CY + 66), TEAMS[w]["name"] + " WIN", 64, (255, 255, 255), al)
        else:
            paste_ball(canvas, 0, CX - 80, CY - 60, BR * sz, al)
            paste_ball(canvas, 1, CX + 80, CY - 60, BR * sz, al)
            text_alpha(canvas, (CX, CY + 66), "DRAW", 64, (255, 255, 255), al)
        text_alpha(canvas, (CX, CY - 175), "FULL TIME", 40, ACCENT, al)
    draw_hud(canvas, min(t, T_FT), fr["score"], goals, ft)
    return canvas.convert("RGB").resize((W, H), Image.LANCZOS)


_SIM = None


def _render_idx(fi):
    return render_frame(_SIM, fi / FPS).tobytes()


def render_video(sim, out_silent):
    global _SIM
    _SIM = sim
    n = int(round(T_END * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_silent]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for k, buf in enumerate(pool.imap(_render_idx, range(n), chunksize=6)):
            p.stdin.write(buf)
            if k % 300 == 0:
                print("frame", k, "/", n, flush=True)
    p.stdin.close()
    p.wait()


# ---------------------------------------------------------------- audio (foley only, no notes)
def make_audio(sim, path, seed=7):
    from scipy.signal import butter, sosfilt, fftconvolve
    rng = np.random.default_rng(seed)
    N = int(T_END * SR) + SR
    L = np.zeros(N); Rr = np.zeros(N)

    def bp(x, lo, hi, order=2):
        return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)

    def lp(x, f, order=2):
        return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)

    def tt(d):
        return np.arange(int(d * SR)) / SR

    def add(sig, t0, gain=1.0, x=CX):
        i0 = int(t0 * SR)
        if i0 >= N:
            return
        sig = sig[: N - i0] * gain
        pan = clamp((x - CX) / (W / 2), -1, 1) * 0.35
        th = (pan + 1) * math.pi / 4
        L[i0:i0 + len(sig)] += sig * math.cos(th)
        Rr[i0:i0 + len(sig)] += sig * math.sin(th)

    def st(semi):
        return 2 ** (semi / 12)

    TOCK = [(1150, 190), (1450, 215), (950, 170), (1300, 240), (1050, 205)]

    def tock(var):
        c, f0 = TOCK[var % len(TOCK)]
        c *= st(rng.uniform(-3, 3)); f0 *= st(rng.uniform(-3, 3))
        t = tt(0.14)
        noise = rng.standard_normal(len(t))
        click = bp(noise, c * 0.6, c * 1.5) * np.exp(-t / rng.uniform(0.007, 0.013))
        f = f0 * (1 + 0.35 * np.exp(-t / 0.01))
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / rng.uniform(0.028, 0.045))
        return lp(0.5 * click + 0.8 * body, 4500)

    def thud():
        t = tt(0.22)
        f = 105 * st(rng.uniform(-3, 3)) * (1 + 0.5 * np.exp(-t / 0.012))
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.065)
        n = rng.standard_normal(len(t))
        felt = lp(n, 700) * np.exp(-t / 0.018)
        clack = bp(n, 1800, 3200) * np.exp(-t / 0.005)
        return 1.0 * body + 0.9 * felt + 0.18 * clack

    def clank():
        t = tt(0.2)
        f0 = 560 * st(rng.uniform(-3, 3))
        s = np.zeros(len(t))
        for r_, a_, d_ in ((1, 1, 0.08), (2.31, 0.55, 0.055), (4.18, 0.3, 0.04), (6.07, 0.15, 0.025)):
            s += a_ * np.sin(2 * np.pi * f0 * r_ * t + rng.random() * 6) * np.exp(-t / d_)
        n = rng.standard_normal(len(t))
        s += 0.6 * bp(n, 2000, 5000) * np.exp(-t / 0.004)
        return lp(s, 5000) * 0.6

    def crowd_noise(d):
        t = tt(d)
        out = np.zeros(len(t))
        for lo, hi in ((250, 700), (500, 1300), (900, 2600)):
            n = bp(rng.standard_normal(len(t)), lo, hi)
            am = 0.7 + 0.3 * np.sin(2 * np.pi * rng.uniform(3, 7) * t + rng.random() * 6)
            out += n * am
        return out / 3

    def ooh():
        d = 1.2
        t = tt(d)
        env = np.clip(t / 0.25, 0, 1) * np.exp(-np.clip(t - 0.25, 0, None) / 0.35)
        n = bp(rng.standard_normal(len(t)), 280, 900)
        return n * env

    def roar():
        d = 3.4
        t = tt(d)
        env = np.clip(t / 0.3, 0, 1) * np.where(t < 1.2, 1.0, np.exp(-(t - 1.2) / 0.7))
        return crowd_noise(d) * env

    def swish():
        t = tt(0.5)
        n = rng.standard_normal(len(t))
        env = np.clip(t / 0.015, 0, 1) * np.exp(-t / 0.16)
        s = bp(n, 1400, 5500) * env
        f = 75 * (1 + 0.4 * np.exp(-t / 0.02))
        s += 1.2 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.09)
        return s

    def whistle(d):
        t = tt(d)
        f0 = 2850
        f = f0 + 85 * np.sin(2 * np.pi * 27 * t)
        tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.72 + 0.28 * np.sin(2 * np.pi * 27 * t))
        breath = bp(rng.standard_normal(len(t)), 2300, 3500) * 0.35
        env = np.clip(t / 0.015, 0, 1) * np.clip((d - t) / 0.05, 0, 1)
        return lp((tone + breath) * env, 6000)

    # crowd bed
    bed = crowd_noise(T_END + 0.5)
    tb = np.arange(len(bed)) / SR
    slow = 0.75 + 0.25 * np.sin(2 * np.pi * 0.21 * tb + 1) * np.sin(2 * np.pi * 0.13 * tb)
    bedenv = np.clip(tb / 0.6, 0, 1) * np.clip((T_END - tb) / 1.5, 0, 1)
    add(bed * slow * bedenv, 0.0, 0.10)

    # physics events, merged per frame
    evs = sorted(sim["events"], key=lambda e: e[1])
    lastt = -1.0
    var = 0
    groups = {}
    for e in evs:
        fidx = int(e[1] * FPS)
        groups.setdefault((fidx, e[0] if e[0] != "wall" else "wall"), []).append(e)
    stats = dict(sounds=0)
    sound_times = []
    for (fidx, kind), es in sorted(groups.items(), key=lambda kv: kv[0][0]):
        e = max(es, key=lambda q: q[3])
        t0 = e[1]
        boost = 1.15 if len(es) > 1 else 1.0
        dense = 0.8 if t0 - lastt < 0.08 else 1.0
        if kind == "wall":
            add(tock(var), t0, 0.42 * (0.6 + 0.4 * e[3]) * rng.uniform(0.75, 1.0) * boost * dense, e[2])
            var += 1 + int(rng.integers(0, 2))
        elif kind == "ball":
            add(thud(), t0, 0.62 * (0.7 + 0.3 * e[3]) * boost, e[2])
        elif kind == "post":
            add(clank(), t0, 0.5, e[2])
            add(ooh(), t0 + 0.08, 0.22)
        elif kind == "goal":
            add(swish(), t0, 0.55, e[2])
            add(roar(), t0 + 0.05, 0.42)
        lastt = t0
        sound_times.append(t0)
    # whistles
    add(whistle(0.45), 0.02, 0.16)
    add(whistle(0.22), T_HALF, 0.16); add(whistle(0.22), T_HALF + 0.34, 0.16)
    add(whistle(0.22), T_FT, 0.17); add(whistle(0.22), T_FT + 0.34, 0.17); add(whistle(0.8), T_FT + 0.68, 0.17)
    add(roar(), T_FT + 0.8, 0.30)
    # light room reverb
    ir_t = np.arange(int(0.45 * SR)) / SR
    ir = rng.standard_normal(len(ir_t)) * np.exp(-ir_t / 0.11)
    ir = lp(ir, 3500)
    ir /= np.sqrt(np.sum(ir ** 2))
    L2 = L + 0.11 * fftconvolve(L, ir)[:N]
    R2 = Rr + 0.11 * fftconvolve(Rr, ir)[:N]
    x = np.stack([L2, R2], 1)[: int(T_END * SR)]
    x = np.tanh(x * 1.2) / 1.2
    x *= 0.6 / np.max(np.abs(x))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes((x * 32767).astype(np.int16).tobytes())
    st_ = np.array(sound_times)
    per_s = np.histogram(st_, bins=np.arange(0, T_END + 1))[0]
    print("audio: physics sounds", len(st_), "max/s", per_s.max(), "mean/s", round(per_s.mean(), 2))


def loudnorm(wav_in, wav_out):
    cmd = ["ffmpeg", "-hide_banner", "-y", "-i", wav_in, "-af",
           "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True).stderr
    js = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    af = ("loudnorm=I=-14:TP=-1.5:LRA=11:linear=true:measured_I={input_i}:measured_TP={input_tp}:"
          "measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={target_offset}").format(**js)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", wav_in, "-af", af,
                    "-ar", str(SR), wav_out], check=True)


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--frames", type=str, default="")
    ap.add_argument("--outdir", type=str, default="keys")
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()
    if args.search:
        search(args.search)
        sys.exit()
    res = simulate(args.seed, record=bool(args.frames or args.out))
    print("score", res["score"], "goals", [(round(g[1], 1), TEAMS[g[2]]["code"]) for g in res["goals"]],
          "walls", res["nwall"], "ballball", res["nball"], "posts", res["npost"], "graze", res["graze"])
    if args.frames:
        os.makedirs(args.outdir, exist_ok=True)
        for s in args.frames.split(","):
            tf = float(s)
            render_frame(res, tf).save(os.path.join(args.outdir, f"f_{tf:05.2f}.png"))
    if args.out:
        base = os.path.splitext(args.out)[0]
        make_audio(res, base + "_raw.wav")
        loudnorm(base + "_raw.wav", base + "_ln.wav")
        render_video(res, base + "_silent.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", base + "_silent.mp4", "-i", base + "_ln.wav",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                        args.out], check=True)
        print("wrote", args.out)
