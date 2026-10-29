#!/usr/bin/env python3
"""Hot Ball vs 200 Rubber Bands — a red hot metal ball rests on a stack of stretched rubber bands.
It burns through them one by one; every band it breaks makes it hotter, so it burns faster.
Payoff: band 200 snaps, the white-hot ball plunges into water -> steam burst, the ball cools down.

Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS down to 1080x1920, 60 fps.
Audio fully synthesized (pentatonic plucks on every snap, thumps, sizzle, riser, steam payoff), -1 dBFS.

    python3.13 hot-ball-bands.py --sim                       # timeline check, no render
    python3.13 hot-ball-bands.py --frames 0,0.2,0.4,0.6,0.8,0.97 --outdir keys/
    python3.13 hot-ball-bands.py --out video.mp4
"""
import argparse, math, os, subprocess, tempfile, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, S = 1080, 1920, 60, 2
SR = 44100
SUB = 20                                  # physics substeps per frame (1200 Hz)
DT = 1.0 / (FPS * SUB)

N_BANDS = 200
CX = 540.0
RAIL_L, RAIL_R = 160.0, 920.0
SP = 72.0                                 # spacing between bands (world px)
Y0 = 1000.0                               # world y of band 0
BALL_R = 84.0
BAND_W = 15.0
G = 3600.0
K_BAND, C_BAND = 128.0, 8.0               # band spring (per unit mass) and damping
V_CAP = 1300.0
BALL_SCREEN_Y = 800.0
T_START, T_END, TAU = 0.72, 0.04, 9.0     # burn time per band: T_END + (T_START-T_END)*exp(-k/TAU)
WATER_GAP = 240.0                         # last band -> water surface
BASIN_DEPTH = 520.0
HOLD = 4.2                                # seconds after the splash

BG_TOP, BG_BOT = np.array([16, 18, 30.]), np.array([6, 7, 12.])
BAND_COLS = [np.array(c, float) for c in ((64, 222, 204), (138, 112, 255), (255, 102, 178))]
GOLD = (255, 200, 72)

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


def band_y(k):
    return Y0 + k * SP


def burn_time(k):
    return T_END + (T_START - T_END) * math.exp(-k / TAU)


def band_color(k):
    return BAND_COLS[k % 3]                          # teal / violet / pink, repeating


HEAT_STOPS = [(0.0, (120, 18, 6)), (0.25, (225, 52, 14)), (0.5, (255, 118, 28)),
              (0.75, (255, 186, 80)), (1.0, (255, 244, 214))]


def heat_rgb(h):
    h = clamp(h)
    for (a, ca), (b, cb) in zip(HEAT_STOPS, HEAT_STOPS[1:]):
        if h <= b:
            u = (h - a) / (b - a)
            return np.array(ca, float) * (1 - u) + np.array(cb, float) * u
    return np.array(HEAT_STOPS[-1][1], float)


# ---------------------------------------------------------------- band geometry
def wrap_path(k, yb, n_arc=22):
    """Polyline of band k pushed down by the ball (or straight). Returns (points, contact)."""
    yk = band_y(k)
    rho = BALL_R + BAND_W * 0.5
    depth = yb + rho - yk
    if depth <= 0:
        return [(RAIL_L, yk), (RAIL_R, yk)], False
    c = np.array([CX, yb])
    pts = []
    tang = []
    for px in (RAIL_L, RAIL_R):
        p = np.array([px, yk])
        d = np.linalg.norm(p - c)
        th0 = math.atan2(p[1] - c[1], p[0] - c[0])
        beta = math.acos(clamp(rho / d, -1, 1))
        cands = [th0 + beta, th0 - beta]
        a = max(cands, key=lambda a: math.sin(a))      # lower tangent (y down)
        tang.append(a)
    aL, aR = tang
    aL = aL % (2 * math.pi)
    aR = aR % (2 * math.pi)
    if aR > aL:
        aR -= 2 * math.pi
    pts.append((RAIL_L, yk))
    for i in range(n_arc + 1):
        a = aL + (aR - aL) * i / n_arc
        pts.append((CX + rho * math.cos(a), yb + rho * math.sin(a)))
    pts.append((RAIL_R, yk))
    return pts, True


def resample(path, n):
    p = np.array(path, float)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, cum[-1], n)
    return np.stack([np.interp(t, cum, p[:, 0]), np.interp(t, cum, p[:, 1])], 1), cum[-1]


# ---------------------------------------------------------------- simulation
HALF_N = 10
HALF_REST = 34.0


def simulate():
    rng = np.random.default_rng(29)
    yb = band_y(0) - BALL_R - 5.0 + 28.0      # start already pressed into band 0
    vb = 0.0
    k = 0
    contact_t = 0.0
    cam = yb - BALL_SCREEN_Y
    camv = 0.0
    t = 0.0
    frames = []
    events = []            # (time, kind, value)
    halves = []            # dict: pos, vel, born, settled, k, side
    smoke = []             # (t0, x, y, vx, vy, life, size)
    sparks = []            # (t0, x, y, vx, vy, life)
    splash_t = None
    in_contact_prev = False
    water_y = band_y(N_BANDS - 1) + WATER_GAP
    basin_floor = water_y + BASIN_DEPTH
    cam_max = water_y - 1000.0
    heat = 0.0
    end_t = None
    for i in range(40):
        side = 1 if i % 2 else -1
        ang = math.pi * (0.5 - side * (0.55 + 0.15 * rng.random()))
        smoke.append((-rng.uniform(0, 2.2), CX + (BALL_R + 4) * math.cos(ang), yb + (BALL_R + 4) * math.sin(ang),
                      side * rng.uniform(5, 30), -rng.uniform(60, 120), rng.uniform(1.6, 2.6), rng.uniform(16, 26)))
    fi = 0
    while True:
        for s in range(SUB):
            # --- ball
            if splash_t is None:
                acc = G
                depth = 0.0
                if k < N_BANDS:
                    depth = yb + BALL_R + BAND_W * 0.5 - band_y(k)
                    if depth > 0:
                        acc -= K_BAND * depth + C_BAND * vb
                        if not in_contact_prev:
                            events.append((t, "land", abs(vb)))
                        in_contact_prev = True
                        contact_t += DT
                        if contact_t >= burn_time(k) or depth > SP - 14:
                            snap_band(k, yb, t, halves, sparks, rng)
                            events.append((t, "snap", k))
                            k += 1
                            contact_t = 0.0
                            in_contact_prev = False
                            vb = min(vb * 0.92, V_CAP)
                    else:
                        in_contact_prev = False
                vb += acc * DT
                yb += vb * DT
                if k >= N_BANDS and yb + BALL_R >= water_y:
                    splash_t = t
                    events.append((t, "splash", vb))
                    spawn_splash(t, yb, sparks, smoke, rng)
            else:
                # sinking in water: heavy drag, rests on basin floor
                vb += (G * 0.35 - 6.0 * vb) * DT
                yb += vb * DT
                if yb + BALL_R > basin_floor - 6:
                    yb = basin_floor - 6 - BALL_R
                    vb = 0.0
            # heat: driven by bands broken, cools in water
            target = min(1.0, (k / N_BANDS) ** 0.8)
            if splash_t is None:
                heat += (target - heat) * min(1.0, DT * 3.0)
            else:
                heat = max(0.0, heat - DT / 1.6)
            t += DT
            if s % 5 == 0 and not os.environ.get("NOHALVES"):
                step_halves(halves, t, DT * 5)
        # smoke from contact points
        if splash_t is None and k < N_BANDS:
            pts, contact = wrap_path(k, yb)
            if contact:
                frac = clamp(contact_t / burn_time(k))
                rate = 1.2 + 3.0 * frac
                for side in (1, -1):
                    if rng.random() < rate * 0.5:
                        ang = math.pi * (0.5 - side * (0.55 + 0.15 * rng.random()))
                        x = CX + (BALL_R + 4) * math.cos(ang)
                        y = yb + (BALL_R + 4) * math.sin(ang)
                        smoke.append((t, x, y, side * rng.uniform(5, 30), -rng.uniform(60, 120),
                                      rng.uniform(1.6, 2.6), rng.uniform(16, 26)))
        if splash_t is not None:
            ts = t - splash_t
            n = 6 * math.exp(-ts / 0.45) + 1.0 * math.exp(-ts / 2.5)
            n = int(n) + (1 if rng.random() < n % 1 else 0)
            for _ in range(n):
                x = CX + rng.normal(0, 70 + 90 * min(ts, 1.5))
                big = ts < 0.8
                smoke.append((t, x, water_y - rng.uniform(0, 25), rng.normal(0, 50),
                              -rng.uniform(200, 480) if big else -rng.uniform(60, 140),
                              rng.uniform(2.0, 3.2), rng.uniform(40, 75) if big else rng.uniform(22, 36)))
        # camera: critically damped follow, clamped at the basin
        target = min(yb - BALL_SCREEN_Y, cam_max)
        w = 7.0
        a = w * w * (target - cam) - 2 * w * camv
        camv += a / FPS
        cam += camv / FPS
        frames.append(dict(t=t, yb=yb, k=k, contact_t=contact_t, cam=cam, heat=heat,
                           splash=splash_t,
                           halves=[(h["k"], h["side"], h["pos"].astype(np.float32).copy())
                                   for h in halves if not h["settled"]]))
        fi += 1
        if splash_t is not None and end_t is None:
            end_t = splash_t + HOLD
        if end_t is not None and t >= end_t:
            break
        if t > 90:
            raise RuntimeError("simulation did not finish")
    # settled halves: keep their final shape for the rest of the video
    finals = {}
    for h in halves:
        finals[(h["k"], h["side"])] = (h["settle_frame_t"], h["pos"].astype(np.float32).copy())
    return dict(frames=frames, events=events, smoke=smoke, sparks=sparks, finals=finals,
                halves_born=[(h["k"], h["side"], h["born"]) for h in halves],
                water_y=water_y, basin_floor=basin_floor, splash=splash_t, duration=t)


def snap_band(k, yb, t, halves, sparks, rng):
    pts, _ = wrap_path(k, yb)
    pts = np.array(pts)
    mid = len(pts) // 2
    left = pts[:mid + 1]
    right = pts[mid:][::-1]
    for side, path in ((-1, left), (1, right)):
        pos, length = resample(path, HALF_N)
        tang = pos[1:] - pos[:-1]
        vel = np.zeros_like(pos)
        halves.append(dict(k=k, side=side, pos=pos, prev=pos.copy(), vel=vel, born=t,
                           settled=False, settle_frame_t=None,
                           rest=HALF_REST / (HALF_N - 1)))
    bx, by = CX, yb + BALL_R
    for _ in range(5):
        a = rng.uniform(math.pi * 1.1, math.pi * 1.9)
        sp = rng.uniform(250, 600)
        sparks.append((t, bx + rng.normal(0, 10), by, sp * math.cos(a), sp * math.sin(a) * 0.8,
                       rng.uniform(0.35, 0.7)))


def step_halves(halves, t, dt):
    ks, damp = 20000.0, 3.2
    for h in halves:
        if h["settled"]:
            continue
        p, v = h["pos"], h["vel"]
        f = np.zeros_like(p)
        f[:, 1] += G * 0.5
        d = p[1:] - p[:-1]
        L = np.linalg.norm(d, axis=1, keepdims=True) + 1e-6
        u = d / L
        fs = ks * (L - h["rest"]) * u
        f[:-1] += fs
        f[1:] -= fs
        # bending stiffness: pull each inner point toward the midpoint of its neighbours
        f[1:-1] += 900.0 * ((p[:-2] + p[2:]) * 0.5 - p[1:-1])
        f -= damp * v
        # substeps for the stiff springs
        sub = 8
        for _ in range(sub):
            v += f * (dt / sub)
            v[0] = 0
            p += v * (dt / sub)
            d = p[1:] - p[:-1]
            L = np.linalg.norm(d, axis=1, keepdims=True) + 1e-6
            u = d / L
            f = np.zeros_like(p)
            f[:, 1] += G * 0.5
            fs = ks * (L - h["rest"]) * u
            f[:-1] += fs
            f[1:] -= fs
            f[1:-1] += 900.0 * ((p[:-2] + p[2:]) * 0.5 - p[1:-1])
            f -= damp * v
        # keep stubs on the inner side of their rail
        if h["side"] < 0:
            p[:, 0] = np.maximum(p[:, 0], RAIL_L - 2)
        else:
            p[:, 0] = np.minimum(p[:, 0], RAIL_R + 2)
        if t - h["born"] > 2.5 and np.abs(v).max() < 3:
            h["settled"] = True
            h["settle_frame_t"] = t


def spawn_splash(t, yb, sparks, smoke, rng):
    for _ in range(26):
        a = rng.uniform(math.pi * 1.15, math.pi * 1.85)
        sp = rng.uniform(400, 1000)
        sparks.append((t, CX + rng.normal(0, 30), yb + BALL_R * 0.6, sp * math.cos(a), sp * math.sin(a),
                       rng.uniform(0.5, 0.9), "drop"))


# ---------------------------------------------------------------- rendering helpers
def make_bg():
    y = np.linspace(0, 1, H * S)[:, None, None]
    col = BG_TOP * (1 - y) + BG_BOT * y
    img = np.broadcast_to(col, (H * S, W * S, 3)).copy()
    xx = np.linspace(-1, 1, W * S)[None, :]
    yy = np.linspace(-1, 1, H * S)[:, None]
    vig = 1 - 0.28 * np.clip((xx ** 2 * 0.8 + yy ** 2 * 0.5), 0, 1)
    img *= vig[:, :, None]
    # faint warm glow behind the ball zone
    d = np.sqrt((xx * W / H) ** 2 + (yy - (BALL_SCREEN_Y / H * 2 - 1)) ** 2)
    img += np.array([10, 4, 2.])[None, None, :] * np.exp(-(d / 0.55) ** 2)[:, :, None]
    return img.astype(np.float32)


def rail_strip(width):
    w = int(width * S)
    x = np.linspace(-1, 1, w)
    shade = 0.35 + 0.65 * np.clip(1 - x ** 2, 0, 1) ** 0.6
    hl = np.exp(-((x + 0.35) / 0.12) ** 2) * 0.5
    base = np.array([92, 98, 116.])
    col = base[None, :] * shade[:, None] + 255 * hl[:, None] * 0.6
    return np.clip(col, 0, 255).astype(np.float32)


def soft_sprite(r):
    n = int(r * 2) + 1
    yy, xx = np.mgrid[0:n, 0:n] - r
    d = np.sqrt(xx ** 2 + yy ** 2) / max(r, 1)
    return np.clip(1 - d, 0, 1) ** 2


def add_glow(img, cx, cy, radius, color, strength):
    r = int(radius)
    x0, x1 = max(0, int(cx) - r), min(img.shape[1], int(cx) + r)
    y0, y1 = max(0, int(cy) - r), min(img.shape[0], int(cy) + r)
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (radius * 0.42) ** 2
    g = np.exp(-d2) * strength
    img[y0:y1, x0:x1] += g[:, :, None] * np.asarray(color, np.float32)[None, None, :]


def blend_soft(img, cx, cy, radius, color, alpha):
    """Translucent soft puff (normal blend, never saturates) for smoke and steam."""
    r = int(radius)
    x0, x1 = max(0, int(cx) - r), min(img.shape[1], int(cx) + r)
    y0, y1 = max(0, int(cy) - r), min(img.shape[0], int(cy) + r)
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (radius * 0.45) ** 2
    a = (np.exp(-d2) * alpha)[:, :, None]
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - a) + np.asarray(color, np.float32)[None, None, :] * a


_tex_cache = {}


def ball_texture(n):
    if n not in _tex_cache:
        rng = np.random.default_rng(7)
        small = rng.random((9, 9))
        im = Image.fromarray((small * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC)
        _tex_cache[n] = np.asarray(im, np.float32) / 255.0
    return _tex_cache[n]


def draw_ball(img, cx, cy, heat, cool):
    """Emissive hot metal ball; `cool` in [0,1] blends toward cold steel (after the water)."""
    R = BALL_R * S
    n = int(R * 2 + 6)
    x0, y0 = int(cx - n / 2), int(cy - n / 2)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    dx = (xx + x0 - cx) / R
    dy = (yy + y0 - cy) / R
    d = np.sqrt(dx ** 2 + dy ** 2)
    alpha = np.clip((1 - d) * R * 0.9, 0, 1)
    nz = np.sqrt(np.clip(1 - d ** 2, 0, 1))
    tex = ball_texture(n)
    hv = 0.14 + 0.86 * heat
    hot = heat_rgb(hv)
    core = heat_rgb(min(1.0, hv + 0.35))
    # emissive: brighter at the centre, darker crusty rim, subtle mottling
    em = (0.55 + 0.45 * nz)[:, :, None]
    mott = (0.93 + 0.07 * tex)[:, :, None]
    col_hot = (hot[None, None, :] * (1 - nz[:, :, None] * 0.7) + core[None, None, :] * nz[:, :, None] * 0.7) * em * mott
    col_hot = col_hot * (1.0 + 0.35 * heat)
    # cold steel: lambert + specular from top-left
    lx, ly, lz = -0.45, -0.6, 0.66
    ndotl = np.clip(dx * lx + dy * ly + nz * lz, 0, 1)
    spec = np.clip(ndotl, 0, 1) ** 40
    steel = np.array([70, 76, 90.])
    col_cold = steel[None, None, :] * (0.25 + 0.85 * ndotl[:, :, None]) * mott + 255 * spec[:, :, None] * 0.85
    # small specular even when hot (glossy surface)
    col_hot = col_hot + 255 * (spec[:, :, None] * 0.35)
    col = col_hot * (1 - cool) + col_cold * cool
    X0, Y0 = max(0, x0), max(0, y0)
    X1, Y1 = min(img.shape[1], x0 + n), min(img.shape[0], y0 + n)
    sl = (slice(Y0 - y0, Y1 - y0), slice(X0 - x0, X1 - x0))
    a = alpha[sl][:, :, None]
    img[Y0:Y1, X0:X1] = img[Y0:Y1, X0:X1] * (1 - a) + col[sl] * a


def text_img(txt, px, fill, shadow=True):
    f = font(px * S)
    bb = f.getbbox(txt)
    w, h = bb[2] - bb[0] + 40, bb[3] - bb[1] + 40
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((20 - bb[0], 20 - bb[1]), txt, font=f, fill=fill)
    return im


def paste_text(base, im, cx, top, shadow=0.55):
    x = int(cx * S - im.width / 2)
    y = int(top * S)
    if shadow:
        a = np.asarray(im)[:, :, 3].astype(np.float32) * shadow
        sh = Image.fromarray(a.astype(np.uint8)).filter(__import__("PIL.ImageFilter").ImageFilter.GaussianBlur(10))
        black = Image.new("RGBA", im.size, (0, 0, 0, 255))
        black.putalpha(sh)
        base.alpha_composite(black, (x, y + 8))
    base.alpha_composite(im, (x, y))


# ---------------------------------------------------------------- frame renderer
SIM = None
STATIC = {}


def init_static():
    STATIC["bg"] = make_bg()
    STATIC["rail"] = rail_strip(22)
    f_q = 80
    STATIC["q1"] = text_img("Can a red hot ball", f_q, (245, 245, 250, 255))
    STATIC["q2"] = text_img("break 200 bands?", f_q, (245, 245, 250, 255))
    STATIC["wm"] = text_img("@novalabs.hq", 30, (255, 255, 255, 90))
    fnum = font(132 * S)
    STATIC["fnum"] = fnum
    STATIC["digw"] = max(fnum.getbbox(str(d))[2] - fnum.getbbox(str(d))[0] for d in range(10))
    STATIC["smoke_spr"] = {}


def counter_img(n, final_mix):
    """'37/200' with fixed-width digit cells so the number never jumps."""
    fnum = STATIC["fnum"]
    fsm = font(76 * S)
    dw = STATIC["digw"]
    s = str(n)
    big_w = dw * len(s)
    slash = "/200"
    sb = fsm.getbbox(slash)
    sw = sb[2] - sb[0]
    asc = fnum.getbbox("0")
    h = asc[3] - asc[1]
    W_ = big_w + 12 * S + sw + 40
    im = Image.new("RGBA", (int(W_), int(h + 60)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    white = np.array([255, 250, 244.])
    col = tuple(int(c) for c in white * (1 - final_mix) + np.array(GOLD, float) * final_mix) + (255,)
    for i, ch in enumerate(s):
        b = fnum.getbbox(ch)
        x = 20 + i * dw + (dw - (b[2] - b[0])) / 2 - b[0]
        d.text((x, 20 - asc[1]), ch, font=fnum, fill=col)
    dim = tuple(int(c) for c in np.array([150, 156, 178.]) * (1 - final_mix) + np.array(GOLD, float) * 0.8 * final_mix) + (255,)
    d.text((20 + big_w + 12 * S - sb[0], 20 + h - (sb[3]) + 2), slash, font=fsm, fill=dim)
    return im


def draw_polyline(d, pts, width, fill):
    d.line(pts, fill=fill, width=int(width), joint="curve")
    r = width / 2
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=fill)


def draw_band(d, pts, col, width, hotmix=None):
    pts = [(x * S, y * S) for x, y in pts]
    dark = tuple(int(c * 0.45) for c in col)
    draw_polyline(d, [(x, y + 2.2 * S) for x, y in pts], width * S, dark)
    draw_polyline(d, pts, width * S * 0.86, tuple(int(c) for c in col))
    hl = tuple(int(min(255, c * 0.6 + 110)) for c in col)
    draw_polyline(d, [(x, y - width * 0.22 * S) for x, y in pts], max(2, width * S * 0.22), hl)


def render_frame(fi):
    sim = SIM
    fr = sim["frames"][fi]
    t, cam, yb, k = fr["t"], fr["cam"], fr["yb"], fr["k"]
    img = STATIC["bg"].copy()
    # rails
    rail = STATIC["rail"]
    for x in (RAIL_L, RAIL_R):
        xs = int(x * S - rail.shape[0] / 2)
        img[:, xs:xs + rail.shape[0]] = rail[None, :, :]
    base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def sy(y):
        return y - cam

    # pegs for every band in view
    kmin = max(0, int((cam - 200 - Y0) / SP))
    kmax = min(N_BANDS - 1, int((cam + H + 200 - Y0) / SP) + 1)
    for kk in range(kmin, kmax + 1):
        yk = sy(band_y(kk))
        for x in (RAIL_L, RAIL_R):
            r = 9 * S
            d.ellipse([x * S - r, yk * S - r, x * S + r, yk * S + r], fill=(48, 52, 64, 255))
            r2 = 5 * S
            d.ellipse([x * S - r2 - 2 * S, yk * S - r2 - 2 * S, x * S + r2 - 2 * S, yk * S + r2 - 2 * S],
                      fill=(150, 156, 172, 255))
    # snapped halves (settled ones use their final shape)
    active = {(kk, sd): pos for kk, sd, pos in fr["halves"]}
    for kk in range(kmin, min(k, kmax + 1)):
        for sd in (-1, 1):
            pos = active.get((kk, sd))
            if pos is None:
                fin = sim["finals"].get((kk, sd))
                if fin is None:
                    continue
                pos = fin[1]
            col = band_color(kk)
            pts = [(float(x), float(y) - cam) for x, y in pos]
            draw_band(d, pts, col, BAND_W * 0.95)
    # intact bands
    for kk in range(max(k, kmin), kmax + 1):
        col = band_color(kk)
        if kk == k and fr["splash"] is None:
            pts, contact = wrap_path(kk, yb)
            frac = clamp(fr["contact_t"] / burn_time(kk)) if contact else 0.0
            w = BAND_W * (1 - 0.45 * frac ** 1.5)
            if contact:
                hot = heat_rgb(0.4 + 0.6 * frac)
                # mix heat into the arc part only: draw full band, then hot arc on top
                draw_band(d, [(x, sy(y)) for x, y in pts], col, w)
                arc = [(x * S, sy(y) * S) for x, y in pts[1:-1]]
                hc = tuple(int(c) for c in (col * (1 - 0.5 - 0.5 * frac) + hot * (0.5 + 0.5 * frac)))
                draw_polyline(d, arc, w * S * 0.7, hc)
            else:
                draw_band(d, [(x, sy(y)) for x, y in pts], col, w)
        else:
            yk = sy(band_y(kk))
            draw_band(d, [(RAIL_L, yk), (RAIL_R, yk)], col, BAND_W)
    # basin + water
    wy = sy(sim["water_y"])
    fy = sy(sim["basin_floor"])
    water_layer = None
    if wy < H + 50:
        bl, br = RAIL_L + 30, RAIL_R - 30
        st = sim["splash"]
        pts = []
        for i in range(61):
            x = bl + (br - bl) * i / 60
            yw = wy
            if st is not None and t > st:
                tt = t - st
                dist = abs(x - CX)
                yw += 18 * math.exp(-tt * 1.6) * math.sin(dist / 34 - tt * 11) * math.exp(-dist / 380)
            pts.append((x * S, yw * S))
        # water is composited over the ball later (so the ball looks submerged)
        water_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        wd = ImageDraw.Draw(water_layer)
        wd.polygon(pts + [(br * S, fy * S), (bl * S, fy * S)], fill=(255, 255, 255, 255))
        ry0 = max(0, int((wy - 30) * S))
        ry1 = min(H * S, int((fy + 4) * S))
        mask = np.asarray(water_layer)[ry0:ry1, :, 3].astype(np.float32) / 255
        yy = np.arange(ry0, ry1, dtype=np.float32)[:, None]
        depth = np.clip((yy - wy * S) / ((fy - wy) * S), 0, 1)
        wcol = np.stack([28 + 0 * depth, 92 - 40 * depth, 168 - 70 * depth], -1)
        water_layer = (mask, wcol, pts, bl, br, wy, fy, ry0, ry1)
        # glass walls + floor behind
        gl = (190, 205, 230, 160)
        d.line([(bl * S, (wy - 70) * S), (bl * S, fy * S), (br * S, fy * S), (br * S, (wy - 70) * S)],
               fill=gl, width=int(6 * S), joint="curve")
    base.alpha_composite(layer)
    arr = np.asarray(base.convert("RGB"), np.float32).copy()

    # ball glow + ball (with motion blur from screen-space velocity)
    heat = fr["heat"]
    cool = 0.0
    if fr["splash"] is not None:
        cool = clamp((t - fr["splash"]) / 1.6) ** 0.8
        heat_vis = heat
    else:
        heat_vis = heat
    glow_c = heat_rgb(min(1, 0.2 + 0.8 * heat_vis))
    gs = (0.28 + 0.55 * heat_vis) * (1 - cool)
    bys = sy(yb)
    if gs > 0.01:
        add_glow(arr, CX * S, bys * S, (300 + 260 * heat_vis) * S, glow_c * 0.9, gs)
    prev = sim["frames"][max(0, fi - 1)]
    vy_screen = (yb - prev["yb"]) - (cam - prev["cam"])
    if abs(vy_screen) > 3:
        # motion blur: average 4 sub-positions, computed on the ball's strip only
        pad = int((BALL_R + abs(vy_screen) + 8) * S)
        y0 = max(0, int(bys * S) - pad)
        y1 = min(H * S, int(bys * S) + pad)
        x0, x1 = int((CX - BALL_R - 8) * S), int((CX + BALL_R + 8) * S)
        region = arr[y0:y1, x0:x1]
        acc = np.zeros_like(region)
        for j in range(4):
            tmp = region.copy()
            draw_ball(tmp, CX * S - x0, (bys - vy_screen * (j / 4.0 - 0.375)) * S - y0, heat_vis, cool)
            acc += tmp
        arr[y0:y1, x0:x1] = acc / 4
    else:
        draw_ball(arr, CX * S, bys * S, heat_vis, cool)
    if gs > 0.01:
        add_glow(arr, CX * S, bys * S, 190 * S, heat_rgb(1.0), 0.16 * gs)
    if fr["splash"] is None and k < N_BANDS:
        _, contact = wrap_path(k, yb)
        if contact:
            frac = clamp(fr["contact_t"] / burn_time(k))
            add_glow(arr, CX * S, (bys + BALL_R) * S, (40 + 50 * frac) * S, heat_rgb(0.9), 0.5 + 0.8 * frac)

    # sparks / droplets
    for sp in sim["sparks"]:
        t0, x, y, vx, vy, life = sp[:6]
        drop = len(sp) > 6
        tt = t - t0
        if tt < 0 or tt > life:
            continue
        px = x + vx * tt
        py = y + vy * tt + 0.5 * G * 0.8 * tt * tt
        py = py - cam
        fade = 1 - tt / life
        if drop:
            add_glow(arr, px * S, py * S, 22 * S, np.array([170, 215, 255.]), 0.9 * fade)
        else:
            add_glow(arr, px * S, py * S, 13 * S, heat_rgb(0.85), 0.9 * fade)
    # water over the ball
    if water_layer is not None:
        mask, wcol, wpts, bl, br, wy_, fy_, ry0, ry1 = water_layer
        if ry1 > ry0:
            a = (mask * 0.55)[:, :, None]
            arr[ry0:ry1] = arr[ry0:ry1] * (1 - a) + wcol * a
            # bright surface line + faint glass reflection
            tmp = Image.new("RGBA", (W * S, ry1 - ry0), (0, 0, 0, 0))
            td = ImageDraw.Draw(tmp)
            td.line([(x, y - ry0) for x, y in wpts], fill=(170, 225, 255, 230), width=int(4 * S))
            td.line([(bl * S + 14 * S, (wy_ + 14) * S - ry0), (bl * S + 14 * S, (fy_ - 14) * S - ry0)],
                    fill=(255, 255, 255, 40), width=int(6 * S))
            ta = np.asarray(tmp, np.float32)
            al = ta[:, :, 3:4] / 255
            arr[ry0:ry1] = arr[ry0:ry1] * (1 - al) + ta[:, :, :3] * al
        if fr["splash"] is None or t - fr["splash"] < 2.5:
            glow = (1 - cool) * (0.2 + 0.6 * heat_vis)
            add_glow(arr, CX * S, bys * S, 260 * S, glow_c * 0.6, 0.35 * glow)
    # smoke / steam
    for (t0, x, y, vx, vy, life, size) in sim["smoke"]:
        tt = t - t0
        if tt < 0 or tt > life:
            continue
        u = tt / life
        px = x + vx * tt + 22 * math.sin(t0 * 7.3 + tt * 2.1) * u
        py = y + vy * tt * (1 - 0.35 * u) - cam
        r = size * (1 + 3.0 * u)
        a = 0.16 * math.sin(math.pi * min(1, u * 1.1))
        a *= clamp((py - 560) / 300)                 # dissolve before reaching the text zone
        blend_soft(arr, px * S, py * S, r * 2 * S, np.array([150, 156, 170.]), a)

    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    # UI: question, counter, bar, watermark
    paste_text(out, STATIC["q1"], W / 2, 112)
    paste_text(out, STATIC["q2"], W / 2, 210)
    st = sim["splash"]
    final_mix = 0.0 if st is None else ease_out((t - st) / 0.5)
    ci = counter_img(k, final_mix)
    # punch on change
    last_snap = max([e[0] for e in SNAPS_UNTIL(t)] or [-9])
    punch = 1 + 0.07 * math.exp(-(t - last_snap) * 18) + (0.18 * math.exp(-(t - st) * 4) if st and t > st else 0)
    if punch > 1.001:
        ci = ci.resize((int(ci.width * punch), int(ci.height * punch)), Image.LANCZOS)
    paste_text(out, ci, W / 2, 330 - (ci.height / S - 196) / 2)
    dd = ImageDraw.Draw(out)
    bw, bh, bx, byy = 620, 16, (W - 620) / 2, 520
    dd.rounded_rectangle([bx * S, byy * S, (bx + bw) * S, (byy + bh) * S], radius=bh * S / 2, fill=(40, 44, 62, 255))
    fillw = bw * k / N_BANDS
    if fillw > bh:
        c0 = heat_rgb(0.45 + 0.5 * k / N_BANDS)
        c = tuple(int(v) for v in (c0 * (1 - final_mix) + np.array(GOLD) * final_mix)) + (255,)
        dd.rounded_rectangle([bx * S, byy * S, (bx + fillw) * S, (byy + bh) * S], radius=bh * S / 2, fill=c)
    wm = STATIC["wm"]
    out.alpha_composite(wm, (int(W * S / 2 - wm.width / 2), int(1800 * S)))
    small = out.convert("RGB").resize((W, H), Image.LANCZOS)
    return small.tobytes()


_SNAP_T = None


def SNAPS_UNTIL(t):
    global _SNAP_T
    if _SNAP_T is None:
        _SNAP_T = np.array([e[0] for e in SIM["events"] if e[1] == "snap"])
    i = np.searchsorted(_SNAP_T, t, side="right")
    return [(_SNAP_T[i - 1],)] if i > 0 else []


def worker_init(sim):
    global SIM
    SIM = sim
    init_static()


# ---------------------------------------------------------------- audio
def adsr(n, a, r):
    e = np.ones(n)
    na = max(1, int(a * SR))
    e[:na] = np.linspace(0, 1, na)
    e *= np.exp(-np.arange(n) / (r * SR))
    return e


def add(buf, t, sig, gain=1.0):
    i = int(t * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[:j - i] * gain


PENTA = [0, 2, 4, 7, 9]


def note_freq(step, base=261.63):
    o, s = divmod(step, 5)
    return base * 2 ** ((12 * o + PENTA[s]) / 12)


def lowpass(x, a):
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a * (x[i] - acc)
        y[i] = acc
    return y


def onepole(x, fc):
    # vectorised-ish one-pole lowpass via scipy-free IIR (chunked python loop is too slow; use cumulative trick)
    a = math.exp(-2 * math.pi * fc / SR)
    y = np.zeros_like(x)
    prev = 0.0
    blk = int(max(16, min(4096, 40.0 / -math.log(a))))   # keep a**blk far from underflow
    for s in range(0, len(x), blk):
        seg = x[s:s + blk]
        # y[n] = (1-a) x[n] + a y[n-1]  -> solved with powers of a inside the block
        n = len(seg)
        pw = a ** np.arange(1, n + 1)
        acc = np.cumsum(seg * (1 - a) / pw) * pw
        acc += prev * pw
        y[s:s + n] = acc
        prev = acc[-1]
    return y


def synth_audio(sim, path):
    dur = sim["duration"] + 0.3
    n = int(dur * SR)
    L = np.zeros(n)
    R = np.zeros(n)
    rng = np.random.default_rng(3)
    snaps = [e for e in sim["events"] if e[1] == "snap"]
    snap_times = np.array([e[0] for e in snaps])
    for t, kind, val in sim["events"]:
        if kind == "snap":
            kk = int(val)
            # density-aware gain
            near = np.sum(np.abs(snap_times - t) < 0.5)
            g = 0.5 / math.sqrt(max(1.0, near / 3.0))
            step = 5 + int(kk * 10 / N_BANDS) + [0, 2, 1, 3, 2, 4][kk % 6]
            f = note_freq(step)
            m = int(0.55 * SR)
            tt = np.arange(m) / SR
            sig = (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * 2 * f * tt) * np.exp(-tt * 9)
                   + 0.12 * np.sin(2 * np.pi * 3 * f * tt) * np.exp(-tt * 14))
            sig *= adsr(m, 0.003, 0.16)
            # rubber "snap" transient: short bright noise click with soft attack
            cn = int(0.025 * SR)
            click = rng.normal(0, 1, cn)
            click = click - onepole(click, 1800)
            click *= adsr(cn, 0.0015, 0.006)
            pan = 0.5 + 0.25 * math.sin(kk * 1.7)
            add(L, t, sig, g * 0.55 * (1 - pan) * 2)
            add(R, t, sig, g * 0.55 * pan * 2)
            add(L, t, click, g * 0.5)
            add(R, t, click, g * 0.5)
        elif kind == "land":
            v = float(val)
            if v < 40:
                continue
            m = int(0.3 * SR)
            tt = np.arange(m) / SR
            f = 70 + 25 * math.exp(-0)
            sig = np.sin(2 * np.pi * (f * tt + 30 * (1 - np.exp(-tt * 20)) / 20)) * adsr(m, 0.004, 0.07)
            # rubbery stretch "boing" glide
            fb = 180
            boing = np.sin(2 * np.pi * (fb * tt - 40 * tt ** 2)) * adsr(m, 0.006, 0.09) * 0.35
            g = 0.35 * clamp(v / 600, 0.2, 1.0)
            add(L, t, sig + boing, g)
            add(R, t, sig + boing, g)
        elif kind == "splash":
            m = int(4.0 * SR)
            tt = np.arange(m) / SR
            noise = rng.normal(0, 1, m)
            body = onepole(noise, 900) * adsr(m, 0.004, 0.35) * 2.2
            hiss = (noise - onepole(noise, 2500)) * (np.exp(-tt / 1.4) * np.clip(tt / 0.08, 0, 1)) * 0.5
            boom = np.sin(2 * np.pi * (55 * tt)) * adsr(m, 0.003, 0.5) * 0.9
            add(L, t, body + hiss + boom, 0.3)
            add(R, t, body + hiss * 0.9 + boom, 0.3)
            # payoff chord (C major add 9), bell-like
            for i, semi in enumerate([0, 7, 12, 16, 19, 26]):
                f = 261.63 * 2 ** (semi / 12)
                mm = int(3.6 * SR)
                t2 = np.arange(mm) / SR
                bell = (np.sin(2 * np.pi * f * t2) + 0.3 * np.sin(2 * np.pi * 2.01 * f * t2) * np.exp(-t2 * 3)) * adsr(mm, 0.01, 1.3)
                add(L, t + 0.03 * i, bell, 0.13 * (1.2 if i % 2 == 0 else 0.8))
                add(R, t + 0.03 * i, bell, 0.13 * (0.8 if i % 2 == 0 else 1.2))
    # continuous sizzle (while burning) + crackles
    fr = sim["frames"]
    env = np.zeros(n)
    for i, f in enumerate(fr):
        if f["splash"] is None and f["k"] < N_BANDS and f["contact_t"] > 0:
            frac = clamp(f["contact_t"] / burn_time(f["k"]))
            a = 0.25 + 0.75 * frac
            s0 = int(i / FPS * SR)
            env[s0:s0 + SR // FPS] = a
    env = onepole(env, 20)
    noise = rng.normal(0, 1, n)
    hp = noise - onepole(noise, 3000)
    crack = (rng.random(n) < 0.0009) * rng.normal(0, 3, n)
    crack = crack - onepole(crack, 2000)
    sizzle = (hp * 0.11 + crack * 0.25) * env
    L += sizzle
    R += sizzle * 0.95 + np.roll(sizzle, 300) * 0.05
    # drone pad + riser before the payoff
    tt = np.arange(n) / SR
    st = sim["splash"]
    prog = np.clip(tt / st, 0, 1)
    pad_amp = (0.03 + 0.05 * prog) * np.clip(tt / 1.0, 0, 1) * np.clip((st + 3.0 - tt) / 1.5, 0, 1)
    pad = np.zeros(n)
    for semi, g in ((-24, 1.0), (-17, 0.6), (-12, 0.5)):
        f = 261.63 * 2 ** (semi / 12)
        pad += g * np.sin(2 * np.pi * f * tt + 0.3 * np.sin(2 * np.pi * 0.2 * tt))
    L += pad * pad_amp
    R += pad * pad_amp
    r0 = st * 0.72
    rmask = np.clip((tt - r0) / (st - r0), 0, 1) * (tt < st)
    phase = 2 * np.pi * np.cumsum(220 + 660 * rmask ** 2) / SR
    riser = (np.sin(phase) * 0.5 + (noise - onepole(noise, 1500)) * 0.4) * rmask ** 2.2 * 0.16
    L += riser
    R += riser
    # light reverb (multi-tap, decorrelated L/R)
    def verb(x, taps):
        y = x.copy()
        for d_ms, g in taps:
            d = int(d_ms * SR / 1000)
            y[d:] += x[:-d] * g
        return y
    L = verb(L, [(37, 0.22), (71, 0.16), (113, 0.11), (167, 0.07)])
    R = verb(R, [(43, 0.22), (79, 0.16), (127, 0.11), (181, 0.07)])
    # gentle fades + normalise to -1 dBFS
    fade = np.ones(n)
    fi = int(0.01 * SR)
    fade[:fi] = np.linspace(0, 1, fi)
    fo = int(0.6 * SR)
    fade[-fo:] = np.linspace(1, 0, fo)
    L *= fade
    R *= fade
    # soft limiter so the splash does not bury the snaps
    p = max(np.abs(L).max(), np.abs(R).max())
    L = np.tanh(2.0 * L / p) / np.tanh(2.0)
    R = np.tanh(2.0 * R / p) / np.tanh(2.0)
    peak = max(np.abs(L).max(), np.abs(R).max())
    gain = 10 ** (-1 / 20) / peak
    st_ = np.stack([L, R], 1) * gain
    pcm = (np.clip(st_, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--frames")
    ap.add_argument("--outdir", default="keys")
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    args = ap.parse_args()
    cache = os.environ.get("SIMCACHE")
    if cache and os.path.exists(cache):
        import pickle
        sim = pickle.load(open(cache, "rb"))
    else:
        sim = simulate()
        if cache:
            import pickle
            pickle.dump(sim, open(cache, "wb"))
    snaps = [e for e in sim["events"] if e[1] == "snap"]
    nf = len(sim["frames"])
    print(f"duration {sim['duration']:.2f}s, frames {nf}, snaps {len(snaps)}, splash at {sim['splash']:.2f}s")
    for q in (0.25, 0.5, 0.75):
        i = int(q * len(snaps))
        print(f"  {int(q*100)}% bands at {snaps[i][0]:.2f}s")
    gaps = np.diff([0] + [e[0] for e in sim["events"]])
    print(f"  longest gap between sound events {gaps.max():.2f}s")
    if args.sim:
        return
    if args.frames:
        os.makedirs(args.outdir, exist_ok=True)
        worker_init(sim)
        for q in args.frames.split(","):
            fi = min(nf - 1, int(float(q) * (nf - 1)))
            raw = render_frame(fi)
            Image.frombytes("RGB", (W, H), raw).save(os.path.join(args.outdir, f"key_{q}.png"))
            print("saved", q, fi)
        return
    tmp = tempfile.mkdtemp()
    wav = os.path.join(tmp, "a.wav")
    synth_audio(sim, wav)
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                             "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                             "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", args.out],
                            stdin=subprocess.PIPE)
    with Pool(args.workers, initializer=worker_init, initargs=(sim,)) as pool:
        for i, raw in enumerate(pool.imap(render_frame, range(nf), chunksize=4)):
            proc.stdin.write(raw)
            if i % 300 == 0:
                print("frame", i, "/", nf, flush=True)
    proc.stdin.close()
    proc.wait()
    print("done", args.out)


if __name__ == "__main__":
    main()
