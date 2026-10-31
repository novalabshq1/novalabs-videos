#!/usr/bin/env python3
"""Brick Ring — a glowing ball bounces inside a ring; every bounce lays one glass brick on the wall.
The ring closes in layer by layer (outer cyan -> violet -> pink -> gold) until the ball is sealed in a
tiny chamber; the whole wall then shatters outward.  Counter: BRICKS n.
Sound mode 1: pure ASMR effects (wood tok, glass tink, clack, pop), no melody. Stereo, pan by position.

    python3.13 brick-ring.py --seed N                      (simulation summary)
    python3.13 brick-ring.py --search 24
    python3.13 brick-ring.py --frames 0,0.25,0.5,0.75,0.9,0.97 --outdir keys/ --seed N
    python3.13 brick-ring.py --out video.mp4 --seed N
"""
import argparse, math, os, subprocess, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

W, H, FPS, S = 1080, 1920, 60, 2
SR = 44100
SUB = 16
DT = 1.0 / (FPS * SUB)
CX, CY, R0 = 540.0, 1135.0, 395.0
M, L = 16, 10                      # slots, layers
HB = 33.7                          # brick thickness
BR = 16.0                          # ball radius
COOL = 0.075                       # min time between two bricks
SEED = 3
V0, V1 = 1800.0, 2800.0
TAIL = 3.6                         # seconds after the shatter starts
PRE = 0.55                         # pause between last brick and shatter

PAL = [(60, 228, 255), (118, 128, 255), (176, 96, 255), (246, 84, 196), (255, 120, 120), (255, 196, 84)]


def layer_col(k):
    x = k / (L - 1) * (len(PAL) - 1)
    i = min(int(x), len(PAL) - 2)
    f = x - i
    return tuple(PAL[i][c] * (1 - f) + PAL[i + 1][c] * f for c in range(3))


def speed_for(frac, v0):
    return v0 + (V1 - v0) * frac ** 0.8


def wall_r(cnt, ang, d):
    dl = BR / max(d, 1.0)
    best = 0
    for a in (ang - dl, ang, ang + dl):
        best = max(best, cnt[int((a % (2 * math.pi)) / (2 * math.pi) * M) % M])
    return R0 - HB * best


def pick_slot(cnt, s):
    mn = min(cnt)
    for off in range(M // 2 + 1):
        for k in ((s + off) % M, (s - off) % M):
            if cnt[k] <= mn + 1 and cnt[k] < L:
                return k
    return int(np.argmin(cnt))


def simulate(seed, v0=V0, tmax=60.0):
    rng = np.random.default_rng(seed)
    cnt = [2] * M
    bricks = [(k, 0, -1.0) for k in range(M)] + [(k, 1, -1.0) for k in range(M)]          # (slot, layer, commit time)
    a0 = rng.random() * 2 * math.pi
    p = np.array([CX + 60 * math.cos(a0), CY + 60 * math.sin(a0)])
    th = rng.random() * 2 * math.pi
    v = np.array([math.cos(th), math.sin(th)])
    pend = None                                          # (slot, hit_t)
    last_add = -9.0
    events, pos = [], []
    t, t_last, t_sh = 0.0, None, None
    total = M * L
    nsteps = int(tmax / DT)
    for step in range(nsteps):
        t = (step + 1) * DT
        frac = (sum(cnt) - 2 * M) / (total - 2 * M)
        sp = speed_for(frac, v0)
        if t_sh is not None:
            sp = 700.0
        v /= np.hypot(*v)
        p = p + v * sp * DT
        d = p - np.array([CX, CY])
        r = float(np.hypot(*d))
        ang = math.atan2(d[1], d[0])
        full = sum(cnt) == total
        rw = (R0 if t_sh is not None else wall_r(cnt, ang, r)) - BR
        # commit a pending brick once the ball is clear of it (or on the next hit)
        if pend is not None:
            k, ht = pend
            clear = r < R0 - HB * (cnt[k] + 1) - BR - 3
            if clear or t - ht > 0.12:
                if not clear:                              # nudge the ball inwards
                    n = d / max(r, 1e-6)
                    lim = R0 - HB * (cnt[k] + 1) - BR - 1
                    p = np.array([CX, CY]) + n * min(r, lim)
                    d = p - np.array([CX, CY]); r = float(np.hypot(*d))
                cnt[k] += 1
                bricks.append((k, cnt[k] - 1, t))
                events.append((t, "add", k, cnt[k] - 1, len(bricks)))
                if sum(cnt) == total:
                    t_last = t
                pend = None
        if r > rw and np.dot(v, d / r) > 0:
            n = d / r
            jit = (rng.random() - 0.5) * 0.22
            c, s_ = math.cos(jit), math.sin(jit)
            n = np.array([n[0] * c - n[1] * s_, n[0] * s_ + n[1] * c])
            v = v - 2 * np.dot(v, n) * n
            p = np.array([CX, CY]) + d / r * (rw - 0.01)
            hit_ang = ang % (2 * math.pi)
            slot = int(hit_ang / (2 * math.pi) * M) % M
            if pend is not None:
                pass
            elif t_sh is None and sum(cnt) < total and t - last_add > COOL:
                pend = (pick_slot(cnt, slot), t)
                last_add = t
                events.append((t, "hit", slot, 1, tuple(p)))
            else:
                events.append((t, "hit", slot, 0, tuple(p)))
        pos.append((p[0], p[1]))
        if t_last is not None and t_sh is None and t > t_last + PRE:
            t_sh = t
        if t_sh is not None and t > t_sh + TAIL + 1:
            break
    return dict(pos=np.array(pos), events=events, bricks=bricks, t_last=t_last, t_sh=t_sh,
                n_hits=sum(1 for e in events if e[1] == "hit"))


def summary(sim):
    ad = [b[2] for b in sim["bricks"] if b[2] >= 0]
    if not ad:
        return None
    ar = np.array(ad)
    return dict(last=sim["t_last"] and round(sim["t_last"], 1), bricks=len(sim["bricks"]),
                rate_first5s=int(np.sum(ar < 5)) / 5, rate_last5s=int(np.sum(ar > (sim["t_last"] or 0) - 5)) / 5,
                max_gap=round(float(np.max(np.diff(ar))), 2))


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


# ---------------------------------------------------------------- timeline: slow motion on the last brick
SLOW = 0.3


def build_timeline(sim):
    e = sim["t_last"]
    s0, s1 = e - 0.35, e + 0.20

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

    total = vt_of(sim["t_sh"]) + TAIL
    return st_of, vt_of, total


# ---------------------------------------------------------------- static layers
SIM = None
STATIC = {}


def make_bg():
    Hs, Ws = H * S, W * S
    y = np.linspace(0, 1, Hs, dtype=np.float32)[:, None]
    x = np.linspace(-1, 1, Ws, dtype=np.float32)[None, :]
    top, bot = np.array([14, 12, 30.], np.float32), np.array([5, 5, 12.], np.float32)
    img = top[None, None, :] * (1 - y[:, :, None]) + bot[None, None, :] * y[:, :, None]
    yy = (y * 2 - 1)
    vig = 1 - 0.32 * np.clip(x ** 2 * 0.7 + yy ** 2 * 0.45, 0, 1)
    img = img * vig[:, :, None]
    py = (np.arange(Hs, dtype=np.float32)[:, None] + 0.5) / S
    px = (np.arange(Ws, dtype=np.float32)[None, :] + 0.5) / S
    r = np.sqrt((px - CX) ** 2 + (py - CY) ** 2)
    inside = np.clip((R0 - r) * S / 2 + 0.5, 0, 1)
    floor = np.array([20, 18, 40.], np.float32) * (0.7 + 0.3 * np.exp(-(r / R0) ** 2 * 1.4))[:, :, None]
    img = img * (1 - inside[:, :, None]) + floor * inside[:, :, None]
    ring = np.exp(-((r - R0) / 2.5) ** 2)
    halo = np.exp(-((r - R0) / 20) ** 2) * 0.12
    img += np.array([150, 160, 230.], np.float32)[None, None, :] * (ring * 0.5 + halo)[:, :, None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def ball_sprite():
    R = BR * S
    n = int(2 * R + 8)
    yy, xx = np.mgrid[0:n, 0:n] - (n - 1) / 2
    d = np.sqrt(xx ** 2 + yy ** 2) / R
    a = np.clip((1 - d) * R / 1.2, 0, 1)
    nz = np.sqrt(np.clip(1 - d ** 2, 0, 1))
    lam = np.clip(-0.35 * xx / R - 0.5 * yy / R + 0.8 * nz, 0, 1)
    rim = np.clip(d, 0, 1) ** 3
    col = np.stack([255 * lam + 90 * rim, 255 * lam + 220 * rim * 0.8, 255 * lam + 255 * rim * 0.6], -1) * 0.95 + 25
    spec = np.exp(-(((xx + 0.35 * R) ** 2 + (yy + 0.4 * R) ** 2) / (0.22 * R) ** 2))
    col = col + 160 * spec[:, :, None]
    return Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)), Image.fromarray((a * 255).astype(np.uint8))


def init_static():
    STATIC["bg"] = make_bg()
    STATIC["q1"] = with_shadow(text_img("How many bricks", 94, (246, 244, 252, 255)))
    STATIC["q2"] = with_shadow(text_img("until it’s trapped?", 94, (246, 244, 252, 255)))
    wm = text_img("@novalabs.hq", 30, (255, 255, 255, 255))
    a = np.asarray(wm).copy()
    a[:, :, 3] = (a[:, :, 3] * 0.35).astype(np.uint8)
    STATIC["wm"] = Image.fromarray(a)
    STATIC["fnum"] = font(150 * S)
    STATIC["flab"] = font(62 * S)
    STATIC["counters"] = {}
    STATIC["ball"] = ball_sprite()


def counter_img(n, col):
    key = (n, col)
    if key in STATIC["counters"]:
        return STATIC["counters"][key]
    fnum, flab = STATIC["fnum"], STATIC["flab"]
    s = str(n)
    dw = max(fnum.getbbox(str(k))[2] - fnum.getbbox(str(k))[0] for k in range(10)) + 6 * S
    b1 = fnum.getbbox("0")
    lab = "BRICKS"
    lb = flab.getbbox(lab)
    numw = dw * 3
    gap = 26 * S
    w = numw + gap + (lb[2] - lb[0])
    h = b1[3] - b1[1]
    im = Image.new("RGBA", (int(w + 60), int(h + 60)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0 = 30 + numw - dw * len(s)
    for k, ch in enumerate(s):
        gb = fnum.getbbox(ch)
        d.text((x0 + k * dw + (dw - (gb[2] - gb[0])) / 2 - gb[0], 30 - b1[1]), ch, font=fnum, fill=col + (255,))
    d.text((30 + numw + gap - lb[0], 30 + h - lb[3]), lab, font=flab, fill=(190, 186, 222, 255))
    out = with_shadow(im)
    STATIC["counters"][key] = out
    return out


# ---------------------------------------------------------------- per frame
def wedge(slot, layer, grow=0.0, inset=0.0, rin_off=0.0):
    """Polygon (list of (x,y) in px*S) of the brick at (slot, layer)."""
    ro = R0 - HB * layer - inset
    ri = ro - HB + 2 * inset + rin_off
    sw = 2 * math.pi / M
    gap_o, gap_i = 1.6 / ro, 1.6 / max(ri, 5)
    a0, a1 = slot * sw, (slot + 1) * sw
    pts = []
    for i in range(7):
        a = a0 + gap_o + (a1 - a0 - 2 * gap_o) * i / 6
        pts.append((CX + ro * math.cos(a), CY + ro * math.sin(a)))
    for i in range(7):
        a = a1 - gap_i - (a1 - a0 - 2 * gap_i) * i / 6
        pts.append((CX + ri * math.cos(a), CY + ri * math.sin(a)))
    if grow:
        mx = sum(q[0] for q in pts) / len(pts)
        my = sum(q[1] for q in pts) / len(pts)
        pts = [(mx + (q[0] - mx) * (1 + grow), my + (q[1] - my) * (1 + grow)) for q in pts]
    return pts


def xform(pts, dx, dy, rot):
    mx = sum(q[0] for q in pts) / len(pts)
    my = sum(q[1] for q in pts) / len(pts)
    c, s = math.cos(rot), math.sin(rot)
    return [(mx + dx + (q[0] - mx) * c - (q[1] - my) * s, my + dy + (q[0] - mx) * s + (q[1] - my) * c) for q in pts]


def sc(pts, k=S):
    return [(q[0] * k, q[1] * k) for q in pts]


def mix(c, d, f):
    return tuple(c[i] * (1 - f) + d[i] * f for i in range(3))


def ci(c, k=1.0):
    return tuple(int(clamp(v * k, 0, 255)) for v in c)


def render_frame(vt):
    sim = SIM
    st_of, vt_of, total = STATIC["tl"]
    st = st_of(vt)
    t_sh = sim["t_sh"]
    sh_age = st - t_sh if st >= t_sh else -1.0
    img = STATIC["bg"].copy()
    d = ImageDraw.Draw(img)
    GS = 4
    glow = Image.new("RGB", (W * S // GS, H * S // GS), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    light = Image.new("RGB", img.size, (0, 0, 0))
    ld = ImageDraw.Draw(light)

    shake = (0, 0)
    if 0 <= sh_age < 0.5:
        a = 14 * (1 - sh_age / 0.5) ** 2
        shake = (int(a * math.sin(sh_age * 90) * S / 2), int(a * math.cos(sh_age * 77) * S / 2))

    # ---- bricks
    n_b = 0
    fl_last = None
    for k, (slot, layer, tc) in enumerate(sim["bricks"]):
        if tc > st:
            break
        n_b += 1
        base = layer_col(layer)
        age = st - tc
        f = clamp(1 - age / 0.24) if tc >= 0 else 0.0
        if sh_age >= 0:
            sw = 2 * math.pi / M
            am = (slot + 0.5) * sw
            rm = R0 - HB * (layer + 0.5)
            rs = np.random.default_rng(k * 7 + 1)
            spd = 380 + 520 * rs.random() + 0.5 * (R0 - rm)
            dist = spd * (1 - math.exp(-sh_age * 2.6)) / 2.6 * 1.0
            tang = (rs.random() - 0.5) * 220 * sh_age
            dx = math.cos(am) * dist - math.sin(am) * tang
            dy = math.sin(am) * dist + math.cos(am) * tang
            rot = (rs.random() - 0.5) * 7 * sh_age
            life = 1.35 + 0.5 * rs.random()
            fade = clamp(1 - (sh_age / life) ** 1.5)
            fade *= clamp((CY + (R0 - rm) * 0 + dy + math.sin(am) * rm - 690) / 140)
            if fade <= 0.01:
                continue
            col = mix(base, (255, 255, 255), 0.5 * clamp(1 - sh_age / 0.25))
            pts = sc(xform(wedge(slot, layer), dx, dy, rot))
            d.polygon(pts, fill=ci(col, 0.55 * fade))
            inner = sc(xform(wedge(slot, layer, inset=3.0), dx, dy, rot))
            d.polygon(inner, fill=ci(col, 0.95 * fade))
            gd.polygon(sc(xform(wedge(slot, layer), dx, dy, rot), S / GS), fill=ci(col, 0.40 * fade))
            continue
        col = mix(base, (255, 255, 255), 0.85 * f ** 1.5)
        g = 0.22 * f
        pts = sc(wedge(slot, layer, grow=g))
        d.polygon(pts, fill=ci(base, 0.42 + 0.3 * f))
        d.polygon(sc(wedge(slot, layer, grow=g, inset=2.6)), fill=ci(col, 0.85))
        # bright face on the arena side + soft top light
        d.polygon(sc(wedge(slot, layer, grow=g, inset=3.2, rin_off=-(HB - 9))), fill=ci(mix(col, (255, 255, 255), 0.22), 1.0))
        gd.polygon(sc(wedge(slot, layer, grow=g), S / GS), fill=ci(col, 0.32 + 0.6 * f))

    # ---- ball + trail
    pos = sim["pos"]
    idx = lambda s_: int(clamp(s_ / DT, 0, len(pos) - 1))
    bp = pos[idx(st)]
    cnt_now = n_b
    layer_now = clamp((cnt_now - 2 * M) / (M * L - 2 * M), 0, 1) * (L - 1)
    ccol = layer_col(min(L - 1, int(layer_now)))
    tr = [pos[idx(st - j * 0.0105)] for j in range(18)]
    for j in range(17):
        a_ = 1 - j / 17
        w_ = max(2.0, BR * 2 * S * (0.15 + 0.85 * a_ ** 1.2))
        c_ = ci(mix((255, 255, 255), ccol, 1 - a_ ** 2), 0.9 * a_ ** 1.4)
        ld.line([(tr[j][0] * S, tr[j][1] * S), (tr[j + 1][0] * S, tr[j + 1][1] * S)], fill=c_, width=int(w_))
        gd.line([(tr[j][0] * S / GS, tr[j][1] * S / GS), (tr[j + 1][0] * S / GS, tr[j + 1][1] * S / GS)],
                fill=ci(ccol, 0.8 * a_), width=max(2, int(w_ / GS * 1.6)))
    gd.ellipse([bp[0] * S / GS - 12, bp[1] * S / GS - 12, bp[0] * S / GS + 12, bp[1] * S / GS + 12], fill=ci(ccol, 0.75))

    # ---- hit ripples + sparks (from events)
    for e in sim["events"]:
        if e[1] != "hit":
            continue
        age = st - e[0]
        if age < 0:
            break
        if age > 0.5:
            continue
        p = e[4]
        if e[3]:
            rr = (8 + 70 * ease_out(age / 0.3)) * S
            al = clamp(1 - age / 0.3)
            if al > 0 and sh_age < 0:
                ld.ellipse([p[0] * S - rr, p[1] * S - rr, p[0] * S + rr, p[1] * S + rr],
                           outline=ci((255, 255, 255), 0.75 * al), width=max(2, int(3 * S * al)))
                rs = np.random.default_rng(int(e[0] * 1000))
                for q in range(5):
                    aa = rs.random() * 2 * math.pi
                    dd_ = (10 + 90 * ease_out(age / 0.4)) * (0.5 + rs.random()) * S
                    al2 = clamp(1 - age / 0.4)
                    qx, qy = p[0] * S + math.cos(aa) * dd_, p[1] * S + math.sin(aa) * dd_
                    ld.ellipse([qx - 3 * S, qy - 3 * S, qx + 3 * S, qy + 3 * S], fill=ci((255, 255, 255), al2))

    # ---- final: seal flash, shatter shock ring and sparks
    t_last = sim["t_last"]
    if st >= t_last and sh_age < 0:
        a_ = clamp(1 - (st - t_last) / 0.5)
        rr = R0 * S * (0.15 + 0.9 * ease_out((st - t_last) / 0.5))
        ld.ellipse([CX * S - rr, CY * S - rr, CX * S + rr, CY * S + rr], outline=ci((255, 220, 140), 0.7 * a_), width=int(6 * S * a_) + 1)
    if sh_age >= 0:
        rr = (20 + 450 * ease_out(sh_age / 0.7)) * S
        a_ = clamp(1 - sh_age / 0.7)
        ld.ellipse([CX * S - rr, CY * S - rr, CX * S + rr, CY * S + rr], outline=ci((255, 240, 200), 0.9 * a_), width=int(14 * S * a_) + 1)
        rs = np.random.default_rng(77)
        for q in range(160):
            aa = rs.random() * 2 * math.pi
            spd = 250 + 1100 * rs.random()
            dist = spd * (1 - math.exp(-sh_age * 2.2)) / 2.2
            al = clamp(1 - sh_age / (0.8 + 0.8 * rs.random()))
            if al <= 0:
                continue
            c_ = layer_col(int(rs.random() * L))
            qx, qy = CX * S + math.cos(aa) * dist * S, CY * S + math.sin(aa) * dist * S
            al *= clamp((qy / S - 690) / 140)
            z = (2 + 4 * rs.random()) * S
            ld.ellipse([qx - z, qy - z, qx + z, qy + z], fill=ci(c_, 1.2 * al))

    # ---- compose
    gl = glow.filter(ImageFilter.GaussianBlur(5)).resize(img.size, Image.BILINEAR)
    img = ImageChops.add(img, ImageChops.multiply(gl, Image.new("RGB", img.size, (170, 170, 170))))
    spr, msk = STATIC["ball"]
    img.paste(spr, (int(bp[0] * S - spr.width / 2), int(bp[1] * S - spr.height / 2)), msk)
    img = ImageChops.add(img, light.filter(ImageFilter.GaussianBlur(1.2 * S)))
    if sh_age >= 0 and sh_age < 0.3:
        fl = (1 - sh_age / 0.3) ** 2 * 0.42
        img = ImageChops.add(img, Image.new("RGB", img.size, (int(255 * fl), int(235 * fl), int(190 * fl))))
    if shake != (0, 0):
        img = ImageChops.offset(img, *shake)

    # ---- text
    bricks_shown = n_b
    gold = (255, 206, 96)
    sealed = st >= t_last
    col = gold if sealed else (255, 255, 255)
    cimg = counter_img(bricks_shown, col)
    pop = 1.0
    last_t = max([b[2] for b in sim["bricks"] if b[2] <= st] + [0])
    if st - last_t < 0.12 and not sealed:
        pop = 1 + 0.07 * (1 - (st - last_t) / 0.12)
    if sealed:
        pop = 1 + 0.10 * math.exp(-(st - t_last) * 5)
    if pop != 1.0:
        cimg = cimg.resize((int(cimg.width * pop), int(cimg.height * pop)), Image.BICUBIC)
    for key, y in (("q1", 282), ("q2", 392)):
        q = STATIC[key]
        img.paste(q, (int(W * S / 2 - q.width / 2), y * S), q)
    img.paste(cimg, (int(W * S / 2 - cimg.width / 2), 535 * S), cimg)
    wm = STATIC["wm"]
    img.paste(wm, (int(W * S / 2 - wm.width / 2), 1790 * S), wm)
    return np.asarray(img.resize((W, H), Image.LANCZOS))


# ---------------------------------------------------------------- audio (stereo, effects only)
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


def add2(buf, t, sig, gain=1.0, pan=0.0):
    k = int(round(t * SR))
    if k < 0 or k >= buf.shape[1]:
        return
    j = min(buf.shape[1], k + len(sig))
    pl, pr = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
    buf[0, k:j] += sig[:j - k] * gain * pl * 1.414
    buf[1, k:j] += sig[:j - k] * gain * pr * 1.414


def sine(f, dur, r, a=0.001, f_end=None):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    if f_end:
        ff = f + (f_end - f) * np.minimum(1, tt / dur) ** 0.5
        ph = 2 * math.pi * np.cumsum(ff) / SR
    else:
        ph = 2 * math.pi * f * tt
    return np.sin(ph) * env(n, a, r)


NOISE = np.random.default_rng(11).normal(0, 1, SR)


def noise_burst(dur, lo, hi, r, a=0.0005, off=0):
    n = int(dur * SR)
    x = band(np.roll(NOISE, off)[:n], lo, hi)
    return x / (np.max(np.abs(x)) + 1e-9) * env(n, a, r)


def msum(*sigs):
    n = max(len(x) for x in sigs)
    out = np.zeros(n)
    for x in sigs:
        out[:len(x)] += x
    return out


def brick_sound(kind, layer, rng):
    """One brick laid down. kind rotates: 0 wood tok, 1 glass tink, 2 clack, 3 pop. Pitch rises with the layer."""
    up = 2 ** (layer / (L - 1) * 0.9)
    j = 2 ** ((rng.random() - 0.5) * 0.18)
    if kind == 0:     # wood "tok"
        f = 210 * up * j
        s = msum(sine(f, 0.16, 0.035) * 0.9, sine(f * 2.3, 0.08, 0.015) * 0.35, noise_burst(0.03, 900, 3200, 0.006, off=int(rng.integers(1000, 30000))) * 0.4)
        return s, 0.9
    if kind == 1:     # glass "tink"
        f = 1650 * up * j
        s = sum(g * sine(f * m, 0.28, 0.07 / (1 + 0.5 * i)) for i, (m, g) in enumerate(((1, 1.0), (2.76, 0.45), (5.4, 0.22))))
        return s * 0.55, 0.7
    if kind == 2:     # clack: two quick clicks
        s = noise_burst(0.04, 1400, 6000, 0.007, off=int(rng.integers(1000, 30000)))
        s2 = np.zeros(int(0.06 * SR))
        s2[:len(s)] += s * 0.8
        k = int(0.011 * SR)
        s2[k:k + len(s)] += s[:len(s2) - k] * 0.5
        return msum(s2, sine(520 * up * j, 0.06, 0.012) * 0.5), 0.8
    f = 420 * up * j  # soft pop: pitch drop
    return msum(sine(f * 1.8, 0.11, 0.03, f_end=f * 0.8), noise_burst(0.015, 2500, 7000, 0.003) * 0.15), 0.8


def synth_audio(sim, path):
    st_of, vt_of, total = build_timeline(sim)
    n = int(total * SR) + SR
    dry = np.zeros((2, n))
    rng = np.random.default_rng(5)
    t_last, t_sh = sim["t_last"], sim["t_sh"]
    kind_i = 0
    last_tick = -1
    for ev in sim["events"]:
        te = ev[0]
        vt = vt_of(te)
        if ev[1] == "add":
            slot, layer = ev[2], ev[3]
            kind = [0, 1, 2, 3, 0, 1, 3, 2][kind_i % 8]
            kind_i += 1
            sig, g = brick_sound(kind, layer, rng)
            pan = math.cos((slot + 0.5) * 2 * math.pi / M) * 0.7
            vol = 0.55 + 0.45 * layer / (L - 1)
            if te >= t_last - 1e-6:
                continue
            add2(dry, vt, sig, g * vol * 0.55, pan)
            if layer >= L - 3:       # fuller body in the last layers
                add2(dry, vt, sine(95 + 20 * rng.random(), 0.25, 0.07, f_end=60), 0.30 * vol, pan * 0.5)
        elif ev[1] == "hit" and not ev[3]:
            if vt - last_tick < 0.05:
                continue
            last_tick = vt
            add2(dry, vt, noise_burst(0.02, 2000, 6500, 0.004, off=int(rng.integers(1000, 30000))), 0.10,
                 float(np.clip((ev[4][0] - CX) / R0, -1, 1)) * 0.6)
    # riser (glassy air) into the last brick
    rd = 5.0
    r0 = vt_of(t_last) - rd
    rn = int(rd * SR)
    x = np.linspace(0, 1, rn)
    noise = rng.normal(0, 1, rn)
    ris = np.zeros(rn)
    for k in range(10):
        seg = slice(k * rn // 10, (k + 1) * rn // 10)
        lo = 1200 + 500 * k
        ris[seg] = band(noise[seg], lo, lo * 2.4)[: seg.stop - seg.start]
    ris = ris * x ** 2.4 * 0.09
    add2(dry, r0, ris, 1.0, 0.0)
    # last brick: deep full thud, then a breath of silence
    vl = vt_of(t_last)
    add2(dry, vl, sine(150, 0.9, 0.22, f_end=48), 0.85)
    add2(dry, vl, brick_sound(0, L - 1, rng)[0], 0.8)
    add2(dry, vl, noise_burst(0.2, 150, 2500, 0.04), 0.35)
    # shatter: low boom + hundreds of glass shards
    vs = vt_of(t_sh)
    add2(dry, vs, sine(110, 1.6, 0.5, f_end=34), 1.0)
    add2(dry, vs, noise_burst(1.0, 80, 2400, 0.22), 0.5)
    for i in range(190):
        tt = vs + 0.02 + (rng.random() ** 1.7) * 1.7
        f = 1800 + 4200 * rng.random()
        sig = sum(g * sine(f * m, 0.22, 0.05 * (1 - 0.4 * rng.random())) for m, g in ((1, 1.0), (2.76, 0.4), (5.4, 0.15)))
        dens = math.exp(-(tt - vs) * 1.3)
        add2(dry, tt, sig, 0.10 * (0.3 + dens), float(rng.random() * 2 - 1) * 0.85)
    for i in range(70):
        tt = vs + 0.03 + (rng.random() ** 1.4) * 1.3
        add2(dry, tt, noise_burst(0.05, 600, 3500, 0.012, off=int(rng.integers(1000, 30000))), 0.16 * math.exp(-(tt - vs)), float(rng.random() * 2 - 1) * 0.8)
    # airy tail
    sh = band(rng.normal(0, 1, int(2.5 * SR)), 4500, 12000) * env(int(2.5 * SR), 0.06, 0.6)
    add2(dry, vs + 0.1, sh, 0.05, 0.0)
    # reverb (short, bright room)
    irn = int(1.1 * SR)
    ir = rng.normal(0, 1, irn) * np.exp(-np.arange(irn) / (0.22 * SR))
    ir = band(ir, 300, 9000)
    ir /= np.sqrt(np.sum(ir ** 2))
    Lf = 1 << int(math.ceil(math.log2(n + irn)))
    mix = np.zeros_like(dry)
    for c in range(2):
        wet = np.fft.irfft(np.fft.rfft(dry[c], Lf) * np.fft.rfft(np.roll(ir, c * 37), Lf), Lf)[:n]
        mix[c] = dry[c] + 0.18 * wet
    mix = mix[:, : int(total * SR)]
    fo = int(0.8 * SR)
    mix[:, -fo:] *= np.linspace(1, 0.0, fo) ** 1.5
    return mix, path


def finish_audio(mix, path, drive):
    m = np.tanh(mix * drive) / drive
    m *= 10 ** (-1.2 / 20) / np.max(np.abs(m))
    pcm = (m.T * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def worker_init(seed, v0=V0):
    global SIM
    SIM = simulate(seed, v0)
    init_static()
    STATIC["tl"] = build_timeline(SIM)


def render_bytes(fi):
    return render_frame(fi / FPS).tobytes()


def _job(args):
    sd, v0 = args
    s = simulate(sd, v0)
    return sd, v0, summary(s)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--v0", type=float, default=V0)
    ap.add_argument("--drive", type=float, default=2.0)
    ap.add_argument("--search", type=int, default=0)
    ap.add_argument("--frames", default="")
    ap.add_argument("--outdir", default="keys")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    if a.search:
        with Pool(4) as p:
            for r in p.imap(_job, [(sd, a.v0) for sd in range(a.search)]):
                print(*r, flush=True)
    elif a.frames:
        worker_init(a.seed, a.v0)
        total = STATIC["tl"][2]
        os.makedirs(a.outdir, exist_ok=True)
        for tok in a.frames.split(","):
            v = float(tok)
            vt = v * total if v <= 1 else v
            Image.fromarray(render_frame(vt)).save(os.path.join(a.outdir, f"k_{vt:06.2f}.png"))
            print("frame", round(vt, 2), "/", round(total, 2), flush=True)
    elif a.out:
        worker_init(a.seed, a.v0)
        total = STATIC["tl"][2]
        nfr = int(round(total * FPS))
        wav = a.out + ".wav"
        amix, _ = synth_audio(SIM, wav)
        finish_audio(amix, wav, a.drive)
        proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                 "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                                 "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", a.out],
                                stdin=subprocess.PIPE)
        with Pool(4, initializer=worker_init, initargs=(a.seed, a.v0)) as p:
            for k, b in enumerate(p.imap(render_bytes, range(nfr), chunksize=4)):
                proc.stdin.write(b)
                if k % 300 == 0:
                    print("frame", k, "/", nfr, flush=True)
        proc.stdin.close()
        proc.wait()
        os.remove(wav)
    else:
        s = simulate(a.seed, a.v0)
        print(summary(s), "hits", s["n_hits"], "t_sh", s["t_sh"])
