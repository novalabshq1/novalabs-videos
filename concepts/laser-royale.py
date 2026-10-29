#!/usr/bin/env python3
"""Laser Royale — 8 flag balls in a circle. Every time a ball hits the edge it shoots a new laser
from itself to that point. A ball that touches another team's laser breaks it. No lasers left = out.
The game speeds up (x1.0 -> x2.0). Last ball standing wins.

Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS down to 1080x1920, 60 fps.
Audio fully synthesized, -1 dBFS.

    python3.13 laser-royale.py --sim [--seed N]
    python3.13 laser-royale.py --frames 0,0.2,0.4,0.6,0.8,0.97 --outdir keys/
    python3.13 laser-royale.py --out video.mp4
"""
import argparse, math, os, subprocess, tempfile, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

W, H, FPS, S = 1080, 1920, 60, 2
SR = 44100
SUB = 8
DT = 1.0 / (FPS * SUB)

CX, CY, RA = 540.0, 1010.0, 400.0        # arena
BR = 46.0                                 # ball radius
V0 = 560.0
START_LASERS = 0
START_ANG = [(-0.55, 1.35), (0.55, -1.35)]
START_SPAN = 0.6
MAX_LASERS = 5
LASER_HP = 2
ARM_AT = 3                                # a ball can only be knocked out once it has drawn 3 lasers
CAP_T0, CAP_T1, CAP_END = 14.0, 38.0, 1


def laser_cap(t):
    if t <= CAP_T0:
        return MAX_LASERS
    f = min(1.0, (t - CAP_T0) / (CAP_T1 - CAP_T0))
    return int(round(MAX_LASERS + (CAP_END - MAX_LASERS) * f))
GRACE = 0.15                              # a fresh laser can't be cut for this long
HOLD = 4.0                                # seconds of payoff after the last elimination

TEAMS = [  # name, laser colour
    ("CANADA", (255, 64, 86)),
    ("USA", (70, 136, 255)),
    ("ARGENTINA", (96, 214, 255)),
    ("BRAZIL", (255, 214, 60)),
    ("ALGERIA", (44, 228, 122)),
    ("NETHERLANDS", (255, 140, 44)),
    ("JAPAN", (240, 240, 255)),
    ("FRANCE", (172, 118, 255)),
]
N = len(TEAMS)


def speed_mult(t):
    return 1.0 + min(1.0, t / 30.0)


def seg_dist(p, a, b):
    ab = b - a
    tt = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-9), 0, 1)
    return np.linalg.norm(p - (a + ab * tt)), tt


def simulate(seed, tmax=80.0):
    rng = np.random.default_rng(seed)
    ang0 = rng.random() * 2 * math.pi
    pos = np.array([[CX + 235 * math.cos(ang0 + i * 2 * math.pi / N), CY + 235 * math.sin(ang0 + i * 2 * math.pi / N)]
                    for i in range(N)])
    dirs = rng.random(N) * 2 * math.pi
    vel = np.stack([np.cos(dirs), np.sin(dirs)], 1) * V0
    alive = [True] * N
    armed = [False] * N
    drawn = [0] * N
    lasers = []          # chords: dict(owner, x0, y0, x1, y1, born, dead, ghost=set of balls passing through)
    anchor = np.zeros((N, 2))
    for i in range(N):
        a = ang0 + i * 2 * math.pi / N
        pts = [(CX + RA * math.cos(a + d), CY + RA * math.sin(a + d)) for d in (-START_SPAN, START_SPAN)]
        for k in range(START_LASERS):
            p0 = (CX + RA * math.cos(a + START_ANG[k][0]), CY + RA * math.sin(a + START_ANG[k][0]))
            p1 = (CX + RA * math.cos(a + START_ANG[k][1]), CY + RA * math.sin(a + START_ANG[k][1]))
            lasers.append(dict(owner=i, x0=p0[0], y0=p0[1], x1=p1[0], y1=p1[1], born=-1.0, dead=None, ghost=set()))
        anchor[i] = (CX + RA * math.cos(a), CY + RA * math.sin(a))
    for L in lasers:
        L["ghost"] = {j for j in range(N) if seg_dist(pos[j], np.array((L["x0"], L["y0"])), np.array((L["x1"], L["y1"])))[0] < BR + 2}
    events = []
    frames = []
    t = 0.0
    end_t = None
    winner = None
    last_bb = {}
    C = np.array((CX, CY))
    while True:
        for _ in range(SUB):
            sp = V0 * speed_mult(t)
            for i in range(N):
                if alive[i]:
                    vel[i] *= sp / max(np.linalg.norm(vel[i]), 1e-6)
            pos += vel * DT * np.array(alive)[:, None]
            # arena edge -> new laser
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
                        th = rng.normal(0, 0.05)
                        c, s_ = math.cos(th), math.sin(th)
                        vel[i] = np.array([c * vel[i, 0] - s_ * vel[i, 1], s_ * vel[i, 0] + c * vel[i, 1]])
                        hit = C + nrm * RA
                        a0 = anchor[i].copy()
                        anchor[i] = hit
                        if np.linalg.norm(hit - a0) < 3 * BR:       # too short to be a laser
                            events.append((t, "edge", (i, *hit)))
                            continue
                        mine = [L for L in lasers if L["owner"] == i and L["dead"] is None]
                        mine.sort(key=lambda L: L["born"])
                        for old in mine[:max(0, len(mine) - laser_cap(t) + 1)]:
                            old["dead"] = t
                            old["why"] = "old"
                        L = dict(owner=i, x0=a0[0], y0=a0[1], x1=hit[0], y1=hit[1], born=t, dead=None, hp=LASER_HP, hits=[])
                        L["ghost"] = {j for j in range(N) if alive[j] and
                                      seg_dist(pos[j], a0, hit)[0] < BR + 2}
                        lasers.append(L)
                        drawn[i] += 1
                        armed[i] = drawn[i] >= ARM_AT
                        events.append((t, "laser", (i, *hit)))
            # ball-ball
            for i in range(N):
                for j in range(i + 1, N):
                    if not (alive[i] and alive[j]):
                        continue
                    d = pos[j] - pos[i]
                    r = np.linalg.norm(d)
                    if 1e-6 < r < 2 * BR:
                        nrm = d / r
                        ov = 2 * BR - r
                        pos[i] -= nrm * ov / 2
                        pos[j] += nrm * ov / 2
                        rv = np.dot(vel[j] - vel[i], nrm)
                        if rv < 0:
                            vel[i] += rv * nrm
                            vel[j] -= rv * nrm
                            if t - last_bb.get((i, j), -9) > 0.12:
                                events.append((t, "bump", (i, j, *(pos[i] + nrm * BR))))
                            last_bb[(i, j)] = t
            # enemy lasers are solid: bounce off and break them
            for L in lasers:
                if L["dead"] is not None:
                    continue
                a = np.array((L["x0"], L["y0"]))
                b = np.array((L["x1"], L["y1"]))
                for j in range(N):
                    if not alive[j] or j == L["owner"]:
                        continue
                    dd, tt = seg_dist(pos[j], a, b)
                    if j in L["ghost"]:
                        if dd > BR + 2:
                            L["ghost"].discard(j)
                        continue
                    if dd < BR:
                        q = a + (b - a) * tt
                        nrm = (pos[j] - q) / max(dd, 1e-6)
                        vn = np.dot(vel[j], nrm)
                        if vn < 0:
                            vel[j] -= 2 * vn * nrm
                        pos[j] = q + nrm * BR
                        L["hp"] -= 1
                        L["hits"].append((t, *q))
                        if L["hp"] > 0:
                            L["ghost"].add(j)
                            events.append((t, "crack", (L["owner"], j, *q)))
                            break
                        L["dead"] = t
                        L["why"] = "cut"
                        L["cutby"] = j
                        L["cx"], L["cy"] = q
                        events.append((t, "cut", (L["owner"], j, *q)))
                        break
            for i in range(N):
                if alive[i] and armed[i] and not any(L["owner"] == i and L["dead"] is None for L in lasers):
                    alive[i] = False
                    events.append((t, "out", (i, *pos[i])))
                    for L in lasers:
                        pass
                    if sum(alive) == 1:
                        end_t = t
                        winner = alive.index(True)
            t += DT
        frames.append(dict(t=t, pos=pos.copy(), vel=vel.copy(), alive=list(alive), anchor=anchor.copy()))
        if end_t is not None and t >= end_t + 0.02:
            break
        if t > tmax:
            break
    return dict(frames=frames, lasers=lasers, events=events, end_t=end_t, winner=winner, seed=seed)


def summary(sim):
    outs = [e[0] for e in sim["events"] if e[1] == "out"]
    n_wall = sum(1 for e in sim["events"] if e[1] == "laser")
    n_cut = sum(1 for e in sim["events"] if e[1] == "cut")
    return outs, n_wall, n_cut



# ---------------------------------------------------------------- flags & sprites
FONT_PATHS = ("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
GOLD = (255, 204, 84)
SEED = 18


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


LEAF_R = [(0, -0.50), (0.07, -0.37), (0.15, -0.41), (0.12, -0.13), (0.28, -0.30), (0.31, -0.22), (0.46, -0.25),
          (0.41, -0.10), (0.47, -0.07), (0.26, 0.11), (0.30, 0.20), (0.04, 0.16), (0.035, 0.42)]
LEAF = LEAF_R + [(-x, y) for x, y in reversed(LEAF_R[1:])]


def star_pts(cx, cy, r, rot=-math.pi / 2):
    pts = []
    for k in range(10):
        rr = r if k % 2 == 0 else r * 0.40
        a = rot + k * math.pi / 5
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def flag_img(name, n):
    """Square flag artwork (drawn at 4x, downsampled) meant to be wrapped on a ball."""
    m = n * 4
    im = Image.new("RGB", (m, m), (255, 255, 255))
    d = ImageDraw.Draw(im)
    U = lambda u: u * m
    if name == "CANADA":
        d.rectangle([0, 0, U(0.25), m], fill=(216, 6, 33))
        d.rectangle([U(0.75), 0, m, m], fill=(216, 6, 33))
        d.polygon([(U(0.5 + x * 0.48), U(0.5 + y * 0.48)) for x, y in LEAF], fill=(216, 6, 33))
    elif name == "USA":
        for k in range(13):
            d.rectangle([0, U(k / 13), m, U((k + 1) / 13)], fill=(178, 34, 52) if k % 2 == 0 else (255, 255, 255))
        d.rectangle([0, 0, U(0.52), U(7 / 13)], fill=(60, 59, 110))
        for r in range(5):
            for c in range(5 if r % 2 == 0 else 4):
                x = U(0.07 + c * 0.095 + (0.0475 if r % 2 else 0))
                y = U(0.065 + r * 0.098)
                d.polygon(star_pts(x, y, U(0.028)), fill=(255, 255, 255))
    elif name == "ARGENTINA":
        d.rectangle([0, 0, m, U(1 / 3)], fill=(116, 172, 223))
        d.rectangle([0, U(2 / 3), m, m], fill=(116, 172, 223))
        for k in range(16):
            a = k * math.pi / 8
            d.polygon([(U(0.5 + 0.19 * math.cos(a)), U(0.5 + 0.19 * math.sin(a))),
                       (U(0.5 + 0.09 * math.cos(a + 0.22)), U(0.5 + 0.09 * math.sin(a + 0.22))),
                       (U(0.5 + 0.09 * math.cos(a - 0.22)), U(0.5 + 0.09 * math.sin(a - 0.22)))], fill=(246, 180, 14))
        d.ellipse([U(0.4), U(0.4), U(0.6), U(0.6)], fill=(246, 180, 14))
    elif name == "BRAZIL":
        d.rectangle([0, 0, m, m], fill=(0, 156, 59))
        d.polygon([(U(0.05), U(0.5)), (U(0.5), U(0.13)), (U(0.95), U(0.5)), (U(0.5), U(0.87))], fill=(255, 223, 0))
        d.ellipse([U(0.29), U(0.29), U(0.71), U(0.71)], fill=(0, 39, 118))
        mask = Image.new("L", (m, m), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse([U(0.12), U(0.40), U(1.02), U(1.30)], outline=255, width=int(U(0.035)))
        cm = Image.new("L", (m, m), 0)
        ImageDraw.Draw(cm).ellipse([U(0.29), U(0.29), U(0.71), U(0.71)], fill=255)
        im.paste((255, 255, 255), (0, 0), ImageChops.multiply(mask, cm))
    elif name == "ALGERIA":
        d.rectangle([0, 0, U(0.5), m], fill=(0, 102, 51))
        mask = Image.new("L", (m, m), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse([U(0.5 - 0.25), U(0.25), U(0.75), U(0.75)], fill=255)
        md.ellipse([U(0.565 - 0.20), U(0.30), U(0.565 + 0.20), U(0.70)], fill=0)
        md.polygon(star_pts(U(0.60), U(0.5), U(0.115), rot=math.pi), fill=255)
        im.paste((210, 16, 52), (0, 0), mask)
    elif name == "NETHERLANDS":
        d.rectangle([0, 0, m, U(1 / 3)], fill=(174, 28, 40))
        d.rectangle([0, U(2 / 3), m, m], fill=(33, 70, 139))
    elif name == "JAPAN":
        d.rectangle([0, 0, m, m], fill=(246, 246, 248))
        d.ellipse([U(0.2), U(0.2), U(0.8), U(0.8)], fill=(188, 0, 45))
    elif name == "FRANCE":
        d.rectangle([0, 0, U(1 / 3), m], fill=(0, 85, 164))
        d.rectangle([U(2 / 3), 0, m, m], fill=(239, 65, 53))
    return im.resize((n, n), Image.LANCZOS)


FLAG_COLS = {"CANADA": [(216, 6, 33), (255, 255, 255)], "USA": [(178, 34, 52), (255, 255, 255), (60, 59, 110)],
             "ARGENTINA": [(116, 172, 223), (255, 255, 255), (246, 180, 14)],
             "BRAZIL": [(0, 156, 59), (255, 223, 0), (0, 39, 118)], "ALGERIA": [(0, 102, 51), (255, 255, 255), (210, 16, 52)],
             "NETHERLANDS": [(174, 28, 40), (255, 255, 255), (33, 70, 139)], "JAPAN": [(246, 246, 248), (188, 0, 45)],
             "FRANCE": [(0, 85, 164), (255, 255, 255), (239, 65, 53)]}

_sprite_cache = {}


def ball_sprite(team, r_px, flash=0.0):
    """RGB + alpha mask of a shaded flag ball with a neon rim, radius r_px (supersampled px)."""
    key = (team, int(r_px), round(flash, 2))
    if key in _sprite_cache:
        return _sprite_cache[key]
    name, col = TEAMS[team]
    rim = max(4, r_px * 0.09)
    R = r_px
    n = int(2 * (R + rim) + 4)
    c = n / 2
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    dx, dy = (xx - c) / R, (yy - c) / R
    d = np.sqrt(dx ** 2 + dy ** 2)
    inner = int(2 * R * 0.98)
    flag = np.asarray(flag_img(name, inner), np.float32)
    canvas = np.zeros((n, n, 3), np.float32)
    o = int(round(c - inner / 2))
    canvas[o:o + inner, o:o + inner] = flag
    nz = np.sqrt(np.clip(1 - d ** 2, 0, 1))
    lx, ly, lz = -0.42, -0.55, 0.72
    lam = np.clip(dx * lx + dy * ly + nz * lz, 0, 1)
    shade = 0.50 + 0.62 * lam
    spec = np.exp(-(((dx + 0.36) ** 2 + (dy + 0.42) ** 2) / 0.035)) * 0.75
    body = canvas * shade[:, :, None] + 255 * spec[:, :, None]
    body = body * (1 - 0.30 * np.clip((d - 0.75) / 0.25, 0, 1) ** 2)[:, :, None]
    # neon rim
    rd = (d * R - R - rim * 0.45) / (rim * 0.55)
    rim_a = np.clip(1 - np.abs(rd), 0, 1) ** 0.6
    colv = np.array(col, np.float32)
    rimc = colv * 0.85 + 255 * 0.15
    a_body = np.clip((1 - d) * R + 0.5, 0, 1)
    out = body * a_body[:, :, None] + rimc[None, None, :] * (rim_a * (1 - a_body))[:, :, None]
    alpha = np.maximum(a_body, rim_a)
    # thin bright line where rim meets body
    edge = np.exp(-((d - 1.0) * R / 1.6) ** 2) * 0.55
    out = out + rimc[None, None, :] * edge[:, :, None] * 0.6
    if flash > 0:
        out = out * (1 - flash) + 255 * flash
    rgb = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    m = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8))
    _sprite_cache[key] = (rgb, m)
    return rgb, m


def soft_disc(r, power=2.0):
    n = int(2 * r) + 2
    yy, xx = np.mgrid[0:n, 0:n] - n / 2
    d = np.sqrt(xx ** 2 + yy ** 2) / r
    return np.clip(1 - d, 0, 1) ** power


# ---------------------------------------------------------------- timeline (slow motion around the final knock-out)
SLOW = 0.3
T_SKIP = 1.25                              # video starts once the first lasers are drawn


def build_timeline(sim):
    e = sim["end_t"]
    s0, s1 = e - 0.40, e + 0.10
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
    total = v_end + HOLD + 2.2
    return st_of, vt_of, v_end, total


# ---------------------------------------------------------------- static layers
SIM = None
STATIC = {}


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


def make_bg():
    Hs, Ws = H * S, W * S
    y = np.linspace(0, 1, Hs, dtype=np.float32)[:, None]
    x = np.linspace(-1, 1, Ws, dtype=np.float32)[None, :]
    top, bot = np.array([14, 15, 28.], np.float32), np.array([5, 6, 11.], np.float32)
    img = top[None, None, :] * (1 - y[:, :, None]) + bot[None, None, :] * y[:, :, None]
    yy = (y * 2 - 1)
    vig = 1 - 0.30 * np.clip(x ** 2 * 0.7 + yy ** 2 * 0.45, 0, 1)
    img = img * vig[:, :, None]
    # arena floor: slightly lifted disc + faint inner glow
    py = (np.arange(Hs, dtype=np.float32)[:, None] + 0.5) / S
    px = (np.arange(Ws, dtype=np.float32)[None, :] + 0.5) / S
    r = np.sqrt((px - CX) ** 2 + (py - CY) ** 2)
    inside = np.clip((RA - r) * S / 2 + 0.5, 0, 1)
    floor = np.array([17, 19, 34.], np.float32) * (0.75 + 0.25 * np.exp(-(r / RA) ** 2 * 1.2))[:, :, None]
    img = img * (1 - inside[:, :, None]) + floor * inside[:, :, None]
    # ring: crisp line + soft halo
    ring = np.exp(-((r - RA) / 3.2) ** 2)
    halo = np.exp(-((r - RA) / 22) ** 2) * 0.22
    img += np.array([150, 162, 210.], np.float32)[None, None, :] * (ring * 0.85 + halo)[:, :, None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def init_static():
    STATIC["bg"] = make_bg()
    STATIC["q1"] = with_shadow(text_img("Which country", 88, (246, 246, 252, 255)))
    STATIC["q2"] = with_shadow(text_img("survives?", 88, (246, 246, 252, 255)))
    wm = text_img("@novalabs.hq", 30, (255, 255, 255, 255))
    a = np.asarray(wm).copy()
    a[:, :, 3] = (a[:, :, 3] * 0.35).astype(np.uint8)
    STATIC["wm"] = Image.fromarray(a)
    STATIC["fnum"] = font(150 * S)
    STATIC["flab"] = font(74 * S)
    STATIC["glowdot"] = soft_disc(40, 1.6)
    STATIC["counters"] = {}


def counter_img(n, col):
    key = (n, col)
    if key in STATIC["counters"]:
        return STATIC["counters"][key]
    fnum, flab = STATIC["fnum"], STATIC["flab"]
    s = str(n)
    lab = " LEFT"
    b1 = fnum.getbbox("0")
    dw = max(fnum.getbbox(str(k))[2] - fnum.getbbox(str(k))[0] for k in range(10))
    lb = flab.getbbox(lab)
    w = dw + (lb[2] - lb[0]) + 40 * S
    h = b1[3] - b1[1]
    im = Image.new("RGBA", (int(w + 60), int(h + 60)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    gb = fnum.getbbox(s)
    d.text((30 + (dw - (gb[2] - gb[0])) / 2 - gb[0], 30 - b1[1]), s, font=fnum, fill=col + (255,))
    d.text((30 + dw + 10 * S - lb[0], 30 + h - lb[3]), lab, font=flab, fill=(200, 204, 222, 255))
    out = with_shadow(im)
    STATIC["counters"][key] = out
    return out


# ---------------------------------------------------------------- per-frame state helpers
def ball_pos(sim, st):
    fr = sim["frames"]
    k = st * FPS - 1               # frames[i] holds the state at t=(i+1)/FPS
    i0 = int(math.floor(k))
    i0 = max(0, min(len(fr) - 1, i0))
    i1 = min(len(fr) - 1, i0 + 1)
    f = clamp(k - i0)
    if k < 0:
        return fr[0]["pos"], fr[0]["anchor"]
    return fr[i0]["pos"] * (1 - f) + fr[i1]["pos"] * f, fr[i0]["anchor"]


def out_time(sim):
    return {e[2][0]: e[0] for e in sim["events"] if e[1] == "out"}


def alive_at(sim, st):
    ot = out_time(sim)
    return [ot.get(i, 1e9) > st for i in range(N)]


def rng_for(k):
    return np.random.default_rng(1000 + k)


def paste(img, rgb, mask, cx, cy):
    img.paste(rgb, (int(round(cx - rgb.width / 2)), int(round(cy - rgb.height / 2))), mask)


def scaled_mask(mask, a):
    return mask.point(lambda v: int(v * a))


def lerp_col(a, b, f):
    return tuple(int(a[k] + (b[k] - a[k]) * f) for k in range(3))


def render_frame(vt):
    sim = SIM
    st_of, vt_of, v_end, total = STATIC["tl"]
    vt = max(vt, 0.0)
    se = st_of(vt)                             # effect clock (keeps running after the end)
    st = min(se, sim["end_t"])                 # physics clock
    after = vt - v_end                         # >0 once the winner is decided
    win = sim["winner"]
    img = STATIC["bg"].copy()
    glow = Image.new("RGB", (W // 2, H // 2), (0, 0, 0))   # quarter-res additive glow layer
    gd = ImageDraw.Draw(glow)
    d = ImageDraw.Draw(img)
    g = 0.25                                   # world -> glow layer scale
    pos, anchor = ball_pos(sim, st)
    if after > 0:
        pos = pos.copy()
        mv = ease_io((after - 0.45) / 1.0)
        pos[win] = pos[win] * (1 - mv) + np.array((CX, CY)) * mv
    ot = out_time(sim)
    alive = [ot.get(i, 1e9) > st for i in range(N)]
    lines = Image.new("RGB", img.size, (0, 0, 0))   # additive crisp layer (lasers, sparks, rings)
    ld = ImageDraw.Draw(lines)

    # ---- lasers
    for li, L in enumerate(sim["lasers"]):
        if L["born"] > se:
            continue
        col = TEAMS[L["owner"]][1]
        age = se - L["born"]
        if L["dead"] is not None and se >= L["dead"]:
            dt_ = se - L["dead"]
            if L.get("why") == "old":
                fade = 1 - dt_ / 0.45
                if fade <= 0:
                    continue
                inten, segs = fade * 0.75, [((L["x0"], L["y0"]), (L["x1"], L["y1"]))]
            else:
                # shatter: the two halves snap back toward their anchors
                k = ease_out(dt_ / 0.35)
                if k >= 1:
                    continue
                q = (L["cx"], L["cy"])
                p0, p1 = (L["x0"], L["y0"]), (L["x1"], L["y1"])
                h0 = (q[0] + (p0[0] - q[0]) * k, q[1] + (p0[1] - q[1]) * k)
                h1 = (q[0] + (p1[0] - q[0]) * k, q[1] + (p1[1] - q[1]) * k)
                inten, segs = (1 - k) * 1.1, [(p0, h0), (p1, h1)]
        else:
            nh = sum(1 for h in L.get("hits", []) if h[0] <= st)
            inten = 1.0 if nh == 0 else 0.55 + 0.12 * math.sin(st * 40 + li)
            grow = ease_out(age / 0.10) if L["born"] >= 0 else 1
            p0 = (L["x0"], L["y0"])
            p1 = (L["x0"] + (L["x1"] - L["x0"]) * grow, L["y0"] + (L["y1"] - L["y0"]) * grow)
            segs = [(p0, p1)]
            if age < 0.25 and L["born"] >= 0:
                inten *= 1 + 0.8 * (1 - age / 0.25)
            if after > 0 and L["owner"] == win:
                inten *= (1 + 0.6 * ease_out(after / 0.6)) * (1 - ease_io((after - 1.3) / 0.5))
                if inten <= 0.01:
                    continue
        core = lerp_col(col, (255, 255, 255), 0.45)
        gcol = tuple(int(min(255, c * min(inten, 1.6) * 0.75)) for c in col)
        ccol = tuple(int(min(255, c * min(inten, 1.0) + 30 * max(0, inten - 1))) for c in core)
        for a_, b_ in segs:
            gd.line([(a_[0] * S * g, a_[1] * S * g), (b_[0] * S * g, b_[1] * S * g)], fill=gcol, width=5)
            ld.line([(a_[0] * S, a_[1] * S), (b_[0] * S, b_[1] * S)], fill=ccol, width=int(3.6 * S))

    # ---- in-progress trail (anchor -> ball): shows the next laser being drawn
    if after <= 0:
        for i in range(N):
            if not alive[i]:
                continue
            col = TEAMS[i][1]
            ax, ay = anchor[i]
            bx, by = pos[i]
            dist = math.hypot(bx - ax, by - ay)
            if dist < BR * 1.2:
                continue
            ex, ey = bx - (bx - ax) / dist * BR * 1.05, by - (by - ay) / dist * BR * 1.05
            # dashed, dim
            nd = int(dist / 22)
            for k in range(nd):
                f0, f1 = k / nd, (k + 0.5) / nd
                ld.line([((ax + (ex - ax) * f0) * S, (ay + (ey - ay) * f0) * S),
                        ((ax + (ex - ax) * f1) * S, (ay + (ey - ay) * f1) * S)],
                       fill=tuple(int(c * 0.42) for c in col), width=int(2 * S))

    # ---- event effects (particles, flashes)
    for ei, (te, kind, data) in enumerate(sim["events"]):
        dt_ = se - te
        if after > 0 and te >= sim["end_t"] - 0.5:
            dt_ = vt - vt_of(te)
        if dt_ < 0 or dt_ > 1.2:
            continue
        if kind == "laser" and dt_ < 0.35:
            i, x, y = data
            col = TEAMS[i][1]
            r = 10 + 46 * ease_out(dt_ / 0.35)
            a = 1 - dt_ / 0.35
            gd.ellipse([(x - r) * S * g, (y - r) * S * g, (x + r) * S * g, (y + r) * S * g],
                       outline=tuple(int(c * a) for c in col), width=3)
            ld.ellipse([(x - r * 0.5) * S, (y - r * 0.5) * S, (x + r * 0.5) * S, (y + r * 0.5) * S],
                      outline=tuple(int(c * a * 0.9) for c in col), width=int(2 * S))
        elif kind in ("cut", "crack") and dt_ < 0.6:
            o, j, x, y = data
            col = TEAMS[o][1]
            rng = rng_for(ei)
            nP = 14 if kind == "cut" else 6
            ang = rng.random(nP) * 2 * math.pi
            spd = rng.uniform(160, 520, nP) * (1 if kind == "cut" else 0.6)
            life = rng.uniform(0.3, 0.6, nP)
            for k in range(nP):
                if dt_ > life[k]:
                    continue
                f = dt_ / life[k]
                dist = spd[k] * dt_ * (1 - 0.5 * f)
                px, py = x + math.cos(ang[k]) * dist, y + math.sin(ang[k]) * dist
                tl = 10 * (1 - f)
                tx, ty = px - math.cos(ang[k]) * tl, py - math.sin(ang[k]) * tl
                c2 = tuple(int(c * (1 - f) + 255 * 0.3 * (1 - f)) for c in col)
                ld.line([(tx * S, ty * S), (px * S, py * S)], fill=c2, width=int(2.6 * S))
                gd.line([(tx * S * g, ty * S * g), (px * S * g, py * S * g)], fill=c2, width=3)
            if dt_ < 0.18:
                r = 26 * (1 - dt_ / 0.18) + 6
                a = 1 - dt_ / 0.18
                gd.ellipse([(x - r) * S * g, (y - r) * S * g, (x + r) * S * g, (y + r) * S * g],
                           fill=tuple(int(c * a * 0.8) for c in lerp_col(col, (255, 255, 255), 0.4)))
        elif kind == "bump" and dt_ < 0.2:
            i, j, x, y = data
            a = 1 - dt_ / 0.2
            r = 18 + 30 * dt_ / 0.2
            gd.ellipse([(x - r) * S * g, (y - r) * S * g, (x + r) * S * g, (y + r) * S * g],
                       fill=(int(45 * a), int(45 * a), int(58 * a)))
        elif kind == "out" and dt_ < 1.2:
            i, x, y = data
            col = TEAMS[i][1]
            fcols = FLAG_COLS[TEAMS[i][0]]
            rng = rng_for(ei)
            nP = 46
            ang = rng.random(nP) * 2 * math.pi
            spd = rng.uniform(220, 760, nP)
            life = rng.uniform(0.6, 1.15, nP)
            sz = rng.uniform(7, 15, nP)
            rot = rng.random(nP) * 6
            for k in range(nP):
                if dt_ > life[k]:
                    continue
                f = dt_ / life[k]
                dist = spd[k] * (1 - math.exp(-dt_ * 3.2)) / 3.2
                px, py = x + math.cos(ang[k]) * dist, y + math.sin(ang[k]) * dist + 160 * dt_ ** 2
                rr_ = math.hypot(px - CX, py - CY)
                if rr_ > RA - 14:
                    px, py = CX + (px - CX) * (RA - 14) / rr_, CY + (py - CY) * (RA - 14) / rr_
                s_ = sz[k] * (1 - f * 0.7)
                c2 = fcols[k % len(fcols)]
                c2 = tuple(int(c * (1 - f * 0.6)) for c in c2)
                th = rot[k] + dt_ * 9
                tri = [(px + s_ * math.cos(th + q * 2.1), py + s_ * math.sin(th + q * 2.1)) for q in range(3)]
                d.polygon([(a_ * S, b_ * S) for a_, b_ in tri], fill=c2)
            if dt_ < 0.5:
                f = dt_ / 0.5
                r = BR + 120 * ease_out(f)
                a = (1 - f) ** 1.5
                gd.ellipse([(x - r) * S * g, (y - r) * S * g, (x + r) * S * g, (y + r) * S * g],
                           outline=tuple(int(c * a) for c in col), width=6)
                ld.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S],
                           outline=tuple(int(c * a * 0.8) for c in lerp_col(col, (255, 255, 255), 0.5)), width=int(3 * S))
            if dt_ < 0.12:
                a = 1 - dt_ / 0.12
                r = BR * 2.2
                gd.ellipse([(x - r) * S * g, (y - r) * S * g, (x + r) * S * g, (y + r) * S * g],
                           fill=tuple(int(c * a) for c in lerp_col(col, (255, 255, 255), 0.6)))

    # ---- winner celebration: its lasers burst out and take the whole arena
    if after > 1.3:
        col = TEAMS[win][1]
        core = lerp_col(col, (255, 255, 255), 0.45)
        nR = 24
        rot = 0.25 * (after - 1.3)
        for k in range(nR):
            delay = (k % 4) * 0.06
            gr = ease_out((after - 1.3 - delay) / 0.45)
            if gr <= 0:
                continue
            a = rot + k * 2 * math.pi / nR
            r0 = BR * 2.55 + 34
            r1 = r0 + (RA - r0) * gr
            p0 = (CX + r0 * math.cos(a), CY + r0 * math.sin(a))
            p1 = (CX + r1 * math.cos(a), CY + r1 * math.sin(a))
            fl = 1 + 0.9 * max(0, 1 - (after - 1.3 - delay) / 0.5)
            gd.line([(p0[0] * S * g, p0[1] * S * g), (p1[0] * S * g, p1[1] * S * g)],
                    fill=tuple(int(min(255, c * 0.6 * fl)) for c in col), width=5)
            ld.line([(p0[0] * S, p0[1] * S), (p1[0] * S, p1[1] * S)],
                    fill=tuple(int(min(255, c * 0.85 * min(fl, 1.3))) for c in core), width=int(3.2 * S))
            if gr >= 1 and after - 1.3 - delay < 0.9:
                fa = 1 - (after - 1.3 - delay - 0.45) / 0.45
                if fa > 0:
                    gd.ellipse([(p1[0] - 20) * S * g, (p1[1] - 20) * S * g, (p1[0] + 20) * S * g, (p1[1] + 20) * S * g],
                               fill=tuple(int(c * fa) for c in col))

    # ---- winner celebration: confetti + gold ring
    if after > 0:
        rng = rng_for(99)
        nC = 110
        x0 = rng.uniform(60, 900, nC)
        vy = rng.uniform(430, 700, nC)
        t0 = rng.uniform(0.0, 0.8, nC) + 1.4
        ph = rng.random(nC) * 6
        fcols = FLAG_COLS[TEAMS[win][0]] + [GOLD]
        for k in range(nC):
            tt = after - t0[k]
            if tt < 0:
                continue
            y = 560 + vy[k] * tt - 30
            if y > 1660:
                continue
            x = x0[k] + 26 * math.sin(tt * 3 + ph[k])
            w_ = 9 * abs(math.cos(tt * 5 + ph[k])) + 1.5
            th = ph[k] + tt * 2.2
            c, s_ = math.cos(th), math.sin(th)
            quad = [(x + c * u - s_ * v, y + s_ * u + c * v) for u, v in ((-w_, -6), (w_, -6), (w_, 6), (-w_, 6))]
            sh = 0.75 + 0.25 * abs(math.cos(tt * 5 + ph[k]))
            c2 = tuple(int(q * sh) for q in fcols[k % len(fcols)])
            d.polygon([(a_ * S, b_ * S) for a_, b_ in quad], fill=c2)

    # ---- balls
    shadows = []
    for i in range(N):
        if not alive[i]:
            continue
        r_ball = BR
        if after > 0 and i == win:
            r_ball = BR * (1 + 1.55 * ease_io((after - 0.45) / 1.0))
            r_ball *= 1 + 0.05 * math.sin(max(0, after - 1.9) * 4) * (after > 1.9)
        x, y = pos[i]
        # contact-shadow + coloured underglow
        col = TEAMS[i][1]
        rr = r_ball * 1.6
        gd.ellipse([(x - rr) * S * g, (y - rr) * S * g, (x + rr) * S * g, (y + rr) * S * g],
                   fill=tuple(int(c * 0.22) for c in col))
    glow = glow.filter(ImageFilter.GaussianBlur(7))
    glow2 = glow.filter(ImageFilter.GaussianBlur(18))
    glow = ImageChops.add(glow, glow2)
    img = ImageChops.add(img, glow.resize(img.size, Image.BILINEAR))
    img = ImageChops.add(img, lines)
    d = ImageDraw.Draw(img)

    if after > 0 and after > 1.6:
        a = ease_out((after - 1.6) / 0.5)
        rr = BR * 2.55 + 26 + 10 * math.sin(after * 3)
        d.ellipse([(CX - rr) * S, (CY - rr) * S, (CX + rr) * S, (CY + rr) * S],
                  outline=lerp_col((0, 0, 0), GOLD, a * 0.85), width=int(4 * S))

    vel = SIM["frames"][min(len(SIM["frames"]) - 1, max(0, int(st * FPS) - 1))]["vel"]
    for i in range(N):
        if not alive[i]:
            continue
        x, y = pos[i]
        r_ball = BR
        if after > 0 and i == win:
            r_ball = BR * (1 + 1.55 * ease_io((after - 0.45) / 1.0))
            r_ball *= 1 + 0.05 * math.sin(max(0, after - 1.9) * 4) * (after > 1.9)
        flash = 0.0
        hit_ts = [e[0] for e in sim["events"] if e[1] in ("cut",) and e[2][0] == i and 0 <= st - e[0] < 0.15]
        if hit_ts:
            flash = 0.45 * (1 - (st - max(hit_ts)) / 0.15)
        rgb, m = ball_sprite(i, r_ball * S, round(flash * 4) / 4)
        v = np.zeros(2)
        if after <= 0:
            rate = (st_of(vt + 0.5 / FPS) - st_of(vt - 0.5 / FPS))
            v = vel[i] * rate
        sp = math.hypot(*v)
        if sp * S < 3:
            paste(img, rgb, m, x * S, y * S)
            continue
        pad = int(rgb.width / 2 + sp * S + 4)
        bx0, by0 = int(x * S) - pad, int(y * S) - pad
        box = (max(0, bx0), max(0, by0), min(img.width, bx0 + 2 * pad), min(img.height, by0 + 2 * pad))
        base = img.crop(box)
        acc = np.zeros((base.height, base.width, 3), np.float32)
        for k in range(4):
            f = (k + 0.5) / 4 - 0.5                     # -0.375 .. 0.375 of the inter-frame motion * 0.5 shutter
            tmp = base.copy()
            tmp.paste(rgb, (int(round((x + v[0] * f * 0.5) * S - rgb.width / 2)) - box[0],
                            int(round((y + v[1] * f * 0.5) * S - rgb.height / 2)) - box[1]), m)
            acc += np.asarray(tmp, np.float32)
        img.paste(Image.fromarray((acc / 4).astype(np.uint8)), box[:2])

    # ---- HUD
    img = img.convert("RGBA")
    q1, q2 = STATIC["q1"], STATIC["q2"]
    img.alpha_composite(q1, (int(W * S / 2 - q1.width / 2), int(140 * S)))
    img.alpha_composite(q2, (int(W * S / 2 - q2.width / 2), int(240 * S)))
    n_left = sum(alive)
    last_out = max([t_ for t_ in ot.values() if t_ <= st], default=-9)
    punch = 0.0
    if st - last_out < 0.35:
        punch = (1 - (st - last_out) / 0.35)
    if after > 1.3:
        a = ease_out((after - 1.3) / 0.4)
        nm = TEAMS[win][0] + " WINS"
        key = ("win", nm)
        if key not in STATIC["counters"]:
            STATIC["counters"][key] = with_shadow(text_img(nm, 104, GOLD + (255,)))
        ci = STATIC["counters"][key]
        sc = 0.7 + 0.3 * ease_out((after - 1.3) / 0.35) + 0.06 * math.sin(clamp((after - 1.3) / 0.5) * math.pi)
        ci = ci.resize((int(ci.width * sc), int(ci.height * sc)), Image.LANCZOS)
        arr = np.asarray(ci).copy()
        arr[:, :, 3] = (arr[:, :, 3] * a).astype(np.uint8)
        img.alpha_composite(Image.fromarray(arr), (int(W * S / 2 - ci.width / 2), int((440 - 62 * sc) * S - 30)))
    else:
        col = (255, 255, 255)
        if n_left <= 2:
            col = lerp_col((255, 255, 255), GOLD, 0.85)
        if punch > 0:
            col = lerp_col(col, (255, 90, 100), punch * 0.7)
        ci = counter_img(n_left, col)
        sc = 1 + 0.22 * punch ** 2
        if after > 0.9:
            sc *= 1 - 0.3 * ease_io((after - 0.9) / 0.4)
        if sc != 1:
            ci = ci.resize((int(ci.width * sc), int(ci.height * sc)), Image.LANCZOS)
        a = 1.0 if after <= 0.9 else 1 - ease_io((after - 0.9) / 0.4)
        if a > 0:
            if a < 1:
                arr = np.asarray(ci).copy()
                arr[:, :, 3] = (arr[:, :, 3] * a).astype(np.uint8)
                ci = Image.fromarray(arr)
            img.alpha_composite(ci, (int(W * S / 2 - ci.width / 2), int(440 * S - ci.height / 2)))
    wm = STATIC["wm"]
    img.alpha_composite(wm, (int(W * S / 2 - wm.width / 2), int(1585 * S)))
    img = img.convert("RGB")
    # light shake on knock-outs
    sh = 0.0
    for t_ in ot.values():
        if 0 <= st - t_ < 0.25:
            sh = max(sh, (1 - (st - t_) / 0.25) * (7 if t_ == sim["end_t"] else 3.5))
    if sh > 0:
        ox, oy = int(sh * S * math.sin(vt * 91)), int(sh * S * math.cos(vt * 77))
        img = ImageChops.offset(img, ox, oy)
    return img.resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- audio
PENTA = [0, 2, 4, 7, 9]


def note_freq(step, base=261.63):
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
    team_step = [5, 6, 7, 8, 9, 10, 11, 12]
    last = {}
    for te, kind, data in sim["events"]:
        vt = vt_of(te)
        if vt < 0:
            continue
        # polyphony guard: at most one sound of a kind per 28 ms
        if vt - last.get(kind, -1) < 0.028:
            continue
        last[kind] = vt
        if kind == "laser":
            i = data[0]
            f = note_freq(team_step[i])
            add(dry, vt, tone(f, 0.7, r=0.32), 0.24)
            add(dry, vt, sweep(2600, 650, 0.09, r=0.035), 0.07)
        elif kind == "edge":
            add(dry, vt, tone(1800, 0.06, r=0.015, parts=((1, 1),)), 0.05)
        elif kind == "crack":
            add(dry, vt, tone(3300, 0.12, a=0.001, r=0.03, parts=((1, 1), (1.42, 0.6))), 0.09)
            nz = band(rng.normal(0, 1, int(0.05 * SR)), 3000, 9000) * env(int(0.05 * SR), 0.001, 0.012)
            add(dry, vt, nz, 0.10)
        elif kind == "cut":
            o = data[0]
            nzn = int(0.22 * SR)
            nz = band(rng.normal(0, 1, nzn), 2500, 11000) * env(nzn, 0.001, 0.05)
            add(dry, vt, nz, 0.22)
            f = note_freq(team_step[o] + 5)
            add(dry, vt, tone(f, 0.8, a=0.002, r=0.22, parts=((1, 1), (2.76, 0.35), (5.4, 0.15))), 0.16)
        elif kind == "bump":
            add(dry, vt, sweep(170, 85, 0.14, a=0.002, r=0.05), 0.22)
        elif kind == "out":
            i = data[0]
            final = abs(te - sim["end_t"]) < 1e-6
            g = 1.0 if final else 0.75
            add(dry, vt, sweep(85, 34, 1.2, a=0.003, r=0.42 if final else 0.3), 0.85 * g)
            nzn = int(0.6 * SR)
            nz = band(rng.normal(0, 1, nzn), 60, 1800) * env(nzn, 0.002, 0.14)
            add(dry, vt, nz, 0.40 * g)
            nz2 = band(rng.normal(0, 1, nzn), 3000, 12000) * env(nzn, 0.001, 0.08)
            add(dry, vt, nz2, 0.16 * g)
            for k in range(4):
                add(dry, vt + 0.06 + k * 0.075, tone(note_freq(team_step[i] + 4 - k), 0.6, r=0.18), 0.12 * g)
    # pad: C major drone that thickens as the field shrinks
    tt = np.arange(n) / SR
    ot = sorted(vt_of(e[0]) for e in sim["events"] if e[1] == "out")
    left = np.full(n, float(N))
    for k, v in enumerate(ot):
        left[int(max(0, v) * SR):] = N - k - 1
    inten = 0.035 + 0.05 * (N - left) / (N - 1)
    inten = np.convolve(inten, np.ones(4410) / 4410, mode="same")
    pad = np.zeros(n)
    for f, g in ((130.81, 1.0), (196.0, 0.7), (261.63, 0.6), (329.63, 0.45), (392.0, 0.3)):
        pad += g * (np.sin(2 * math.pi * f * tt) + 0.5 * np.sin(2 * math.pi * f * 1.003 * tt + 1.0))
    pad *= (0.8 + 0.2 * np.sin(2 * math.pi * 0.23 * tt))
    pad = pad / 3.0 * inten
    pad *= np.clip(tt / 0.6, 0, 1)
    # heartbeat during the duel
    duel_v = ot[-2] if len(ot) >= 2 else v_end - 8
    t_h = duel_v + 0.6
    while t_h < v_end - 0.15:
        prog = (t_h - duel_v) / max(1e-3, v_end - duel_v)
        add(dry, t_h, sweep(95, 48, 0.18, a=0.003, r=0.06), 0.30 + 0.15 * prog)
        add(dry, t_h + 0.16, sweep(85, 45, 0.16, a=0.003, r=0.05), 0.20 + 0.1 * prog)
        t_h += 0.62 - 0.2 * prog
    # riser into the last knock-out
    r0 = v_end - 4.5
    rn = int(4.5 * SR)
    x = np.linspace(0, 1, rn)
    noise = rng.normal(0, 1, rn)
    riser = np.zeros(rn)
    for k in range(8):
        seg = slice(k * rn // 8, (k + 1) * rn // 8)
        lo = 400 + 600 * k
        riser[seg] = band(noise[seg], lo, lo * 3)[: (seg.stop - seg.start)]
    riser = riser * x ** 2.2 * 0.12 + sweep(220, 880, 4.5, a=1.5, r=99) * x ** 2 * 0.07
    add(dry, r0, riser, 1.0)
    # winner: whoosh to the centre, then the big chord + bell arpeggio when the lasers burst out
    wn = int(1.0 * SR)
    wh = band(rng.normal(0, 1, wn), 300, 3000) * np.sin(np.linspace(0, math.pi, wn)) ** 2
    add(dry, v_end + 0.45, wh, 0.12)
    cd = 5.0
    chord = sum(tone(f, cd, a=0.02, r=1.6, parts=((1, 1), (2, 0.4), (3, 0.15), (4, 0.06)))
                for f in (261.63, 329.63, 392.0, 523.25, 659.25, 783.99))
    add(dry, v_end + 1.3, chord, 0.20)
    add(dry, v_end + 1.3, sweep(70, 40, 1.0, a=0.003, r=0.4), 0.6)
    for k, f in enumerate((1046.5, 1318.5, 1568.0, 2093.0, 1568.0, 2093.0, 2637.0)):
        add(dry, v_end + 1.3 + 0.09 * k, tone(f, 1.2, a=0.002, r=0.35, parts=((1, 1), (2.76, 0.25))), 0.10)
    sh = band(rng.normal(0, 1, int(2.5 * SR)), 5000, 14000) * env(int(2.5 * SR), 0.05, 0.6)
    add(dry, v_end + 1.4, sh, 0.05)
    # reverb (exponential noise tail, FFT convolution)
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


def render_bytes(fi):
    return render_frame(fi / FPS).tobytes()


def _job(sd):
    s = simulate(sd)
    outs, nw, nc = summary(s)
    return sd, dict(end_t=s["end_t"], winner=s["winner"]), (outs, nw, nc)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--search", type=int, default=0)
    ap.add_argument("--frames", default="")
    ap.add_argument("--outdir", default="keys")
    ap.add_argument("--out", default="")
    ap.add_argument("--audio", default="")
    a = ap.parse_args()
    if a.search:
        with Pool(4) as p:
            res = p.map(_job, range(a.search))
        for sd, s, (outs, nw, nc) in res:
            print(sd, s["end_t"] and round(s["end_t"], 1), TEAMS[s["winner"]][0] if s["winner"] is not None else None,
                  [round(x, 1) for x in outs], nw, nc, flush=True)
    elif a.audio:
        s = simulate(a.seed)
        synth_audio(s, a.audio)
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
        outs, nw, nc = summary(s)
        tl = build_timeline(s)
        print("end", round(s["end_t"], 2), "winner", TEAMS[s["winner"]][0], "outs", [round(x, 1) for x in outs],
              "lasers", nw, "cuts", nc, "video", round(tl[3], 2), "s")
