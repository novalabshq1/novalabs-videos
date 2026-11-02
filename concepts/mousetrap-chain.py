#!/usr/bin/env python3
"""Mousetrap Chain — 1 ping-pong ball falls on a floor of 300 armed mousetraps.
Each trap carries 2 balls; when a ball lands on an armed trap it SNAPS and throws its 2 balls.
Chain reaction, counter 0 / 300. The last traps glow; the 300th snap ends it.

Sound mode: BRUITAGES only (synthesized snaps, ping-pong bounces, wall knocks). No music.

Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS down to 1080x1920, 60 fps.

    python3 mousetrap-chain.py --search 40          (seed search)
    python3 mousetrap-chain.py --seed N             (summary)
    python3 mousetrap-chain.py --seed N --frames 0,1,5,10 --outdir keys/
    python3 mousetrap-chain.py --seed N --out video.mp4
"""
import argparse, math, os, subprocess, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, S = 1080, 1920, 60, 2
SR = 48000
SUB = 4
DT = 1.0 / (FPS * SUB)

X0, X1, Y0, Y1 = 80.0, 920.0, 360.0, 1600.0       # floor
COLS, ROWS = 15, 20
SPX, SPY = (X1 - X0) / COLS, (Y1 - Y0) / ROWS      # 56 x 62
TW, TH = 44.0, 32.0                                 # trap size
BR = 8.0                                            # ball radius
G = 950.0
ZK = 0.80                                           # screen lift per unit of height
TSCALE = 0.62                                       # simulation slow-motion factor
HOLD = 3.6
SEED = 1

FONT_B = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
FONT_S = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"


def trap_centers():
    xs = X0 + SPX * (np.arange(COLS) + 0.5)
    ys = Y0 + SPY * (np.arange(ROWS) + 0.5)
    gx, gy = np.meshgrid(xs, ys)
    return np.stack([gx.ravel(), gy.ravel()], 1)


TRAPS = trap_centers()
NT = len(TRAPS)
FIRST = (ROWS // 2) * COLS + COLS // 2


def simulate(seed, tmax=60.0, record=True):
    rng = np.random.default_rng(seed)
    cap = 2 * NT + 1
    pos = np.zeros((cap, 2)); z = np.zeros(cap); vel = np.zeros((cap, 2)); vz = np.zeros(cap)
    state = np.zeros(cap, int)          # 0 = sitting on trap (hidden in sim), 1 flying/rolling, 2 resting
    nb = 1
    pos[0] = TRAPS[FIRST] + [rng.uniform(-5, 5), rng.uniform(-4, 4)]
    z[0] = 170.0; vz[0] = -250.0; state[0] = 1
    snap_t = np.full(NT, np.inf)
    snap_dir = np.ones(NT)
    ball_trap = {}                       # ball index -> trap it sat on
    events = []                          # (t, kind, x, strength)
    frames = []
    t = 0.0; step = 0; count = 0; end_t = None
    fdt = 1.0 / FPS
    while t < tmax:
        sdt = DT * (0.80 - 0.30 * min(1.0, count / 140.0))
        act = state == 1
        idx = np.nonzero(act)[0]
        if len(idx):
            pos[idx] += vel[idx] * sdt
            vz[idx] -= G * sdt
            z[idx] += vz[idx] * sdt
            # walls
            for k, lo, hi in ((0, X0 + BR, X1 - BR), (1, Y0 + BR, Y1 - BR)):
                lo_hit = idx[pos[idx, k] < lo]; hi_hit = idx[pos[idx, k] > hi]
                for b in lo_hit:
                    pos[b, k] = lo; s = abs(vel[b, k]); vel[b, k] = s * 0.75
                    if s > 60: events.append((t, 'wall', pos[b, 0], min(1, s / 300)))
                for b in hi_hit:
                    pos[b, k] = hi; s = abs(vel[b, k]); vel[b, k] = -s * 0.75
                    if s > 60: events.append((t, 'wall', pos[b, 0], min(1, s / 300)))
            # floor
            land = idx[(z[idx] < 0) & (vz[idx] < 0)]
            for b in land:
                v = -vz[b]
                z[b] = 0.0
                # trap trigger
                d = np.abs(TRAPS - pos[b])
                hit = np.nonzero((d[:, 0] < TW / 2 + 2) & (d[:, 1] < TH / 2 + 2) & ~np.isfinite(snap_t))[0]
                if len(hit) and v > 90 and ball_trap.get(b, -1) not in hit:
                    tr = hit[0]
                    snap_t[tr] = t; count += 1
                    snap_dir[tr] = 1.0 if rng.random() < 0.5 else -1.0
                    events.append((t, 'snap', TRAPS[tr, 0], 1.0))
                    if count == NT:
                        end_t = t
                    for off in (-1, 1):
                        nbi = nb; nb += 1
                        pos[nbi] = TRAPS[tr] + [off * 10.0, 0.0]
                        z[nbi] = 6.0
                        a = rng.uniform(0, 2 * math.pi)
                        sp = rng.uniform(70, 230)
                        vel[nbi] = [math.cos(a) * sp, math.sin(a) * sp]
                        vz[nbi] = rng.uniform(380, 540)
                        state[nbi] = 1
                        ball_trap[nbi] = tr
                    # the landing ball gets kicked by the snapping bar
                    vz[b] = v * 0.5 + 120; vel[b] *= 0.8
                    events.append((t, 'bounce', pos[b, 0], min(1, v / 500)))
                    continue
                if v > 45:
                    vz[b] = v * 0.68
                    vel[b] *= 0.92
                    events.append((t, 'bounce', pos[b, 0], min(1, v / 500)))
                else:
                    vz[b] = 0.0; z[b] = 0.0; state[b] = 2
                    if v > 25: events.append((t, 'bounce', pos[b, 0], v / 500))
        # rolling friction for resting balls; a rolling ball that bumps an armed trap trips it
        rest = np.nonzero(state == 2)[0]
        for b in rest:
            if vel[b, 0] ** 2 + vel[b, 1] ** 2 < 35 ** 2:
                continue
            d = np.abs(TRAPS - pos[b])
            hit = np.nonzero((d[:, 0] < TW / 2) & (d[:, 1] < TH / 2) & ~np.isfinite(snap_t))[0]
            if len(hit) and ball_trap.get(b, -1) not in hit:
                tr = hit[0]
                snap_t[tr] = t; count += 1
                snap_dir[tr] = 1.0 if rng.random() < 0.5 else -1.0
                events.append((t, 'snap', TRAPS[tr, 0], 1.0))
                if count == NT:
                    end_t = t
                for off in (-1, 1):
                    nbi = nb; nb += 1
                    pos[nbi] = TRAPS[tr] + [off * 10.0, 0.0]
                    z[nbi] = 6.0
                    a = rng.uniform(0, 2 * math.pi)
                    sp = rng.uniform(70, 230)
                    vel[nbi] = [math.cos(a) * sp, math.sin(a) * sp]
                    vz[nbi] = rng.uniform(380, 540)
                    state[nbi] = 1
                    ball_trap[nbi] = tr
                state[b] = 1; vz[b] = 260.0; z[b] = 1.0
        rest = np.nonzero(state == 2)[0]
        if len(rest):
            sp = np.hypot(vel[rest, 0], vel[rest, 1])
            ns = np.maximum(0, sp - 120 * sdt)
            f = np.where(sp > 1e-6, ns / np.maximum(sp, 1e-6), 0)
            vel[rest] *= f[:, None]
            pos[rest] += vel[rest] * sdt
            pos[rest, 0] = np.clip(pos[rest, 0], X0 + BR, X1 - BR)
            pos[rest, 1] = np.clip(pos[rest, 1], Y0 + BR, Y1 - BR)
        step += 1
        t = step * DT
        if step % SUB == 0 and record:
            frames.append((pos[:nb].copy(), z[:nb].copy(), state[:nb].copy(), count))
        if end_t is not None and t > end_t + HOLD:
            break
        if end_t is None and len(idx) == 0 and step > 10:
            break                                   # chain died
    return dict(frames=frames, events=events, snap_t=snap_t, snap_dir=snap_dir,
                end_t=end_t, count=count, nb=nb)


def summary(sim):
    st = sim['snap_t']
    fin = np.sort(st[np.isfinite(st)])
    marks = {k: (round(float(fin[k - 1]), 2) if len(fin) >= k else None) for k in (10, 50, 150, 250, 290, 295, 299, 300)}
    return sim['count'], sim['end_t'], marks


# ----------------------------------------------------------------------------- render
BG_TOP = np.array([14, 16, 26]); BG_BOT = np.array([22, 18, 34])


def ease(x):
    x = min(1, max(0, x))
    return x * x * (3 - 2 * x)


def camera(t):
    """zoom from the first trap (x3.2) to the whole floor (x1)."""
    e = ease((t - 0.4) / 6.0)
    zoom = 3.2 * (1 - e) + 1.0 * e
    c0 = TRAPS[FIRST] + [0, -40]
    c1 = np.array([(X0 + X1) / 2, (Y0 + Y1) / 2])
    c = c0 * (1 - e) + c1 * e
    return zoom, c


def make_bg():
    g = np.linspace(0, 1, H * S)[:, None]
    col = (BG_TOP * (1 - g) + BG_BOT * g).astype(np.uint8)
    arr = np.repeat(col[:, None, :], W * S, 1)
    return Image.fromarray(arr.reshape(H * S, W * S, 3))


_BG = None
LAST = [0]
_FB = None


def lerp(a, b, u):
    return tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))


def render(sim, fi):
    global _BG, _FB
    if _BG is None:
        _BG = make_bg()
        _FB = (ImageFont.truetype(FONT_B, 66 * S), ImageFont.truetype(FONT_B, 150 * S),
               ImageFont.truetype(FONT_S, 44 * S))
    t = fi / FPS
    pos, z, state, count = sim['frames'][min(fi, len(sim['frames']) - 1)]
    st = sim['snap_t']; end_t = sim['end_t']
    if end_t is not None:
        LAST[0] = int(np.argmax(np.where(np.isfinite(st), st, -1)))
    zoom, c = camera(t)
    sx = lambda x: ((x - c[0]) * zoom + 500) * S
    sy = lambda y: ((y - c[1]) * zoom + 980) * S
    img = _BG.copy()
    d = ImageDraw.Draw(img, 'RGBA')
    # floor
    d.rounded_rectangle([sx(X0 - 14), sy(Y0 - 14), sx(X1 + 14), sy(Y1 + 14)], radius=int(22 * zoom * S),
                        fill=(28, 30, 44), outline=(58, 60, 84), width=max(2, int(3 * zoom * S)))
    remaining = NT - count
    pulse = 0.5 + 0.5 * math.sin(t * 9)
    for i in range(NT):
        x, y = TRAPS[i]
        X, Y = sx(x), sy(y)
        hw, hh = TW / 2 * zoom * S, TH / 2 * zoom * S
        if X < -100 or X > W * S + 100 or Y < -100 or Y > H * S + 100:
            continue
        snapped = t >= st[i]
        age = t - st[i] if snapped else -1
        if remaining <= 6 and not snapped and end_t is not None:
            gr = (16 + 10 * pulse) * zoom * S
            d.rounded_rectangle([X - hw - gr, Y - hh - gr, X + hw + gr, Y + hh + gr], radius=int(gr + 6 * S),
                                fill=(255, 190, 70, int(70 + 80 * pulse)))
            rr = (40 + 14 * pulse) * zoom * S
            d.ellipse([X - rr, Y - rr, X + rr, Y + rr], outline=(255, 210, 110, int(120 + 100 * pulse)),
                      width=max(2, int(3 * zoom * S)))
        wood = (226, 180, 118) if not snapped else lerp((226, 180, 118), (112, 84, 62), min(1, age / 0.5))
        if end_t is not None and t > end_t:
            # golden wave rolling out from the 300th trap
            dist = math.hypot(x - TRAPS[LAST[0]][0], y - TRAPS[LAST[0]][1])
            w = (t - end_t) * 900 - dist
            if w > 0:
                wood = lerp((255, 236, 170), (232, 178, 80), min(1, w / 260))
        d.rounded_rectangle([X - hw, Y - hh, X + hw, Y + hh], radius=int(5 * zoom * S), fill=wood,
                            outline=lerp(wood, (40, 28, 20), 0.45), width=max(1, int(1.6 * zoom * S)))
        # wire bar: armed on one half, flips over the hinge in 50 ms
        dirn = sim['snap_dir'][i]
        if not snapped:
            u = -1.0
        else:
            u = min(1.0, -1.0 + 2.0 * age / 0.05)
        bw = (TW / 2 - 4) * zoom * S * u * dirn
        by = (TH / 2 - 5) * zoom * S
        metal = (205, 210, 222) if not snapped else (150, 154, 166)
        lw = max(2, int(2.6 * zoom * S))
        x2 = X + bw
        d.line([X, Y - by, x2, Y - by], fill=metal, width=lw)
        d.line([x2, Y - by, x2, Y + by], fill=metal, width=lw)
        d.line([X, Y + by, x2, Y + by], fill=metal, width=lw)
        d.line([X, Y - by - 2 * S, X, Y + by + 2 * S], fill=(90, 70, 55), width=lw)   # hinge
        if not snapped:
            # its 2 balls
            for off in (-1, 1):
                bx, byy = X + off * 10 * zoom * S, Y
                r = BR * zoom * S
                d.ellipse([bx - r + 2 * S, byy - r + 3 * S, bx + r + 2 * S, byy + r + 3 * S], fill=(0, 0, 0, 70))
                d.ellipse([bx - r, byy - r, bx + r, byy + r], fill=(246, 244, 238))
                r2 = r * 0.38
                d.ellipse([bx - r * 0.45 - r2, byy - r * 0.45 - r2, bx - r * 0.45 + r2, byy - r * 0.45 + r2],
                          fill=(255, 255, 255))
        elif age < 0.3:
            k = age / 0.3
            rr = (22 + 40 * k) * zoom * S
            d.ellipse([X - rr, Y - rr, X + rr, Y + rr], outline=(255, 236, 200, int(200 * (1 - k))),
                      width=max(2, int(3 * zoom * S)))
    # balls: shadows then bodies, painter order
    vis = np.nonzero(state > 0)[0]
    order = vis[np.argsort(pos[vis, 1] + z[vis] * 0.01)]
    for b in order:
        X, Y = sx(pos[b, 0]), sy(pos[b, 1])
        r = BR * zoom * S
        sh = r * (1 + z[b] / 600)
        a = int(90 * max(0.25, 1 - z[b] / 500))
        d.ellipse([X - sh, Y - sh * 0.7 + 2 * S, X + sh, Y + sh * 0.7 + 2 * S], fill=(0, 0, 0, a))
    for b in order:
        X, Y = sx(pos[b, 0]), sy(pos[b, 1] - z[b] * ZK)
        r = BR * zoom * S * (1 + z[b] / 1400)
        d.ellipse([X - r, Y - r, X + r, Y + r], fill=(246, 244, 238))
        r2 = r * 0.38
        d.ellipse([X - r * 0.45 - r2, Y - r * 0.45 - r2, X - r * 0.45 + r2, Y - r * 0.45 + r2], fill=(255, 255, 255))
    # header band so nothing runs under the text
    d.rectangle([0, 0, W * S, 330 * S], fill=(14, 16, 26))
    for k in range(40):
        d.rectangle([0, (330 + k) * S, W * S, (331 + k) * S], fill=(14, 16, 26, int(255 * (1 - k / 40))))
    # text
    fq, fc, fs = _FB
    done = end_t is not None and t >= end_t
    q = "Will all 300 go off?"
    d.text((500 * S, 150 * S), q, font=fq, fill=(240, 240, 248), anchor='mm')
    ctext = f"{count} / {NT}"
    if done:
        k = min(1, (t - end_t) / 0.25)
        col = lerp((255, 255, 255), (255, 200, 80), k)
        sc = 1 + 0.18 * math.exp(-(t - end_t) * 6) * math.sin(min(math.pi, (t - end_t) * 12))
    else:
        col = (255, 255, 255); sc = 1.0
    if sc != 1.0:
        f2 = ImageFont.truetype(FONT_B, int(150 * S * sc))
    else:
        f2 = fc
    d.text((500 * S, 285 * S), ctext, font=f2, fill=col, anchor='mm')
    if done:
        # gold flash over everything at the final snap
        k = (t - end_t)
        if k < 0.5:
            ov = Image.new('RGB', img.size, (255, 220, 150))
            img = Image.blend(img, ov, 0.35 * (1 - k / 0.5))
    return img.resize((W, H), Image.LANCZOS)


# ----------------------------------------------------------------------------- audio
def synth(sim, dur, seed):
    rng = np.random.default_rng(seed + 99)
    n = int(dur * SR) + SR
    L = np.zeros(n); R = np.zeros(n)

    def tone(f, dec, length, phase_noise=0.0):
        tt = np.arange(int(length * SR)) / SR
        return np.sin(2 * math.pi * f * tt) * np.exp(-tt / dec)

    def noise(length, dec):
        tt = np.arange(int(length * SR)) / SR
        x = rng.standard_normal(len(tt))
        x = np.diff(np.concatenate([[0], x]))       # crude high-pass
        return x * np.exp(-tt / dec)

    def mix(*parts):
        m = max(len(p) for p in parts)
        out = np.zeros(m)
        for p in parts:
            out[:len(p)] += p
        return out

    def add(sig, t, x, gain):
        i = int(t * SR)
        if i >= n: return
        sig = sig[:n - i]
        p = (x - X0) / (X1 - X0)          # 0..1
        p = 0.5 + (p - 0.5) * 0.7
        L[i:i + len(sig)] += sig * gain * math.cos(p * math.pi / 2) * 1.414
        R[i:i + len(sig)] += sig * gain * math.sin(p * math.pi / 2) * 1.414

    ev = sim['events']
    # density-aware gain so the crackle doesn't wall up
    times = np.array([e[0] * TSCALE / TSCALE for e in ev]) if ev else np.zeros(0)
    end_t = sim['end_t']
    for (t, kind, x, s) in ev:
        dens = np.sum(np.abs(times - t) < 0.05)
        dg = 1.0 / math.sqrt(max(1, dens / 2))
        if kind == 'snap':
            f = rng.uniform(0.9, 1.12)
            sig = mix(noise(0.012, 0.0018) * 0.9, tone(1150 * f, 0.010, 0.06) * 0.8, tone(2350 * f, 0.006, 0.04) * 0.4,
                      tone(3150 * f, 0.045, 0.15) * 0.10, tone(420 * f, 0.02, 0.08) * 0.5)
            gain = 0.55 * dg
            if end_t is not None and abs(t - end_t) < 1e-6:
                gain = 1.0
                sig = mix(sig, tone(95, 0.18, 0.7) * 0.9, noise(0.4, 0.09) * 0.25)
            add(sig, t, x, gain)
        elif kind == 'bounce':
            f = rng.uniform(0.92, 1.08) * (1500 + 500 * s)
            sig = mix(tone(f, 0.009, 0.04), noise(0.006, 0.0012) * 0.5, tone(f * 0.52, 0.006, 0.03) * 0.4)
            add(sig, t, x, 0.30 * (0.2 + s) * dg)
        else:
            sig = mix(tone(520 * rng.uniform(0.9, 1.1), 0.012, 0.06), noise(0.008, 0.002) * 0.6)
            add(sig, t, x, 0.22 * s * dg)
    # first ball "whoosh" falling at start (filtered noise swell)
    st = np.stack([L, R], 1)[:int(dur * SR)]
    st = np.tanh(st * 1.3) / np.tanh(1.3)
    pk = np.max(np.abs(st)) + 1e-9
    st = st / pk * 0.89
    fade = int(0.4 * SR)
    st[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return st


def write_wav(path, st):
    data = (st * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data.tobytes())


# ----------------------------------------------------------------------------- main
_SIM = None


def _init(seed):
    global _SIM
    _SIM = simulate(seed)
    # event times must be in VIDEO time: simulation time t is already video time (DT * steps)


def _rf(fi):
    return render(_SIM, fi).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=SEED)
    ap.add_argument('--search', type=int, default=0)
    ap.add_argument('--frames', default='')
    ap.add_argument('--outdir', default='keys')
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    if a.search:
        for s in range(a.search):
            sim = simulate(s, record=False)
            print(s, *summary(sim), flush=True)
        return
    sim = simulate(a.seed)
    print(*summary(sim))
    nf = len(sim['frames'])
    print('frames', nf, 'dur', nf / FPS, 'balls', sim['nb'])
    if a.frames:
        os.makedirs(a.outdir, exist_ok=True)
        for tt in a.frames.split(','):
            fi = min(nf - 1, int(float(tt) * FPS))
            render(sim, fi).save(os.path.join(a.outdir, f'f_{float(tt):05.2f}.png'))
        return
    if a.out:
        dur = nf / FPS
        wav = a.out + '.wav'
        write_wav(wav, synth(sim, dur, a.seed))
        tmp = a.out + '.v.mp4'
        p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                              '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'medium',
                              '-crf', '17', '-pix_fmt', 'yuv420p', tmp], stdin=subprocess.PIPE)
        with Pool(4, initializer=_init, initargs=(a.seed,)) as pool:
            for k, buf in enumerate(pool.imap(_rf, range(nf), chunksize=8)):
                p.stdin.write(buf)
                if k % 300 == 0: print('frame', k, flush=True)
        p.stdin.close(); p.wait()
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', tmp, '-i', wav, '-c:v', 'copy', '-c:a', 'aac',
                        '-b:a', '192k', '-shortest', '-movflags', '+faststart', a.out], check=True)
        os.remove(tmp)
        print('done', a.out)


if __name__ == '__main__':
    main()
