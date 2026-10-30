#!/usr/bin/env python3
"""Match Day — Chelsea vs Man United. A spinning ring with a goal-shaped opening; two team balls
(CHE blue, MUN red) bounce inside. A ball that leaves through the goal scores for its team.
Clock runs 0' -> 90'+3', the ring spins faster after half-time and the goal widens late in the game.

Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS down to 1080x1920, 60 fps.
Audio fully synthesized, -1 dBFS.

    python3 match-che-mun.py --search 200
    python3 match-che-mun.py --seed N                       (simulation summary)
    python3 match-che-mun.py --frames 0,0.2,0.4,0.6,0.8,0.97 --outdir keys/ --seed N
    python3 match-che-mun.py --out video.mp4 --seed N
"""
import argparse, math, os, subprocess, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

W, H, FPS, S = 1080, 1920, 60, 2
SR = 44100
SUB = 8
DT = 1.0 / (FPS * SUB)

CX, CY, RA = 540.0, 1150.0, 390.0
BR = 62.0
NET_D = 82.0
POST_R = 8.0
T90 = 36.0                    # seconds of play for 90 minutes
T_END = T90 + 3.0             # + 3 minutes of added time
HOLD = 5.0
V1, V2 = 610.0, 700.0
W1, W2 = 0.78, 1.05           # ring angular speed (rad/s) first / second half
GA1, GA2 = 0.28, 0.35       # goal half-angle (rad)
SEED = 0

TEAMS = [
    dict(name="CHELSEA", code="CHE", col=(36, 112, 255), light=(120, 175, 255)),
    dict(name="MAN UNITED", code="MUN", col=(238, 38, 62), light=(255, 130, 140)),
]
GOLD = (255, 210, 74)
FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]


def clamp(x, a=0.0, b=1.0):
    return min(max(x, a), b)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def minute(t):
    if t <= T90:
        return 90.0 * t / T90
    return 90.0 + 3.0 * (t - T90) / (T_END - T90)


def ring_angle(t, th0):
    h = T90 / 2
    if t <= h:
        return th0 + W1 * t
    return th0 + W1 * h + W2 * (t - h)


def half_angle(t):
    return GA1 + (GA2 - GA1) * ease_io((minute(t) - 58) / 10.0)


# ---------------------------------------------------------------- simulation
def simulate(seed):
    rng = np.random.default_rng(seed)
    th0 = rng.random() * 2 * math.pi
    nst = int(T_END / DT) + 1
    P = np.zeros((2, nst, 2))
    MODE = np.zeros((2, nst), np.int8)       # 0 play, 1 in net, 2 absent
    spawn_log = [[0.0], [0.0]]
    pos = np.array([[CX - 150, CY - 90], [CX + 150, CY + 90.]]) + rng.normal(0, 30, (2, 2))
    ang = np.zeros(2)
    for i in range(2):
        ang[i] = math.atan2(CY - pos[i, 1], CX - pos[i, 0]) + rng.normal(0, 0.5)
    vel = np.stack([np.cos(ang), np.sin(ang)], 1) * V1
    mode = [0, 0]
    tg = [0.0, 0.0]
    lat = [0.0, 0.0]
    respawn = [0.0, 0.0]
    score = [0, 0]
    goals = []         # (t, team, minute)
    hits = []          # (t, team, strength)
    clashes = []
    last_hit = [-1, -1]
    last_clash = -1
    C = np.array([CX, CY])
    for k in range(nst):
        t = k * DT
        th = ring_angle(t, th0)
        ga = half_angle(t)
        V = V1 if minute(t) < 45 else V2
        gdir = np.array([math.cos(th), math.sin(th)])
        gper = np.array([-math.sin(th), math.cos(th)])
        posts = [C + RA * np.array([math.cos(th + s * ga), math.sin(th + s * ga)]) for s in (-1, 1)]
        for i in range(2):
            if mode[i] == 0:
                p = pos[i] + vel[i] * DT
                v = vel[i] / np.linalg.norm(vel[i]) * V
                rel = p - C
                d = np.linalg.norm(rel)
                dth = (math.atan2(rel[1], rel[0]) - th + math.pi) % (2 * math.pi) - math.pi
                in_gap = abs(dth) < ga
                if d + BR > RA and not in_gap:
                    n = rel / d
                    if np.dot(v, n) > 0:
                        v = v - 2 * np.dot(v, n) * n
                        if t - last_hit[i] > 0.05:
                            hits.append((t, i, 1.0))
                            last_hit[i] = t
                    p = C + n * (RA - BR)
                for ps in posts:
                    dd = p - ps
                    L = np.linalg.norm(dd)
                    if L < BR + POST_R:
                        n = dd / max(L, 1e-6)
                        if np.dot(v, n) < 0:
                            v = v - 2 * np.dot(v, n) * n
                            if t - last_hit[i] > 0.05:
                                hits.append((t, i, 0.7))
                                last_hit[i] = t
                        p = ps + n * (BR + POST_R)
                if in_gap and d > RA + 16:
                    mode[i] = 1
                    tg[i] = t
                    lat[i] = float(np.dot(rel, gper))
                    score[i] += 1
                    goals.append((t, i, minute(t)))
                    respawn[i] = t + 1.45
                pos[i], vel[i] = p, v
            elif mode[i] == 1:
                tau = t - tg[i]
                r = RA + 16 + 30 * ease_out(tau / 0.4)
                pos[i] = C + gdir * r + gper * lat[i] * (1 - 0.5 * ease_out(tau / 0.5))
                if tau > 1.0:
                    mode[i] = 2
            else:
                if t >= respawn[i] and t < T_END - 1.0:
                    other = pos[1 - i] if mode[1 - i] == 0 else np.array([CX + 9999, CY])
                    c = C
                    for _ in range(40):
                        a = rng.random() * 2 * math.pi
                        c = C + rng.random() ** 0.5 * 160 * np.array([math.cos(a), math.sin(a)])
                        if np.linalg.norm(c - other) > 3 * BR:
                            break
                    pos[i] = c
                    a2 = rng.random() * 2 * math.pi
                    vel[i] = np.array([math.cos(a2), math.sin(a2)]) * V
                    mode[i] = 0
                    spawn_log[i].append(t)
        if mode[0] == 0 and mode[1] == 0:
            dd = pos[1] - pos[0]
            L = np.linalg.norm(dd)
            if L < 2 * BR:
                n = dd / max(L, 1e-6)
                rv = np.dot(vel[0] - vel[1], n)
                if rv > 0:
                    vel[0] = vel[0] - rv * n
                    vel[1] = vel[1] + rv * n
                    if t - last_clash > 0.1:
                        clashes.append((t, 1.0))
                        last_clash = t
                mid = (pos[0] + pos[1]) / 2
                pos[0] = mid - n * BR
                pos[1] = mid + n * BR
        for i in range(2):
            P[i, k] = pos[i]
            MODE[i, k] = mode[i]
    return dict(P=P, MODE=MODE, goals=goals, hits=hits, clashes=clashes, score=score, th0=th0,
                spawns=spawn_log, nst=nst, seed=seed)


def summary(s):
    return dict(score=s["score"], goals=[(round(t, 1), TEAMS[i]["code"], round(m)) for t, i, m in s["goals"]],
                clashes=len(s["clashes"]), hits=len(s["hits"]))


def seed_ok(s):
    g = s["goals"]
    if not (4 <= len(g) <= 7):
        return False
    a, b = s["score"]
    if a == b or abs(a - b) > 1:
        return False
    last = g[-1]
    win = 0 if a > b else 1
    if last[1] != win or last[2] < 80:
        return False
    if g[0][2] > 30:
        return False
    sc = [0, 0]
    tie = 0
    for _, i, _ in g:
        sc[i] += 1
        if sc[0] == sc[1]:
            tie += 1
    if tie < 1:
        return False
    ms = [x[2] for x in g]
    return all(b_ - a_ >= 6 for a_, b_ in zip(ms, ms[1:]))


def total_time():
    return T_END + HOLD


def state_at(sim, t, i):
    k = min(sim["nst"] - 1, max(0, int(round(min(t, T_END) / DT))))
    return sim["P"][i, k], int(sim["MODE"][i, k])


def score_at(sim, t):
    sc = [0, 0]
    for tg, i, _ in sim["goals"]:
        if tg <= t:
            sc[i] += 1
    return sc


# ---------------------------------------------------------------- drawing helpers
STATIC = {}


def font(px):
    for p in FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, int(px))
    return ImageFont.load_default()


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


def scale_img(im, f):
    return im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))), Image.BICUBIC)


def fade_img(im, a):
    arr = np.asarray(im).copy()
    arr[:, :, 3] = (arr[:, :, 3] * clamp(a)).astype(np.uint8)
    return Image.fromarray(arr)


def put_center(canvas, im, cx, cy):
    x = int(round(cx * S - im.width / 2))
    y = int(round(cy * S - im.height / 2))
    canvas.alpha_composite(im, (x, y))


TXT = {}


def cached_text(txt, px, fill, shadow=True):
    key = (txt, px, tuple(fill), shadow)
    if key not in TXT:
        im = text_img(txt, px, tuple(fill) + (255,))
        TXT[key] = with_shadow(im) if shadow else im
    return TXT[key]


def lerp(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def make_bg():
    Hs, Ws = H * S, W * S
    y = np.linspace(0, 1, Hs, dtype=np.float32)[:, None]
    x = np.linspace(-1, 1, Ws, dtype=np.float32)[None, :]
    top, bot = np.array([12, 18, 40.], np.float32), np.array([4, 6, 16.], np.float32)
    img = top[None, None, :] * (1 - y[:, :, None]) + bot[None, None, :] * y[:, :, None]
    yy = (y * 2 - 1)
    vig = 1 - 0.30 * np.clip(x ** 2 * 0.7 + yy ** 2 * 0.45, 0, 1)
    img = img * vig[:, :, None]
    py = (np.arange(Hs, dtype=np.float32)[:, None] + 0.5) / S
    px = (np.arange(Ws, dtype=np.float32)[None, :] + 0.5) / S
    r = np.sqrt((px - CX) ** 2 + (py - CY) ** 2)
    inside = np.clip((RA - r) * S / 2 + 0.5, 0, 1)
    floor = np.array([14, 28, 52.], np.float32) * (0.8 + 0.3 * np.exp(-(r / RA) ** 2 * 1.4))[:, :, None]
    img = img * (1 - inside[:, :, None]) + floor * inside[:, :, None]
    cc = np.exp(-((r - 96) / 1.6) ** 2) * 0.16 + np.exp(-(r / 5.0) ** 2) * 0.22
    line = np.exp(-((px - CX) / 1.4) ** 2) * 0.09
    img += np.array([170, 200, 255.], np.float32)[None, None, :] * ((cc + line) * (r < RA - 4))[:, :, None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")


def ball_sprite(team):
    r = BR * S
    n = int(2 * r + 8)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2
    u, v = (xx - c) / r, (yy - c) / r
    rr = np.sqrt(u * u + v * v)
    z = np.sqrt(np.clip(1 - rr * rr, 0, 1))
    L = np.array([-0.45, -0.6, 0.66]); L /= np.linalg.norm(L)
    diff = np.clip(u * L[0] + v * L[1] + z * L[2], 0, 1)
    base = np.array(TEAMS[team]["col"], np.float32)
    col = base[None, None, :] * (0.42 + 0.78 * diff[:, :, None]) + ((1 - z) ** 2.5)[:, :, None] * np.array([20, 24, 40.])
    h = np.array([L[0], L[1], L[2] + 1]); h /= np.linalg.norm(h)
    spec = np.clip(u * h[0] + v * h[1] + z * h[2], 0, 1) ** 48
    col += spec[:, :, None] * 255 * 0.85
    rim = np.clip((rr - 0.82) / 0.18, 0, 1) ** 2
    col += rim[:, :, None] * np.array(TEAMS[team]["light"], np.float32) * 0.28
    alpha = np.clip((1 - rr) * r + 0.5, 0, 1)
    im = Image.fromarray(np.dstack([np.clip(col, 0, 255), alpha * 255]).astype(np.uint8), "RGBA")
    code = TEAMS[team]["code"]
    f = font(43 * S)
    bb = f.getbbox(code)
    d = ImageDraw.Draw(im)
    tx, ty = c - (bb[0] + bb[2]) / 2, c - (bb[1] + bb[3]) / 2
    d.text((tx + 1.5 * S, ty + 1.5 * S), code, font=f, fill=(0, 0, 20, 110))
    d.text((tx, ty), code, font=f, fill=(255, 255, 255, 250))
    return im


def halo(team, r_px):
    n = int(2 * r_px)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    rr = np.sqrt((xx - n / 2) ** 2 + (yy - n / 2) ** 2) / (n / 2)
    a = np.clip(1 - rr, 0, 1) ** 2.2
    col = np.array(TEAMS[team]["col"], np.float32)
    return Image.fromarray(np.clip(a[:, :, None] * col[None, None, :], 0, 255).astype(np.uint8))


def init_static():
    STATIC["bg"] = make_bg()
    STATIC["spr"] = [ball_sprite(0), ball_sprite(1)]
    STATIC["halo"] = [halo(0, BR * S * 2.1), halo(1, BR * S * 2.1)]
    wm = text_img("@novalabs.hq", 30, (255, 255, 255, 255))
    a = np.asarray(wm).copy()
    a[:, :, 3] = (a[:, :, 3] * 0.35).astype(np.uint8)
    STATIC["wm"] = Image.fromarray(a)


# ---------------------------------------------------------------- confetti
def confetti(seed, n, ox, oy, ang0, spread, vmin, vmax, cols, top=False):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        if top:
            x0, y0 = rng.random() * W, -60 - rng.random() * 400
            vx, vy = rng.normal(0, 40), 120 + rng.random() * 200
        else:
            a = ang0 + (rng.random() - 0.5) * spread
            sp = vmin + rng.random() * (vmax - vmin)
            x0, y0, vx, vy = ox, oy, math.cos(a) * sp, math.sin(a) * sp
        out.append((x0, y0, vx, vy, rng.random() * 6.28, (rng.random() - 0.5) * 14,
                    7 + rng.random() * 8, 4 + rng.random() * 6, cols[int(rng.integers(0, len(cols)))]))
    return out


def draw_confetti(d, pieces, tau, life=2.2, g=900.0, drag=1.4, ytop=True):
    if tau < 0 or tau > life:
        return
    ymin = 640 * S if ytop else 0
    f = 1 - ease_io((tau - life * 0.6) / (life * 0.4)) if tau > life * 0.6 else 1.0
    for x0, y0, vx, vy, r0, rv, w, h, col in pieces:
        dec = (1 - math.exp(-drag * tau)) / drag
        x = x0 + vx * dec
        y = y0 + vy * dec + 0.5 * g * tau * tau * 0.6
        r = r0 + rv * tau
        c, s = math.cos(r), math.sin(r)
        hh = h * abs(math.cos(rv * tau * 0.7 + r0)) + 1.2
        pts = [((x + (a * c - b * s)) * S, (y + (a * s + b * c)) * S) for a, b in ((-w, -hh), (w, -hh), (w, hh), (-w, hh))]
        if min(p_[1] for p_ in pts) < ymin:
            continue
        d.polygon(pts, fill=tuple(int(c_ * f) for c_ in col) + (255,))


# ---------------------------------------------------------------- frame
def draw_ball(cv, i, ts, sim, alpha=1.0, scale=1.0):
    sp = STATIC["spr"][i]
    hl = STATIC["halo"][i]
    if scale != 1.0:
        sp = scale_img(sp, scale)
        hl = hl.resize((max(1, int(hl.width * scale)), max(1, int(hl.height * scale))), Image.BILINEAR)
    if alpha < 0.999:
        sp = fade_img(sp, alpha)
    sub = [state_at(sim, t, i)[0] for t in ts]
    pad = int(BR * S * 2.3)
    x0 = int(min(q[0] for q in sub) * S - pad)
    y0 = int(min(q[1] for q in sub) * S - pad)
    x1 = int(max(q[0] for q in sub) * S + pad)
    y1 = int(max(q[1] for q in sub) * S + pad)
    crop = cv.crop((x0, y0, x1, y1)).convert("RGB")
    acc = np.zeros((crop.height, crop.width, 3), np.float32)
    for q in sub:
        tmp = Image.new("RGB", crop.size, (0, 0, 0))
        tmp.paste(hl, (int(q[0] * S - hl.width / 2 - x0), int(q[1] * S - hl.height / 2 - y0)))
        c = ImageChops.add(crop, Image.eval(tmp, lambda v: int(v * 0.30 * alpha))).convert("RGBA")
        c.alpha_composite(sp, (int(q[0] * S - sp.width / 2 - x0), int(q[1] * S - sp.height / 2 - y0)))
        acc += np.asarray(c.convert("RGB")).astype(np.float32)
    out = Image.fromarray(np.clip(acc / len(sub), 0, 255).astype(np.uint8)).convert("RGBA")
    cv.paste(out, (x0, y0))


def draw_ring_and_goal(cv, th, ga, glow_col, glow_amt):
    pad = int((RA + NET_D + 90) * S)
    cx, cy = int(CX * S), int(CY * S)
    box = (cx - pad, cy - pad, cx + pad, cy + pad)
    crop = cv.crop(box).convert("RGB")
    hp = pad                                  # glow layer at half resolution: size = pad (= 2*pad/2)
    gl = Image.new("RGB", (hp, hp), (0, 0, 0))
    gd = ImageDraw.Draw(gl)
    hc = hp / 2
    rr = RA * S / 2
    base_col = (110, 130, 200)
    gcol = lerp(base_col, glow_col, glow_amt)
    a0 = math.degrees(th + ga)
    a1 = math.degrees(th - ga) + 360
    gd.arc([hc - rr, hc - rr, hc + rr, hc + rr], a0, a1,
           fill=tuple(int(c * (0.55 + 0.45 * glow_amt)) for c in gcol), width=int(9 * S / 2))
    gl = gl.filter(ImageFilter.GaussianBlur(10 * S / 2 * (1 + glow_amt)))
    gl = gl.resize((pad * 2, pad * 2), Image.BILINEAR)
    crop = ImageChops.add(crop, Image.eval(gl, lambda v: int(v * (0.85 + 0.5 * glow_amt))))
    d = ImageDraw.Draw(crop)
    c0 = pad
    ring_col = lerp((232, 238, 255), glow_col, 0.55 * glow_amt)
    d.arc([c0 - RA * S, c0 - RA * S, c0 + RA * S, c0 + RA * S], a0, a1, fill=ring_col, width=int(6.5 * S))
    gd_ = np.array([math.cos(th), math.sin(th)])
    gp_ = np.array([-math.sin(th), math.cos(th)])
    half_w = RA * math.sin(ga)
    mid_in = RA * math.cos(ga)

    def pt(r, lat):
        return (c0 + (gd_[0] * r + gp_[0] * lat) * S, c0 + (gd_[1] * r + gp_[1] * lat) * S)
    r_back = RA + NET_D
    netcol = lerp((70, 88, 130), glow_col, 0.5 * glow_amt)
    n_d, n_l = 6, 8
    for j in range(1, n_d):
        r = mid_in + (r_back - mid_in) * j / n_d
        d.line([pt(r, -half_w), pt(r, half_w)], fill=netcol, width=int(1.4 * S))
    for j in range(-n_l + 1, n_l):
        lat = half_w * j / n_l
        d.line([pt(mid_in, lat), pt(r_back, lat)], fill=netcol, width=int(1.4 * S))
    fr = lerp((240, 244, 255), glow_col, 0.5 * glow_amt)
    d.line([pt(RA, -half_w), pt(r_back, -half_w), pt(r_back, half_w), pt(RA, half_w)], fill=fr, width=int(5 * S), joint="curve")
    for sgn in (-1, 1):
        x, y = pt(RA, sgn * half_w)
        d.ellipse([x - 7 * S, y - 7 * S, x + 7 * S, y + 7 * S], fill=fr)
        x, y = pt(r_back, sgn * half_w)
        d.ellipse([x - 2.5 * S, y - 2.5 * S, x + 2.5 * S, y + 2.5 * S], fill=fr)
    cv.paste(crop.convert("RGBA"), (box[0], box[1]))


def render_frame(t):
    sim = STATIC["sim"]
    th0 = sim["th0"]
    play_t = min(t, T_END)
    cv = STATIC["bg"].copy()
    th = ring_angle(play_t, th0)
    ga = half_angle(play_t)
    glow_col, glow_amt = (255, 255, 255), 0.0
    for tg, i, m in sim["goals"]:
        if 0 <= t - tg < 1.1:
            glow_col, glow_amt = TEAMS[i]["light"], (1 - ease_io((t - tg) / 1.1)) * 0.9
    final = t >= T_END
    winner = 0 if sim["score"][0] > sim["score"][1] else 1
    if final:
        fa = ease_io((t - T_END) / 1.2)
        glow_col, glow_amt = TEAMS[winner]["light"], max(glow_amt, 0.75 * fa)
    for tg, i, m in sim["goals"]:
        tau = t - tg
        if 0 <= tau < 1.2:
            a = ease_out(tau / 0.15) * (1 - ease_io((tau - 0.55) / 0.65))
            sc = 0.82 + 0.3 * ease_out(tau / 0.5)
            im = scale_img(cached_text("GOAL", 150, TEAMS[i]["light"], True), sc)
            put_center(cv, fade_img(im, a * 0.8), CX, CY - 10)
    draw_ring_and_goal(cv, th, ga, glow_col, glow_amt)
    d = ImageDraw.Draw(cv)
    for gi, (tg, i, m) in enumerate(sim["goals"]):
        tau = t - tg
        if 0 <= tau < 2.2:
            thg = ring_angle(tg, th0)
            ox = CX + (RA + 30) * math.cos(thg)
            oy = CY + (RA + 30) * math.sin(thg)
            pcs = confetti(100 + gi, 40, ox, oy, thg, 1.5, 260, 560, [TEAMS[i]["col"], TEAMS[i]["light"], (255, 255, 255), GOLD])
            draw_confetti(d, pcs, tau, life=2.0)
    if final:
        pcs = confetti(777, 220, 0, 0, 0, 0, 0, 0, [TEAMS[winner]["col"], TEAMS[winner]["light"], (255, 255, 255), GOLD], top=True)
        draw_confetti(d, pcs, t - T_END - 0.05, life=HOLD - 0.4, g=260.0, drag=0.3, ytop=True)
    shut = 0.5 / FPS
    ts = [play_t - shut * k / 3 for k in range(4)]
    for i in range(2):
        alpha, scale = 1.0, 1.0
        p, m = state_at(sim, play_t, i)
        if m == 2 and not (final and i == winner):
            continue
        if m == 1:
            tau = play_t - [g[0] for g in sim["goals"] if g[1] == i and g[0] <= play_t][-1]
            alpha = 1 - ease_io((tau - 0.55) / 0.45)
            scale = 1 - 0.08 * ease_io(tau / 0.3)
        sp_t = [s for s in sim["spawns"][i] if s <= play_t][-1]
        if sp_t > 0 and play_t - sp_t < 0.35:
            scale = 0.35 + 0.65 * ease_out((play_t - sp_t) / 0.35)
            alpha = min(alpha, ease_out((play_t - sp_t) / 0.2))
        if final:
            fa = ease_io((t - T_END - 0.2) / 1.0)
            if i == winner:
                q = p + (np.array([CX, CY]) - p) * fa if m != 2 else np.array([CX, CY])
                sp = scale_img(STATIC["spr"][i], (1 + 0.55 * fa) * (1.0 if m != 2 else ease_out((t - T_END - 0.2) / 0.5)) + 1e-3)
                hl = STATIC["halo"][i]
                hl = hl.resize((int(hl.width * (1 + 0.7 * fa)), int(hl.height * (1 + 0.7 * fa))), Image.BILINEAR)
                tmp = Image.new("RGB", cv.size, (0, 0, 0))
                tmp.paste(hl, (int(q[0] * S - hl.width / 2), int(q[1] * S - hl.height / 2)))
                c = ImageChops.add(cv.convert("RGB"), Image.eval(tmp, lambda v: int(v * 0.35))).convert("RGBA")
                c.alpha_composite(sp, (int(q[0] * S - sp.width / 2), int(q[1] * S - sp.height / 2)))
                cv = c
                continue
            alpha = 1 - 0.8 * fa
            draw_ball(cv, i, [play_t], sim, alpha=alpha, scale=scale)
            continue
        draw_ball(cv, i, ts if m == 0 else [play_t], sim, alpha=alpha, scale=scale)
    # ---- header
    sc = score_at(sim, t if not final else T_END)
    m_ = minute(play_t)
    qq = cached_text("Who wins?", 120, (246, 246, 252))
    if final:
        q = cached_text(TEAMS[winner]["name"] + " WINS", 84 if winner == 1 else 104, TEAMS[winner]["light"])
        qa = ease_out((t - T_END - 0.3) / 0.35)
        put_center(cv, fade_img(scale_img(q, 0.85 + 0.15 * qa), qa), W / 2, 150)
        put_center(cv, fade_img(qq, 1 - qa), W / 2, 150)
    else:
        put_center(cv, qq, W / 2, 150)
    parts = [("Chelsea", TEAMS[0]["light"]), ("vs", (200, 206, 225)), ("Man United", TEAMS[1]["light"])]
    ims = [cached_text(tx, 52, c, False) for tx, c in parts]
    gap = 26 * S
    wt = sum(im.width - 60 for im in ims) + gap * 2
    x = W * S / 2 - wt / 2
    for im in ims:
        cv.alpha_composite(im, (int(x - 30), int(262 * S - im.height / 2)))
        x += im.width - 60 + gap
    pop = [0, 0]
    for tg, i, _ in sim["goals"]:
        if 0 <= t - tg < 0.7:
            pop[i] = ease_out((t - tg) / 0.12) * (1 - ease_io((t - tg - 0.12) / 0.58))
    sy = 400
    for i, xx in ((0, 400), (1, 680)):
        col = lerp((250, 250, 255), TEAMS[i]["light"], pop[i])
        im = scale_img(cached_text(str(sc[i]), 190, col), 1 + 0.38 * pop[i])
        put_center(cv, im, xx, sy)
    put_center(cv, cached_text("-", 150, (170, 180, 210)), 540, sy + 6)
    put_center(cv, cached_text("CHE", 54, TEAMS[0]["light"], False), 205, sy + 6)
    put_center(cv, cached_text("MUN", 54, TEAMS[1]["light"], False), 875, sy + 6)
    gold_a = clamp((m_ - 80) / 10)
    ccol = lerp((225, 230, 245), GOLD, gold_a)
    if final:
        put_center(cv, cached_text("FULL TIME", 70, GOLD), 540, 535)
    else:
        ctext = f"{int(m_)}'" if m_ < 90 else f"90+{int(m_ - 90) + 1}'"
        cells = [30 if ch == "'" else 56 if ch != '+' else 50 for ch in ctext]
        x0 = 540 - sum(cells) / 2
        for ch, cell in zip(ctext, cells):
            put_center(cv, cached_text(ch, 78, ccol), x0 + cell / 2, 535)
            x0 += cell
    bx0, bx1, by = 290, 790, 600
    dd = ImageDraw.Draw(cv)
    dd.rounded_rectangle([bx0 * S, (by - 5) * S, bx1 * S, (by + 5) * S], radius=5 * S, fill=(40, 52, 86, 255))
    prog = clamp(m_ / 93.0) if not final else 1.0
    if prog > 0.01:
        fc = lerp((140, 170, 255), GOLD, gold_a) if not final else GOLD
        dd.rounded_rectangle([bx0 * S, (by - 5) * S, (bx0 + (bx1 - bx0) * prog) * S, (by + 5) * S], radius=5 * S, fill=fc + (255,))
    wm = STATIC["wm"]
    cv.alpha_composite(wm, (int(W * S / 2 - wm.width / 2), int(1760 * S)))
    return cv.convert("RGB").resize((W, H), Image.LANCZOS)


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


def whistle(dur):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    ph = 2 * math.pi * 2850 * tt + 5.0 * np.sin(2 * math.pi * 32 * tt)
    s = np.sin(ph) + 0.35 * np.sin(2 * ph)
    e = np.minimum(1, tt / 0.012) * np.minimum(1, np.maximum(0, (dur - tt) / 0.03))
    rng = np.random.default_rng(3)
    return (s + band(rng.normal(0, 1, n), 2500, 5000) * 0.25) * e


def crowd(dur, a, r, lo=350, hi=3200, seed=0):
    n = int(dur * SR)
    rng = np.random.default_rng(seed)
    x = band(rng.normal(0, 1, n), lo, hi)
    x /= np.max(np.abs(x)) + 1e-9
    tt = np.arange(n) / SR
    e = np.minimum(1, tt / a) * np.exp(-np.maximum(0, tt - a) / r)
    return x * e


def synth_audio(sim, path):
    total = total_time()
    n = int(total * SR) + SR
    dry = np.zeros(n)
    rng = np.random.default_rng(5)
    step = [4, 9]
    last = -1
    add(dry, 0.03, whistle(0.20), 0.16)
    for t, i, strength in sim["hits"]:
        if t - last < 0.03:
            continue
        last = t
        step[i] = int(np.clip(step[i] + rng.choice([-2, -1, 1, 2]), 0 if i == 0 else 5, 9 if i == 0 else 14))
        add(dry, t, tone(note_freq(step[i]), 0.75, r=0.30), 0.20 * strength)
        add(dry, t, sweep(420, 140, 0.07, r=0.03), 0.10)
    for t, s_ in sim["clashes"]:
        add(dry, t, sweep(150, 55, 0.18, a=0.002, r=0.07), 0.45)
        add(dry, t, band(rng.normal(0, 1, int(0.05 * SR)), 1200, 6000) * env(int(0.05 * SR), 0.001, 0.012), 0.12)
    for gi, (t, i, m) in enumerate(sim["goals"]):
        notes = [523.25, 659.25, 783.99, 1046.5] if i == 0 else [587.33, 739.99, 880.0, 1174.66]
        sw = band(rng.normal(0, 1, int(0.3 * SR)), 1500, 7000) * env(int(0.3 * SR), 0.01, 0.1)
        add(dry, t - 0.02, sw, 0.14)
        add(dry, t, sweep(120, 45, 0.5, a=0.003, r=0.2), 0.55)
        add(dry, t, crowd(2.4, 0.35, 0.9, seed=10 + gi), 0.34)
        for k, f in enumerate(notes):
            add(dry, t + 0.06 + 0.075 * k, tone(f, 1.1, r=0.35), 0.17)
    t_h = T90 - 5.0
    while t_h < T_END - 0.2:
        prog = (t_h - (T90 - 5.0)) / 8.0
        add(dry, t_h, sweep(95, 48, 0.18, a=0.003, r=0.06), 0.28 + 0.2 * prog)
        add(dry, t_h + 0.16, sweep(85, 45, 0.16, a=0.003, r=0.05), 0.18 + 0.1 * prog)
        t_h += 0.66 - 0.22 * prog
    rn = int(4.0 * SR)
    x = np.linspace(0, 1, rn)
    noise = rng.normal(0, 1, rn)
    riser = np.zeros(rn)
    for k in range(8):
        seg = slice(k * rn // 8, (k + 1) * rn // 8)
        lo = 400 + 600 * k
        riser[seg] = band(noise[seg], lo, lo * 3)[: (seg.stop - seg.start)]
    riser = riser * x ** 2.2 * 0.12 + sweep(220, 880, 4.0, a=1.5, r=99) * x ** 2 * 0.06
    add(dry, T_END - 4.0, riser, 1.0)
    for off, dur in ((0.0, 0.22), (0.36, 0.22), (0.72, 0.8)):
        add(dry, T_END + off, whistle(dur), 0.22)
    add(dry, T_END + 0.9, crowd(4.0, 0.6, 1.7, seed=77), 0.42)
    chord = sum(tone(f, 4.5, a=0.02, r=1.6, parts=((1, 1), (2, 0.4), (3, 0.15), (4, 0.06)))
                for f in (261.63, 329.63, 392.0, 523.25, 659.25, 783.99))
    add(dry, T_END + 1.0, chord, 0.20)
    add(dry, T_END + 1.0, sweep(70, 40, 1.0, a=0.003, r=0.4), 0.6)
    for k, f in enumerate((1046.5, 1318.5, 1568.0, 2093.0, 1568.0, 2093.0, 2637.0)):
        add(dry, T_END + 1.0 + 0.09 * k, tone(f, 1.2, a=0.002, r=0.35, parts=((1, 1), (2.76, 0.25))), 0.10)
    add(dry, T_END + 1.1, band(rng.normal(0, 1, int(2.5 * SR)), 5000, 14000) * env(int(2.5 * SR), 0.05, 0.6), 0.05)
    tt = np.arange(n) / SR
    mins = np.interp(tt, tt[::441], np.array([minute(min(x_, T_END)) for x_ in tt[::441]])) / 93.0
    bed = band(rng.normal(0, 1, n), 250, 1800)
    bed = bed / np.max(np.abs(bed)) * (0.02 + 0.07 * mins ** 1.5) * (0.8 + 0.2 * np.sin(2 * math.pi * 0.3 * tt))
    pad = np.zeros(n)
    for f, g in ((130.81, 1.0), (196.0, 0.7), (261.63, 0.6), (329.63, 0.4)):
        pad += g * (np.sin(2 * math.pi * f * tt) + 0.5 * np.sin(2 * math.pi * f * 1.003 * tt + 1.0))
    pad = pad / 3.0 * (0.02 + 0.05 * mins ** 2) * np.clip(tt / 0.6, 0, 1)
    irn = int(1.6 * SR)
    ir = band(rng.normal(0, 1, irn) * np.exp(-np.arange(irn) / (0.32 * SR)), 200, 9000)
    ir /= np.sqrt(np.sum(ir ** 2))
    L = 1 << int(math.ceil(math.log2(n + irn)))
    wet = np.fft.irfft(np.fft.rfft(dry, L) * np.fft.rfft(ir, L), L)[:n]
    mix = (dry + 0.22 * wet + bed + pad)[: int(total * SR)]
    fo = int(0.6 * SR)
    mix[-fo:] *= np.linspace(1, 0.0, fo) ** 1.5
    mix = np.tanh(mix * 1.1) / 1.1
    mix *= 10 ** (-1 / 20) / np.max(np.abs(mix))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())


# ---------------------------------------------------------------- cli
def worker_init(seed):
    init_static()
    STATIC["sim"] = simulate(seed)


def render_bytes(fi):
    return render_frame(fi / FPS).tobytes()


def _job(sd):
    s = simulate(sd)
    return sd, seed_ok(s), summary(s)


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
            for sd, ok, sm in p.imap(_job, range(a.search)):
                if ok:
                    print(sd, sm, flush=True)
    elif a.audio:
        synth_audio(simulate(a.seed), a.audio)
    elif a.frames:
        worker_init(a.seed)
        total = total_time()
        os.makedirs(a.outdir, exist_ok=True)
        for tok in a.frames.split(","):
            v = float(tok)
            vt = v * total if v <= 1 else v
            render_frame(vt).save(os.path.join(a.outdir, f"k_{vt:06.2f}.png"))
            print("frame", round(vt, 2), "/", round(total, 2), flush=True)
    elif a.out:
        worker_init(a.seed)
        nfr = int(round(total_time() * FPS))
        wav = a.out + ".wav"
        synth_audio(STATIC["sim"], wav)
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
        print(summary(s), seed_ok(s), "video", round(total_time(), 1), "s")
