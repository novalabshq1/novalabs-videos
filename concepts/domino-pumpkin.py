#!/usr/bin/env python3
"""Domino Pumpkin — 2,000 dominoes stand in a spiral (seen from above). The chain falls from the
outside in; each fallen domino shows its painted face, so the falling wave "prints" a picture.
The front spins faster and faster toward the centre (constant domino rate on shrinking turns,
plus a speed-up). When the last domino falls, the hidden jack-o'-lantern lights up.

Sound mode: BRUITAGES only (domino clacks + landing taps, riser of noise, ignition, fire crackle).

Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS to 1080x1920, 60 fps.
    python3.13 domino-pumpkin.py --info
    python3.13 domino-pumpkin.py --frames 0,5,10,20,30,36,38,41 --outdir keys/
    python3.13 domino-pumpkin.py --out video.mp4
"""
import argparse, math, os, subprocess, wave, tempfile
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

W, H, FPS, S = 1080, 1920, 60, 2
SR = 44100
CX, CY, R = 508.0, 1062.0, 425.0          # arena (kept out of the right 140 px band)
N = 2000
PITCH = 21.0                              # radial distance between spiral arms
LW = 17.0                                 # domino width (radial)
TH = 3.6                                  # thickness
HT = 19.0                                 # height
R_MIN = 14.0
K_SETTLE = 6.0                            # after hitting the next one, settles in K*dt
HOLD = 5.6                                # seconds after the last domino
FONT_B = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
FONT_S = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"

rng0 = np.random.default_rng(31)


# ---------------------------------------------------------------- geometry
def build_spiral():
    phi_max = (R - R_MIN) * 2 * math.pi / PITCH
    ph = np.linspace(0, phi_max, 400000)
    r = R - PITCH * ph / (2 * math.pi) - LW / 2 - 3
    x = CX + r * np.cos(ph - math.pi / 2)
    y = CY + r * np.sin(ph - math.pi / 2)
    seg = np.hypot(np.diff(x), np.diff(y))
    cum = np.concatenate([[0], np.cumsum(seg)])
    s = cum[-1] / N
    targets = (np.arange(N) + 0.0) * s
    idx = np.searchsorted(cum, targets)
    idx = np.clip(idx, 1, len(x) - 2)
    bx, by = x[idx], y[idx]
    tx, ty = x[idx + 1] - x[idx - 1], y[idx + 1] - y[idx - 1]
    tl = np.hypot(tx, ty)
    ux, uy = tx / tl, ty / tl                # travel direction (domino falls this way)
    nx, ny = -uy, ux                         # across
    rr = r[idx]
    lw = np.minimum(LW, np.maximum(7.0, rr * 0.9))
    return bx, by, ux, uy, nx, ny, s, lw, rr


BX, BY, UX, UY, NX, NY, SP, LWI, RR = build_spiral()
TH_F = math.acos(TH / SP)                    # resting angle (shingled)
TH_HIT = math.asin((SP - TH) / HT)
EXT_F = HT * math.sin(TH_F) + TH * math.cos(TH_F)


def build_timing():
    i = np.arange(N) / (N - 1)
    rate = 40.0 + (112.0 - 40.0) * i ** 2.2
    dt = 1.0 / rate
    ts = np.concatenate([[0.0], np.cumsum(dt[:-1])])
    return ts, dt


TS, DT = build_timing()
T_LAST = TS[-1]
T_END = T_LAST + DT[-1] * (1 + K_SETTLE)     # last domino lies flat
T_IGN = T_END + 0.30
T_PRE = 1.6                                  # video t=0 is sim t=T_PRE (chain already falling)
DUR = (T_END + HOLD) - T_PRE
NFRAMES = int(round(DUR * FPS))


def angles(t):
    u = t - TS
    th = np.zeros(N)
    a = (u > 0) & (u < DT)
    th[a] = TH_HIT * (u[a] / DT[a]) ** 2
    b = u >= DT
    v = np.clip((u[b] - DT[b]) / (K_SETTLE * DT[b]), 0, 1)
    thf = np.full(N, TH_F)
    thf[-1] = math.radians(88)
    th[b] = TH_HIT + (thf[b] - TH_HIT) * (1 - (1 - v) ** 2)
    return th


# ---------------------------------------------------------------- picture
def hexc(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def make_picture(n=1000):
    ys, xs = np.mgrid[0:n, 0:n]
    X = (xs + 0.5) / n * 2 - 1
    Y = (ys + 0.5) / n * 2 - 1
    img = np.zeros((n, n, 3))
    # night sky gradient
    top, bot = hexc('#3a1d6b'), hexc('#160c2c')
    f = np.clip((Y + 1) / 2, 0, 1)[..., None]
    img[:] = top * (1 - f) + bot * f
    # moon (crescent)
    mx, my, mr = -0.47, -0.73, 0.125
    moon = ((X - mx) ** 2 + (Y - my) ** 2 < mr ** 2) & ((X - mx - 0.06) ** 2 + (Y - my + 0.035) ** 2 > (mr * 0.86) ** 2)
    img[moon] = hexc('#f6e7a8')
    # ground
    gy = 0.76 + 0.04 * np.cos(X * 2.2)
    ground = Y > gy
    img[ground] = hexc('#1c2b20') * (1 - 0.3 * np.clip((Y[ground] - 0.76) / 0.25, 0, 1))[..., None]
    # pumpkin ribs (outer first)
    ribs = [(-0.62, 0.36, 0.64), (0.62, 0.36, 0.64), (-0.33, 0.40, 0.70), (0.33, 0.40, 0.70), (0.0, 0.42, 0.73)]
    cyp = 0.11
    light, mid, dark = hexc('#ffb048'), hexc('#f27a14'), hexc('#9a3a08')
    body = np.zeros((n, n), bool)
    for k, (rx, hw, hh) in enumerate(ribs):
        d = np.sqrt(((X - rx) / hw) ** 2 + ((Y - cyp) / hh) ** 2)
        m = d < 1
        body |= m
        dd = d[m]
        col = np.where((dd < 0.55)[..., None], light * (1 - dd[..., None] / 0.55) + mid * (dd[..., None] / 0.55),
                       mid * (1 - (dd[..., None] - 0.55) / 0.45) + dark * ((dd[..., None] - 0.55) / 0.45))
        shade = 0.86 if k < 2 else (0.93 if k < 4 else 1.0)
        img[m] = col * shade
    # stem
    stem = (np.abs(X - 0.02 - 0.18 * np.clip(-(Y + 0.56), 0, None) ** 1.6 * (Y < -0.56)) < 0.075) & (Y > -0.88) & (Y < -0.50)
    stem &= ~((Y > -0.6) & body & (np.abs(X) > 0.1))
    img[stem] = hexc('#5e7d2a') * (0.8 + 0.25 * ((X[stem] + 0.1) > 0))[..., None]
    # face
    face = np.zeros((n, n), bool)

    def tri(p):
        (x1, y1), (x2, y2), (x3, y3) = p
        def side(ax, ay, bx, by):
            return (X - bx) * (ay - by) - (ax - bx) * (Y - by)
        d1, d2, d3 = side(x1, y1, x2, y2), side(x2, y2, x3, y3), side(x3, y3, x1, y1)
        neg = (d1 < 0) | (d2 < 0) | (d3 < 0)
        pos = (d1 > 0) | (d2 > 0) | (d3 > 0)
        return ~(neg & pos)

    face |= tri([(-0.56, 0.0), (-0.14, 0.0), (-0.36, -0.34)])
    face |= tri([(0.56, 0.0), (0.14, 0.0), (0.36, -0.34)])
    face |= tri([(-0.10, 0.21), (0.10, 0.21), (0.0, 0.05)])
    xm = 0.64
    yt = 0.36 - 0.15 * (X / xm) ** 2
    yb = 0.60 - 0.33 * (X / xm) ** 2
    mouth = (np.abs(X) < xm) & (Y > yt) & (Y < yb)
    tooth1 = (X > -0.30) & (X < -0.13) & (Y < 0.36 - 0.15 * (X / xm) ** 2 + 0.11)
    tooth2 = (X > 0.13) & (X < 0.30) & (Y > 0.60 - 0.33 * (X / xm) ** 2 - 0.11)
    mouth &= ~tooth1 & ~tooth2
    face |= mouth
    img[face] = hexc('#2a1007')
    return img, face.astype(float)


def sample_colors():
    pic, face = make_picture()
    n = pic.shape[0]
    # visible strip centre of each fallen domino
    off = EXT_F - SP / 2
    vx, vy = BX + UX * off, BY + UY * off
    px = ((vx - (CX - R)) / (2 * R) * n).astype(int)
    py = ((vy - (CY - R)) / (2 * R) * n).astype(int)
    cols = np.zeros((N, 3))
    fm = np.zeros(N)
    k = 6
    for i in range(N):
        x0, x1 = max(0, px[i] - k), min(n, px[i] + k + 1)
        y0, y1 = max(0, py[i] - k), min(n, py[i] + k + 1)
        cols[i] = pic[y0:y1, x0:x1].reshape(-1, 3).mean(0)
        fm[i] = face[y0:y1, x0:x1].mean()
    # stars: a few sky dominoes twinkle pale
    rng = np.random.default_rng(5)
    sky = (cols.sum(1) < 200) & (fm < 0.05) & (py < n * 0.62)
    st = sky & (rng.random(N) < 0.06)
    cols[st] = cols[st] * 0.35 + hexc('#d9c8ff') * 0.65
    cols *= rng.uniform(0.95, 1.04, (N, 1))
    lit = cols.copy()
    lc1, lc2 = hexc('#fff3a6'), hexc('#ffa424')
    mix = rng.uniform(0, 1, N)[:, None]
    lc = lc1 * (1 - mix * 0.7) + lc2 * (mix * 0.7)
    fmm = np.clip((fm - 0.15) / 0.6, 0, 1)[:, None]
    lit = cols * (1 - fmm) + lc * fmm
    return np.clip(cols, 0, 255), np.clip(lit, 0, 255), fm, vx, vy


COLS, LIT, FACE, VX, VY = sample_colors()
IVORY = hexc('#efe6d3')


# ---------------------------------------------------------------- render
def font(p, sz):
    return ImageFont.truetype(p, int(sz))


def make_background():
    ys, xs = np.mgrid[0:H * S, 0:W * S].astype(np.float32)
    xs /= S
    ys /= S
    d = np.hypot(xs - CX, ys - CY)
    base = np.array([21, 17, 27], np.float32)
    vig = 1.0 + 0.35 * np.exp(-((d / 700.0) ** 2)) - 0.25 * np.clip((d - 600) / 900, 0, 1)
    img = base[None, None, :] * vig[..., None]
    # felt disc under the dominoes
    disc = np.clip((R + 16 - d) * S / 2.0, 0, 1)
    felt = np.array([30, 24, 40], np.float32)[None, None, :] * (1.0 + 0.12 * np.exp(-((d / 380.0) ** 2)))[..., None]
    img = img * (1 - disc[..., None]) + felt * disc[..., None]
    ring = np.clip(1 - np.abs(d - (R + 16)) * S / 2.0, 0, 1)
    img = img * (1 - ring[..., None] * 0.6) + np.array([70, 60, 90], np.float32) * ring[..., None] * 0.6
    # fine noise for texture
    rng = np.random.default_rng(2)
    img += rng.normal(0, 1.4, img.shape[:2])[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


LDX, LDY = 0.52, 0.70


def lighting(t):
    """0 before ignition; 0..1 ramp with per-domino spatial delay after."""
    if t < T_IGN:
        return np.zeros(N), 0.0
    dist = np.hypot(VX - CX, VY - CY) / R
    k = np.clip((t - T_IGN - dist * 0.35) / 0.45, 0, 1)
    k = k * k * (3 - 2 * k)
    fl = 1.0 + 0.07 * math.sin(t * 23.0) + 0.05 * math.sin(t * 37.0 + 1.3) + 0.04 * math.sin(t * 11.0)
    return k, fl


def embers(t):
    out = []
    if t < T_IGN + 0.2:
        return out
    rng = np.random.default_rng(77)
    src = np.nonzero(FACE > 0.6)[0]
    n_e = 70
    births = T_IGN + 0.2 + rng.random(n_e) * (T_END + HOLD - T_IGN - 0.2)
    life = rng.uniform(1.3, 2.4, n_e)
    pick = src[rng.integers(0, len(src), n_e)]
    vy = rng.uniform(90, 170, n_e)
    ph = rng.random(n_e) * 6.28
    for k in range(n_e):
        a = t - births[k]
        if 0 <= a < life[k]:
            x = VX[pick[k]] + 18 * math.sin(a * 3.0 + ph[k]) + a * 10 * math.cos(ph[k])
            y = VY[pick[k]] - vy[k] * a
            if y < 600:
                continue
            fade = (1 - a / life[k]) * min(1, a / 0.15)
            out.append((x, y, fade, 2.0 + 2.5 * (1 - a / life[k])))
    return out


class Renderer:
    def __init__(self):
        self.bg = make_background()
        self.bg_dark = Image.eval(self.bg, lambda v: int(v * 0.42))
        self.f_q = font(FONT_B, 74)
        self.f_c = font(FONT_B, 98)
        self.f_c2 = font(FONT_S, 50)
        self.f_w = font(FONT_S, 30)

    def frame(self, vt):
        t = vt + T_PRE
        th = angles(t)
        lk, fl = lighting(t)
        sinth, costh = np.sin(th), np.cos(th)
        ext = HT * sinth + TH * costh
        # ---- shadows (1x, blurred)
        sh = Image.new('L', (W, H), 0)
        sd = ImageDraw.Draw(sh)
        hl = LWI / 2
        ax, ay = BX - NX * hl, BY - NY * hl
        bx2, by2 = BX + NX * hl, BY + NY * hl
        shl = HT * 0.62 * (costh + 0.10)
        for i in range(N):
            ex, ey = UX[i] * ext[i], UY[i] * ext[i]
            dx, dy = LDX * shl[i], LDY * shl[i]
            sd.polygon([(ax[i], ay[i]), (bx2[i], by2[i]), (bx2[i] + ex + dx, by2[i] + ey + dy),
                        (ax[i] + ex + dx, ay[i] + ey + dy)], fill=255)
        sh = sh.filter(ImageFilter.GaussianBlur(2.2)).resize((W * S, H * S), Image.BILINEAR)
        sh = Image.eval(sh, lambda v: int(v * 0.85))
        img = Image.composite(self.bg_dark, self.bg, sh)
        d = ImageDraw.Draw(img)
        # ---- dominoes, last index first (domino i lies on top of i+1)
        cols = COLS * (1 - lk[:, None]) + LIT * lk[:, None]
        if fl:
            boost = 1 + (fl - 1) * (FACE > 0.3) * lk
            cols = np.clip(cols * boost[:, None], 0, 255)
        shade = 0.50 + 0.50 * sinth / math.sin(TH_F)
        for i in range(N - 1, -1, -1):
            s_ = S
            a0x, a0y = ax[i] * s_, ay[i] * s_
            b0x, b0y = bx2[i] * s_, by2[i] * s_
            ux, uy = UX[i] * s_, UY[i] * s_
            e = ext[i]
            if th[i] <= 1e-4:
                c = IVORY * 0.93
                d.polygon([(a0x, a0y), (b0x, b0y), (b0x + ux * TH, b0y + uy * TH), (a0x + ux * TH, a0y + uy * TH)],
                          fill=tuple(int(v) for v in c))
                continue
            face_len = HT * sinth[i]
            edge_len = TH * costh[i]
            fc = cols[i] * min(1.08, shade[i])
            d.polygon([(a0x, a0y), (b0x, b0y), (b0x + ux * face_len, b0y + uy * face_len),
                       (a0x + ux * face_len, a0y + uy * face_len)], fill=tuple(int(v) for v in fc))
            # highlight near the top of the face
            hi = np.minimum(255, fc * 1.13 + 6)
            h0 = max(0.0, face_len - 2.2)
            d.polygon([(a0x + ux * h0, a0y + uy * h0), (b0x + ux * h0, b0y + uy * h0),
                       (b0x + ux * face_len, b0y + uy * face_len), (a0x + ux * face_len, a0y + uy * face_len)],
                      fill=tuple(int(v) for v in hi))
            if edge_len > 0.25:
                w_ = costh[i] ** 2
                ec = IVORY * 0.93 * w_ + hi * (1 - w_)
                d.polygon([(a0x + ux * face_len, a0y + uy * face_len), (b0x + ux * face_len, b0y + uy * face_len),
                           (b0x + ux * e, b0y + uy * e), (a0x + ux * e, a0y + uy * e)],
                          fill=tuple(int(v) for v in ec))
            # contact shadow on the next domino
            j = i + 1
            if j < N and th[j] > TH_F * 0.85 and th[i] > TH_F * 0.5:
                nc = cols[j] * min(1.08, shade[j]) * 0.66
                d.polygon([(a0x + ux * e, a0y + uy * e), (b0x + ux * e, b0y + uy * e),
                           (b0x + ux * (e + 2.6), b0y + uy * (e + 2.6)), (a0x + ux * (e + 2.6), a0y + uy * (e + 2.6))],
                          fill=tuple(int(v) for v in nc))
        # ---- glow after ignition
        if t >= T_IGN:
            q = 4
            gl = Image.new('L', (W * S // q, H * S // q), 0)
            gd = ImageDraw.Draw(gl)
            for i in np.nonzero((FACE > 0.25) & (lk > 0))[0]:
                v = int(255 * lk[i] * min(1, FACE[i] * 1.4))
                x0, y0 = BX[i] * S / q, BY[i] * S / q
                ee = ext[i] * S / q
                hw = LWI[i] / 2 * S / q
                gd.polygon([(x0 - NX[i] * hw, y0 - NY[i] * hw), (x0 + NX[i] * hw, y0 + NY[i] * hw),
                            (x0 + NX[i] * hw + UX[i] * ee, y0 + NY[i] * hw + UY[i] * ee),
                            (x0 - NX[i] * hw + UX[i] * ee, y0 - NY[i] * hw + UY[i] * ee)], fill=v)
            for (x, y, fade, rad) in embers(t):
                rr = rad * S / q * 1.6
                gd.ellipse([x * S / q - rr, y * S / q - rr, x * S / q + rr, y * S / q + rr], fill=int(255 * fade))
            g1 = gl.filter(ImageFilter.GaussianBlur(5)).resize((W * S, H * S), Image.BILINEAR)
            g2 = gl.filter(ImageFilter.GaussianBlur(22)).resize((W * S, H * S), Image.BILINEAR)
            ga = np.asarray(g1, np.float32) * 0.30 * fl + np.asarray(g2, np.float32) * 0.42 * fl
            glow = np.clip(ga[..., None] * np.array([1.0, 0.62, 0.20], np.float32), 0, 255).astype(np.uint8)
            img = ImageChops.add(img, Image.fromarray(glow))
            # crisp ember cores
            d = ImageDraw.Draw(img)
            for (x, y, fade, rad) in embers(t):
                rr = rad * S * 0.55
                c = (255, int(200 + 40 * fade), int(110 * fade))
                if fade > 0.08:
                    d.ellipse([x * S - rr, y * S - rr, x * S + rr, y * S + rr],
                              fill=tuple(int(255 * 0.15 + v * 0.85 * fade) for v in c))
        # ---- slow push-in at the end
        z = 1.0
        if t > T_END - 0.5:
            u = min(1, (t - (T_END - 0.5)) / 3.0)
            z = 1.0 + 0.055 * (u * u * (3 - 2 * u))
        if z > 1.0001:
            cw, ch = W * S / z, H * S / z
            fx, fy = CX * S, CY * S
            x0 = fx - (fx / (W * S)) * cw
            y0 = fy - (fy / (H * S)) * ch
            img = img.resize((W, H), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))
        else:
            img = img.resize((W, H), Image.LANCZOS)
        # ---- text
        d = ImageDraw.Draw(img)
        tx = 508
        d.text((tx, 250), "What will 2,000", font=self.f_q, fill=(245, 240, 250), anchor="mm")
        d.text((tx, 334), "dominoes draw?", font=self.f_q, fill=(245, 240, 250), anchor="mm")
        nfall = int(np.sum(TS <= t))
        done = t >= T_END
        num = f"{nfall:,}"
        col = (255, 196, 70) if done else (255, 150, 52)
        # fixed-width cells so the number does not jitter
        self._counter(d, num, " / 2,000", 492, col)
        d.text((tx, 1590), "@novalabs.hq", font=self.f_w, fill=(120, 110, 140), anchor="mm")
        return img

    def _counter(self, d, num, tail, y, col):
        cw = 60
        widths = [cw if ch.isdigit() else 26 for ch in num]
        tw = d.textlength(tail, font=self.f_c2)
        total = sum(widths) + tw + 6
        x = 508 - total / 2
        for ch, w_ in zip(num, widths):
            d.text((x + w_ / 2, y), ch, font=self.f_c, fill=col, anchor="ms")
            x += w_
        d.text((x + 6, y), tail, font=self.f_c2, fill=(170, 160, 190), anchor="ls")


_R = None


def _init():
    global _R
    _R = Renderer()


def render_chunk(args):
    f0, f1, path = args
    _init()
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                          "-crf", "15", "-pix_fmt", "yuv420p", "-g", "60", path], stdin=subprocess.PIPE)
    for f in range(f0, f1):
        p.stdin.write(_R.frame(f / FPS).tobytes())
    p.stdin.close()
    p.wait()
    return path


# ---------------------------------------------------------------- audio
def biquad_bp(x, f, q):
    w0 = 2 * math.pi * f / SR
    al = math.sin(w0) / (2 * q)
    b0, b1, b2 = al, 0, -al
    a0, a1, a2 = 1 + al, -2 * math.cos(w0), 1 - al
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
    for n in range(len(x)):
        v = b0 * x[n] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, x[n], y1, v
        y[n] = v
    return y


def lowpass_fft(x, fc):
    X = np.fft.rfft(x)
    fr = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (fr / fc) ** 4)
    return np.fft.irfft(X, len(x))


def highpass_fft(x, fc):
    X = np.fft.rfft(x)
    fr = np.fft.rfftfreq(len(x), 1 / SR)
    X *= (fr / fc) ** 4 / (1 + (fr / fc) ** 4)
    return np.fft.irfft(X, len(x))


def make_clacks(rng, n=16):
    out = []
    for _ in range(n):
        L = int(0.06 * SR)
        tt = np.arange(L) / SR
        y = np.zeros(L)
        base = rng.uniform(2100, 2700)
        for k, (m, a, dec) in enumerate([(1.0, 1.0, 0.020), (1.63, 0.6, 0.013), (2.31, 0.35, 0.009), (3.05, 0.2, 0.006)]):
            fq = base * m * rng.uniform(0.96, 1.04)
            y += a * np.sin(2 * math.pi * fq * tt + rng.random() * 6) * np.exp(-tt / dec)
        nb = rng.normal(0, 1, L) * np.exp(-tt / 0.0016)
        y += 1.4 * highpass_fft(nb, 2500)
        body = np.sin(2 * math.pi * rng.uniform(850, 1200) * tt) * np.exp(-tt / 0.006) * 0.7
        y += body
        y *= np.minimum(1, tt / 0.0004)
        out.append(y / np.max(np.abs(y)))
    return out


def make_taps(rng, n=10):
    out = []
    for _ in range(n):
        L = int(0.07 * SR)
        tt = np.arange(L) / SR
        nb = rng.normal(0, 1, L) * np.exp(-tt / 0.004)
        y = lowpass_fft(nb, rng.uniform(1500, 2400))
        y += 0.5 * np.sin(2 * math.pi * rng.uniform(420, 600) * tt) * np.exp(-tt / 0.012)
        y *= np.minimum(1, tt / 0.0005)
        out.append(y / np.max(np.abs(y)))
    return out


def place(buf, snd, t, gain, pan):
    i0 = int(round(t * SR))
    if i0 < 0 or i0 >= buf.shape[1]:
        return
    n = min(len(snd), buf.shape[1] - i0)
    gl, gr = math.cos(pan * math.pi / 2), math.sin(pan * math.pi / 2)
    buf[0, i0:i0 + n] += snd[:n] * gain * gl
    buf[1, i0:i0 + n] += snd[:n] * gain * gr


def make_audio(path):
    rng = np.random.default_rng(9)
    total = DUR
    L = int(total * SR) + 1
    buf = np.zeros((2, L))
    clacks, taps = make_clacks(rng), make_taps(rng)
    events = []
    for i in range(N):
        pan = float(np.clip(0.5 + (BX[i] - CX) / (2 * R) * 0.8, 0.08, 0.92))
        prog = i / N
        # the hit of domino i on domino i+1 (= start of i+1)
        if i + 1 < N:
            th_ = TS[i + 1] - T_PRE
            g = 0.34 * rng.uniform(0.75, 1.0) * (1.0 - 0.25 * prog)
            place(buf, clacks[rng.integers(len(clacks))], th_, g, pan)
            events.append(th_)
        tl = TS[i] + DT[i] * (1 + K_SETTLE) - T_PRE
        place(buf, taps[rng.integers(len(taps))], tl, 0.13 * rng.uniform(0.7, 1.0), pan)
    # the very last domino hits the felt
    lastland = T_END - T_PRE
    tt = np.arange(int(0.25 * SR)) / SR
    thud = np.sin(2 * math.pi * 95 * tt) * np.exp(-tt / 0.06) + 0.6 * lowpass_fft(rng.normal(0, 1, len(tt)), 900) * np.exp(-tt / 0.03)
    place(buf, thud / np.max(np.abs(thud)), lastland, 0.55, 0.5)
    events.append(lastland)
    # quiet room / wind bed
    nz = rng.normal(0, 1, L)
    wind = lowpass_fft(nz, 380)
    wind /= np.max(np.abs(wind)) + 1e-9
    tl_ = np.arange(L) / SR
    wmod = 0.55 + 0.45 * np.sin(2 * math.pi * 0.11 * tl_) * np.sin(2 * math.pi * 0.047 * tl_ + 1)
    buf += 0.035 * wind * wmod
    # noise riser as the vortex spins up (ends exactly at the last landing)
    r0, r1 = lastland - 6.0, lastland
    i0, i1 = int(r0 * SR), int(r1 * SR)
    seg = rng.normal(0, 1, i1 - i0)
    u = np.linspace(0, 1, i1 - i0)
    # sweep: blend of progressively brighter low-passes
    lo = lowpass_fft(seg, 500)
    hi = lowpass_fft(seg, 4500)
    sw = lo * (1 - u) + hi * u
    sw /= np.max(np.abs(sw))
    env = u ** 2.2 * 0.16
    buf[0, i0:i1] += sw * env
    buf[1, i0:i1] += sw * env
    # ignition "fwoomp"
    ti = T_IGN - T_PRE
    tt = np.arange(int(1.2 * SR)) / SR
    boom = np.sin(2 * math.pi * (55 + 30 * np.exp(-tt / 0.08)) * tt) * np.exp(-tt / 0.35)
    fw = lowpass_fft(rng.normal(0, 1, len(tt)), 1200) * np.minimum(1, tt / 0.04) * np.exp(-tt / 0.32)
    fw /= np.max(np.abs(fw))
    ign = 0.8 * boom + 0.7 * fw
    place(buf, ign, ti, 0.75, 0.5)
    events.append(ti)
    # fire: soft roar + crackles
    j0 = int((ti + 0.1) * SR)
    nfire = L - j0
    roar = lowpass_fft(rng.normal(0, 1, nfire), 700)
    roar /= np.max(np.abs(roar))
    tf = np.arange(nfire) / SR
    fade_out = np.clip((total - (ti + 0.1) - tf) / 1.2, 0, 1)
    renv = np.minimum(1, tf / 0.4) * (0.85 + 0.15 * np.sin(tf * 17)) * fade_out
    buf[:, j0:] += 0.09 * roar * renv
    ct = ti + 0.15
    while ct < total - 0.4:
        ct += rng.exponential(1 / 14)
        Lc = int(0.012 * SR)
        tc = np.arange(Lc) / SR
        cr = highpass_fft(rng.normal(0, 1, Lc), 1800) * np.exp(-tc / 0.002)
        g = rng.uniform(0.08, 0.3) * float(np.clip((total - ct) / 1.2, 0, 1))
        place(buf, cr / (np.max(np.abs(cr)) + 1e-9), ct, g, rng.uniform(0.3, 0.7))
    # small reverb
    ir_len = int(0.4 * SR)
    ti_ = np.arange(ir_len) / SR
    ir = rng.normal(0, 1, ir_len) * np.exp(-ti_ / 0.09)
    ir = lowpass_fft(ir, 5000)
    ir /= np.sqrt(np.sum(ir ** 2))
    for ch in range(2):
        n2 = 1 << int(math.ceil(math.log2(L + ir_len)))
        wet = np.fft.irfft(np.fft.rfft(buf[ch], n2) * np.fft.rfft(ir, n2), n2)[:L]
        buf[ch] = buf[ch] + 0.22 * wet
    # master: soft limit and -1 dBFS
    fade = np.clip((total - np.arange(L) / SR) / 0.5, 0, 1)
    buf *= fade
    buf = np.tanh(buf * 1.3) / 1.3
    buf *= (10 ** (-1 / 20)) / np.max(np.abs(buf))
    pcm = (buf.T * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--frames")
    ap.add_argument("--outdir", default="keys")
    ap.add_argument("--out")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    if a.info or True:
        print(f"N={N} spacing={SP:.2f}px thf={math.degrees(TH_F):.1f} thit={math.degrees(TH_HIT):.1f} "
              f"fall={T_LAST:.2f}s end={T_END:.2f}s dur={DUR:.2f}s frames={NFRAMES} "
              f"face dominoes={int(np.sum(FACE > 0.4))}")
    if a.frames:
        os.makedirs(a.outdir, exist_ok=True)
        _init()
        for s in a.frames.split(','):
            vt = float(s)
            _R.frame(vt).save(os.path.join(a.outdir, f"k_{vt:05.2f}.png"))
    if a.out:
        tmp = tempfile.mkdtemp(dir=os.path.dirname(os.path.abspath(a.out)))
        wav = os.path.join(tmp, "a.wav")
        make_audio(wav)
        bounds = np.linspace(0, NFRAMES, a.jobs * 3 + 1).astype(int)
        chunks = [(bounds[k], bounds[k + 1], os.path.join(tmp, f"c{k:02d}.mp4")) for k in range(len(bounds) - 1)]
        with Pool(a.jobs) as p:
            parts = p.map(render_chunk, chunks)
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w") as f:
            for q in parts:
                f.write(f"file '{q}'\n")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", wav,
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", a.out],
                       check=True)
        print("wrote", a.out)


if __name__ == "__main__":
    main()
