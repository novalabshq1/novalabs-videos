#!/usr/bin/env python3
"""Rainbow Galton — 600 glass marbles drain from a messy rainbow hopper through 12 rows of pegs.
Each marble is coloured by the bin it WILL land in, so pure chaos at the top sorts itself into a
perfect rainbow gradient at the bottom. When the last marble lands, the theoretical bell curve
is drawn over the pile: it fits.

Sound mode: BRUITAGES only (peg clicks, marble tocks, hopper rumble, whoosh, thump). No notes.

Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS down to 1080x1920, 60 fps.
    python3.13 rainbow-galton.py --search 400        (seed closest to the theoretical curve)
    python3.13 rainbow-galton.py --frames 0,0.1,...  --outdir keys/ --seed N
    python3.13 rainbow-galton.py --out video.mp4 --seed N
"""
import argparse, math, os, subprocess, wave, colorsys
from math import comb
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, S = 1080, 1920, 60, 2
SR = 44100
N = 600
ROWS = 12
NB = ROWS + 1
CX = 490.0                    # board centre (keeps clear of the right 140 px band)
DX = 66.0                     # peg spacing = bin width
PEG_Y0, PEG_DY = 640.0, 40.0
PEG_R, BR = 5.0, 7.0
G = 4200.0
FLOOR = 1650.0                # bin floor (bottom 250 px stay empty)
BIN_TOP = PEG_Y0 + ROWS * PEG_DY + 4
LAYER = 12.6
HOP_Y0 = 290.0               # hopper top
SPOUT_Y = 585.0
T0 = 1.3                      # sim time shown at video frame 0 (stream already flowing)
SEED = 1192

# timeline (video time) filled after simulate
FONT_PATHS = ("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def font(px):
    for p in FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, int(px))
    return ImageFont.load_default()


def bin_color(b):
    # hue by cumulative probability: every colour gets an equal share of the 600 marbles
    pr = [comb(ROWS, k) / 2 ** ROWS for k in range(NB)]
    mid = sum(pr[:b]) + pr[b] / 2
    q = min(1.0, max(0.0, (mid - 0.03) / 0.94))
    h = 0.86 * q
    r, g, bb = colorsys.hsv_to_rgb(h, 0.70, 1.0)
    return (int(r * 255), int(g * 255), int(bb * 255))


def peg_xy(k, i):
    return CX + (i - k / 2.0) * DX, PEG_Y0 + k * PEG_DY


def emission_times():
    ts, t = [], 0.0
    while len(ts) < N:
        u = min(1.0, t / 16.0)
        rate = 10.0 + 35.0 * u * u * (3 - 2 * u)
        ts.append(t)
        t += 1.0 / rate
    return np.array(ts)


def hopper_slots():
    """Hex-packed slots inside the V hopper, bottom first."""
    slots = []
    rows = int((SPOUT_Y - 20 - HOP_Y0) / 12.2) + 1
    for r in range(rows):
        y = SPOUT_Y - 22 - r * 12.2
        frac = (SPOUT_Y - y) / (SPOUT_Y - HOP_Y0)
        half = 22 + frac * (395 - 22) - BR - 3
        off = 7.0 if r % 2 else 0.0
        xs = np.arange(-half + off, half + 0.01, 14.4)
        xs = xs - (xs.mean() if len(xs) else 0)
        for x in xs:
            slots.append((CX + x, y))
    return slots


def simulate(seed):
    rng = np.random.default_rng(seed)
    em = emission_times()
    paths = (rng.random((N, ROWS)) < 0.5).astype(int)   # 1 = right
    final = paths.sum(1)
    counts = np.bincount(final, minlength=NB)
    balls, clicks, tocks = [], [], []
    fill = [0] * NB
    perms = {}
    for n in range(N):
        segs = []                       # (t0, t1, x0, y0, x1, y1, v0y)
        t = em[n]
        # fall from spout to first peg top
        x, y = CX + rng.uniform(-1.5, 1.5), SPOUT_Y
        ty = PEG_Y0 - PEG_R - BR
        dt = math.sqrt(2 * (ty - y) / G)
        segs.append((t, t + dt, x, y, CX, ty, 0.0))
        t += dt
        clicks.append((t, 0))
        i = 0
        for k in range(ROWS):
            px, py = peg_xy(k, i)
            i2 = i + paths[n, k]
            if k + 1 < ROWS:
                nx, ny = peg_xy(k + 1, i2)
                ny -= PEG_R + BR
            else:
                nx, ny = CX + (i2 - 6) * DX, BIN_TOP + 10
            h = rng.uniform(4.5, 8.0)
            v0 = -math.sqrt(2 * G * h)
            dy = ny - (py - PEG_R - BR)
            T = (-v0 + math.sqrt(v0 * v0 + 2 * G * dy)) / G
            segs.append((t, t + T, px, py - PEG_R - BR, nx, ny, v0))
            t += T
            if k + 1 < ROWS:
                clicks.append((t, k + 1))
            i = i2
        b = i
        j = fill[b]
        fill[b] += 1
        L, c = divmod(j, 4)
        if (b, L) not in perms:
            perms[(b, L)] = rng.permutation(4)
        c = perms[(b, L)][c]
        bx = CX + (b - 6) * DX
        sx = bx + (-21 + 14 * c) + (3 if L % 2 else -3)
        sy = FLOOR - BR - L * LAYER
        # free fall inside the bin, continuing the last hop's velocity
        y0 = BIN_TOP + 10
        v_in = segs[-1][6] + G * (segs[-1][1] - segs[-1][0])
        dy = sy - y0
        T = (-v_in + math.sqrt(v_in * v_in + 2 * G * dy)) / G
        segs.append((t, t + T, bx, y0, sx, sy, v_in))
        t += T
        tocks.append((t, b, L))
        # tiny settle bounce
        hb = 2.5
        vb = -math.sqrt(2 * G * hb)
        Tb = 2 * -vb / G
        segs.append((t, t + Tb, sx, sy, sx, sy, vb))
        balls.append(dict(segs=segs, bin=b, sx=sx, sy=sy, land=t, settle=t + Tb, emit=em[n]))
    expected = np.array([N * comb(ROWS, b) / 2 ** ROWS for b in range(NB)])
    err = float(np.sum((counts - expected) ** 2))
    asym = float(abs(np.sum((counts - expected) * (np.arange(NB) - 6))))
    return dict(balls=balls, clicks=clicks, tocks=tocks, counts=counts, expected=expected,
                err=err, asym=asym, emit=em, last=max(bl["settle"] for bl in balls))


def timeline(sim):
    last_v = sim["last"] - T0
    curve0 = last_v + 0.7
    curve1 = curve0 + 1.8
    perfect = curve1 + 0.35
    end = perfect + 3.4
    return dict(last=last_v, curve0=curve0, curve1=curve1, perfect=perfect, end=end)


def seg_pos(sg, t):
    t0, t1, x0, y0, x1, y1, v0 = sg
    tau = t - t0
    u = tau / max(1e-9, t1 - t0)
    x = x0 + (x1 - x0) * u
    if v0 == 0.0 and y1 != y0 and (x1 != x0 or True) and sg is not None:
        pass
    y = y0 + v0 * tau + 0.5 * G * tau * tau
    if x1 == x0 and y1 == y0:          # settle bounce
        y = y0 + v0 * tau + 0.5 * G * tau * tau
        y = min(y, y0)
    return x, y


def ball_pos(bl, t):
    if t < bl["emit"]:
        return None
    if t >= bl["settle"]:
        return bl["sx"], bl["sy"]
    for sg in bl["segs"]:
        if sg[0] <= t < sg[1]:
            return seg_pos(sg, t)
    return bl["sx"], bl["sy"]


# ---------------------------------------------------------------- rendering
ST = {}


def make_sprite(col, r):
    R = int(math.ceil(r * S)) + 2
    sz = 2 * R + 1
    yy, xx = np.mgrid[0:sz, 0:sz].astype(np.float32) - R
    d = np.sqrt(xx ** 2 + yy ** 2) / (r * S)
    alpha = np.clip((1.0 - d) * r * S * 0.9, 0, 1)
    base = np.array(col, np.float32) / 255
    shade = 0.62 + 0.38 * np.clip(1 - np.sqrt((xx + 0.35 * r * S) ** 2 + (yy + 0.4 * r * S) ** 2) / (1.5 * r * S), 0, 1)
    rgb = base[None, None, :] * shade[..., None]
    spec = np.exp(-(((xx + 0.32 * r * S) ** 2 + (yy + 0.38 * r * S) ** 2) / (2 * (0.22 * r * S) ** 2)))
    rgb = rgb + (1 - rgb) * (0.85 * spec)[..., None]
    rim = np.clip((d - 0.78) / 0.22, 0, 1) * 0.35
    rgb = rgb * (1 - rim[..., None])
    img = np.dstack([np.clip(rgb, 0, 1) * 255, alpha * 255]).astype(np.uint8)
    return Image.fromarray(img, "RGBA"), R


def draw_text_center(d, y, txt, px, fill):
    f = font(px * S)
    w = d.textlength(txt, font=f)
    d.text((CX * S - w / 2, y * S), txt, font=f, fill=fill)


def make_bg():
    g = np.linspace(0, 1, H * S, dtype=np.float32)[:, None]
    top, bot = np.array([14, 16, 28]), np.array([6, 7, 13])
    arr = (top * (1 - g) + bot * g)[:, None, :].repeat(W * S, 1)
    img = Image.fromarray(arr.astype(np.uint8).squeeze(), "RGB") if arr.ndim == 3 else None
    img = Image.fromarray(np.broadcast_to((top * (1 - g) + bot * g)[:, None, :], (H * S, W * S, 3)).astype(np.uint8))
    glow = Image.new("RGB", img.size, (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    d = ImageDraw.Draw(img)
    wall = (92, 100, 130)
    # hopper
    pts = [(CX - 395, HOP_Y0), (CX - 22, SPOUT_Y), (CX + 22, SPOUT_Y), (CX + 395, HOP_Y0)]
    for a, b2 in ((0, 1), (2, 3)):
        line = [(pts[a][0] * S, pts[a][1] * S), (pts[b2][0] * S, pts[b2][1] * S)]
        gd.line(line, fill=(40, 46, 70), width=int(14 * S))
        d.line(line, fill=wall, width=int(4 * S))
    # pegs
    for k in range(ROWS):
        for i in range(k + 1):
            x, y = peg_xy(k, i)
            gd.ellipse([(x - 11) * S, (y - 11) * S, (x + 11) * S, (y + 11) * S], fill=(46, 52, 80))
            d.ellipse([(x - PEG_R) * S, (y - PEG_R) * S, (x + PEG_R) * S, (y + PEG_R) * S], fill=(200, 206, 228))
    # bins
    for b in range(NB + 1):
        x = CX + (b - 6.5) * DX
        line = [(x * S, BIN_TOP * S + 30 * S), (x * S, (FLOOR + 2) * S)]
        gd.line(line, fill=(32, 36, 56), width=int(10 * S))
        d.line(line, fill=(70, 77, 104), width=int(3 * S))
    fl = [((CX - 6.5 * DX - 1.5) * S, (FLOOR + 2) * S), ((CX + 6.5 * DX + 1.5) * S, (FLOOR + 2) * S)]
    d.line(fl, fill=wall, width=int(4 * S))
    glow = glow.filter(ImageFilter.GaussianBlur(9 * S))
    img = Image.fromarray(np.clip(np.asarray(img, np.int16) + np.asarray(glow, np.int16), 0, 255).astype(np.uint8))
    return img


def curve_points():
    xs = np.linspace(CX - 6.5 * DX + 4, CX + 6.5 * DX - 4, 400)
    u = (xs - CX) / DX
    var = ROWS / 4.0
    n = N / math.sqrt(2 * math.pi * var) * np.exp(-(u ** 2) / (2 * var))
    ys = FLOOR - (n / 4.0) * LAYER - 3
    return xs, ys


def worker_init(seed):
    sim = simulate(seed)
    ST["sim"] = sim
    ST["tl"] = timeline(sim)
    ST["bg"] = make_bg()
    ST["spr"] = [make_sprite(bin_color(b), BR) for b in range(NB)]
    slots = hopper_slots()
    assert len(slots) >= N, len(slots)
    slots = slots[:N]                         # bottom-most N slots
    order = sorted(range(N), key=lambda s: (round(slots[s][1], 1), -abs(slots[s][0] - CX)))   # top row first, outside in
    ST["hop"] = [slots[order[n]] for n in range(N)]      # ball n leaves from this slot
    ST["curve"] = curve_points()


def ease(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def render_frame(vt):
    sim, tl = ST["sim"], ST["tl"]
    t = vt + T0
    img = ST["bg"].copy()
    d = ImageDraw.Draw(img, "RGBA")
    # question / payoff text
    qa = 1.0 - ease((vt - tl["curve0"]) / 0.4)
    if qa > 0:
        draw_text_center(d, 168, "Will they make a perfect curve?", 50, (238, 240, 250, int(255 * qa)))
    pa = ease((vt - tl["perfect"]) / 0.35)
    if pa > 0:
        draw_text_center(d, 160, "Perfect.", 84, (255, 255, 255, int(255 * pa)))
    spr = ST["spr"]
    # hopper contents
    for n, bl in enumerate(sim["balls"]):
        if t < bl["emit"]:
            x, y = ST["hop"][n]
            sp, R = spr[bl["bin"]]
            img.paste(sp, (int(round(x * S)) - R, int(round(y * S)) - R), sp)
    # moving + settled marbles
    for bl in sim["balls"]:
        if t < bl["emit"]:
            continue
        p = ball_pos(bl, t)
        sp, R = spr[bl["bin"]]
        img.paste(sp, (int(round(p[0] * S)) - R, int(round(p[1] * S)) - R), sp)
    # payoff curve
    if vt >= tl["curve0"]:
        u = ease((vt - tl["curve0"]) / (tl["curve1"] - tl["curve0"]))
        xs, ys = ST["curve"]
        m = max(2, int(len(xs) * u))
        pts = [(x * S, y * S) for x, y in zip(xs[:m], ys[:m])]
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.line(pts, fill=(255, 255, 255, 255), width=int(5 * S), joint="curve")
        gl = layer.filter(ImageFilter.GaussianBlur(10 * S))
        pulse = 1.0 + 0.6 * math.exp(-max(0.0, vt - tl["perfect"]) * 3.0) * (vt >= tl["perfect"])
        ga = np.asarray(gl, np.float32)
        ga[..., 3] = np.clip(ga[..., 3] * 1.6 * pulse, 0, 255)
        img.paste(Image.fromarray(ga.astype(np.uint8), "RGBA"), (0, 0), Image.fromarray(ga.astype(np.uint8), "RGBA"))
        img.paste(layer, (0, 0), layer)
        if u < 1.0:
            hx, hy = pts[-1]
            d2 = ImageDraw.Draw(img, "RGBA")
            for rr, a in ((26, 50), (14, 120), (7, 255)):
                d2.ellipse([hx - rr * S / 2 * 2, hy - rr * S / 2 * 2, hx + rr * S / 2 * 2, hy + rr * S / 2 * 2], fill=(255, 255, 255, a))
    return img.resize((W, H), Image.LANCZOS)


def render_bytes(k):
    return render_frame(k / FPS).tobytes()


# ---------------------------------------------------------------- audio
def synth_audio(sim, path):
    tl = timeline(sim)
    total = tl["end"]
    n = int(total * SR) + SR
    out = np.zeros(n, np.float64)
    rng = np.random.default_rng(7)

    def add(sig, t, g=1.0):
        i = int(round((t - T0) * SR))
        if i < 0:
            sig = sig[-i:]
            i = 0
        if i >= n or len(sig) == 0:
            return
        e = min(n, i + len(sig))
        out[i:e] += g * sig[:e - i]

    # density of events (per 0.1 s) for gain riding
    ct = np.array([c[0] for c in sim["clicks"]])
    hist, edges = np.histogram(ct, bins=np.arange(0, ct.max() + 0.2, 0.1))

    def dens(t):
        k = min(len(hist) - 1, max(0, int(t / 0.1)))
        return hist[k]

    tt = np.arange(int(0.012 * SR)) / SR
    click_bank = []
    for _ in range(48):
        f = rng.uniform(3000, 5600)
        s = np.sin(2 * np.pi * f * tt) * np.exp(-tt / 0.0022)
        s += 0.5 * np.sin(2 * np.pi * f * 1.73 * tt) * np.exp(-tt / 0.0015)
        nz = rng.standard_normal(len(tt)) * np.exp(-tt / 0.0005) * 0.6
        click_bank.append(s + nz)
    for t, k in sim["clicks"]:
        g = 0.20 / math.sqrt(max(1.0, dens(t) / 3.0))
        add(click_bank[rng.integers(48)], t + rng.uniform(-0.0006, 0.0006), g * rng.uniform(0.7, 1.0))

    tt2 = np.arange(int(0.07 * SR)) / SR
    tock_bank = []
    for _ in range(32):
        f = rng.uniform(900, 1500)
        s = np.sin(2 * np.pi * f * tt2) * np.exp(-tt2 / 0.012)
        s += 0.4 * np.sin(2 * np.pi * f * 2.41 * tt2) * np.exp(-tt2 / 0.006)
        s += 0.5 * np.sin(2 * np.pi * 260 * tt2) * np.exp(-tt2 / 0.018)
        nz = rng.standard_normal(len(tt2)) * np.exp(-tt2 / 0.0012) * 0.5
        tock_bank.append(s + nz)
    lt = np.array([x[0] for x in sim["tocks"]])
    for t, b, L in sim["tocks"]:
        local = np.sum(np.abs(lt - t) < 0.15)
        g = 0.42 / math.sqrt(max(1.0, local / 1.5))
        g *= 1.25 if L == 0 else 1.0
        add(tock_bank[rng.integers(32)], t, g)

    # hopper rumble: low-passed noise following emission rate
    em = sim["emit"]
    t_axis = np.arange(n) / SR + T0
    rate = np.interp(t_axis, em[1:], 1.0 / np.diff(em), left=0, right=0)
    nz = rng.standard_normal(n)
    a = math.exp(-2 * math.pi * 900 / SR)
    lp = np.zeros(n)
    acc = 0.0
    # vectorised one-pole via lfilter-free cumulative trick (chunks)
    from itertools import accumulate
    lp = np.array(list(accumulate(nz * (1 - a), lambda p, x: p * a + x)))
    out += lp * 0.05 * np.clip(rate / 45.0, 0, 1)

    # payoff whoosh + shimmer along the curve
    c0, c1, pf = tl["curve0"], tl["curve1"], tl["perfect"]
    L = int((c1 - c0 + 0.6) * SR)
    tw = np.arange(L) / SR
    nzw = rng.standard_normal(L)
    env = np.sin(np.pi * np.clip(tw / (c1 - c0 + 0.6), 0, 1)) ** 2
    # crude rising band-pass: difference of two one-poles with moving cutoff
    y1 = y2 = 0.0
    sig = np.zeros(L)
    for i in range(L):
        fc = 400 + 5000 * (i / L) ** 1.5
        k1 = 1 - math.exp(-2 * math.pi * fc * 1.6 / SR)
        k2 = 1 - math.exp(-2 * math.pi * fc / 1.6 / SR)
        y1 += k1 * (nzw[i] - y1)
        y2 += k2 * (nzw[i] - y2)
        sig[i] = y1 - y2
    out_i = int((c0 - 0.1) * SR)
    out[out_i:out_i + L] += sig * env * 0.55
    for _ in range(160):
        t = c0 + rng.random() * (c1 - c0)
        add(click_bank[rng.integers(48)], t + T0, 0.06 * rng.uniform(0.5, 1.0))
    # perfect: deep soft thump + glassy burst
    tb = np.arange(int(1.6 * SR)) / SR
    thump = np.sin(2 * np.pi * (48 + 30 * np.exp(-tb / 0.05)) * tb) * np.exp(-tb / 0.35)
    add(thump, pf + T0, 0.9)
    for _ in range(40):
        add(click_bank[rng.integers(48)], pf + T0 + rng.exponential(0.12), 0.12 * rng.uniform(0.4, 1))

    # gentle high-pass on everything except thump is unnecessary; normalise
    out = out[:int(total * SR)]
    fade = int(0.6 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    out *= 10 ** (-1 / 20) / max(1e-9, np.max(np.abs(out)))
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def _job(sd):
    s = simulate(sd)
    return sd, s["err"], s["asym"], s["counts"].tolist()


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
            res = sorted(p.map(_job, range(a.search)), key=lambda r: r[1] + 0.5 * r[2])
        for r in res[:8]:
            print(r)
    elif a.audio:
        synth_audio(simulate(a.seed), a.audio)
    elif a.frames:
        worker_init(a.seed)
        total = ST["tl"]["end"]
        os.makedirs(a.outdir, exist_ok=True)
        for tok in a.frames.split(","):
            v = float(tok)
            vt = v * total if v <= 1 else v
            render_frame(vt).save(os.path.join(a.outdir, f"k_{vt:06.2f}.png"))
            print("frame", round(vt, 2), "/", round(total, 2), flush=True)
    elif a.out:
        worker_init(a.seed)
        total = ST["tl"]["end"]
        nfr = int(round(total * FPS))
        wav = a.out + ".wav"
        synth_audio(ST["sim"], wav)
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
        print("counts", s["counts"].tolist(), "err", round(s["err"], 1), "timeline",
              {k: round(v, 2) for k, v in timeline(s).items()})
