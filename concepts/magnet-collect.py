#!/usr/bin/env python3
"""Magnet Collect — one red magnet in the middle of 400 steel bearings.
Every ball it touches snaps on with a click and becomes magnetic too, so the cluster grows
long spiky chains that reach for the stragglers. Counter 400 -> 0.
Payoff: when the last ball snaps on, a pulse of light runs from the magnet out through every
chain, ball by ball, with a cascade of ticks.

Sound mode: BRUITAGES only (synthesized clicks, rolling hiss, ticks, thump). No musical notes.
Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS down to 1080x1920, 60 fps.

    python3.13 magnet-collect.py --seed N                 (simulation summary)
    python3.13 magnet-collect.py --search 20              (seed search)
    python3.13 magnet-collect.py --frames 0,0.3,0.9 --outdir keys/ --seed N
    python3.13 magnet-collect.py --out video.mp4 --seed N
"""
import argparse, math, os, subprocess, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, S = 1080, 1920, 60, 2
SR = 44100
SUB = 6
DT = 1.0 / (FPS * SUB)

N = 400
R = 12.5                     # bearing radius
MR = 30.0                    # magnet radius
MX, MY = 470.0, 1000.0       # magnet position
X0, X1, Y0, Y1 = 50.0, 900.0, 400.0, 1630.0   # free area (keeps 250 px bottom + 140 px right clear)
PRE = 0.0                    # (sim starts at 0; video starts at sim t0, see below)
WAVE_V = 430.0               # px/s of the final light pulse along the chains
SEED = 0


def K_of(t):
    # magnetic strength grows slowly with time so the stragglers always get caught
    return 2.5e5 * (1.0 + 0.05 * t + 0.006 * t * t)


def simulate(seed, tmax=40.0):
    rng = np.random.default_rng(seed)
    pts = []
    tries = 0
    while len(pts) < N and tries < 200000:
        tries += 1
        p = np.array([rng.uniform(X0 + R, X1 - R), rng.uniform(Y0 + R, Y1 - R)])
        if math.hypot(p[0] - MX, p[1] - MY) < MR + 110:
            continue
        if pts and np.min(np.hypot(*(np.array(pts) - p).T)) < 2 * R + 9:
            continue
        pts.append(p)
    assert len(pts) == N, len(pts)
    pos = np.array(pts)
    vel = rng.normal(0, 6, (N, 2))
    free = np.ones(N, bool)
    cl_pos = [np.array([MX, MY])]           # cluster: index 0 = magnet
    cl_rad = [MR]
    cl_par = [-1]
    cl_ball = [-1]                           # cluster idx -> ball idx
    cap_t = np.full(N, np.inf)
    cl_idx_of = np.full(N, -1)
    events = []                              # (t, x, y, speed)
    frames = []
    t = -PRE
    step = 0
    frame_every = SUB
    end_t = None
    while t < tmax:
        if step % frame_every == 0:
            frames.append((t, pos.copy(), free.copy()))
        step += 1
        t += DT
        idx = np.nonzero(free)[0]
        if len(idx) == 0:
            if end_t is None:
                end_t = t
            if t > end_t + 0.05:
                break
            continue
        C = np.array(cl_pos)
        CR = np.array(cl_rad)
        P = pos[idx]
        d = P[:, None, :] - C[None, :, :]
        dist = np.hypot(d[..., 0], d[..., 1])
        gap = dist - CR[None, :]
        j = np.argmin(gap, 1)
        dj = dist[np.arange(len(idx)), j]
        u = -d[np.arange(len(idx)), j] / dj[:, None]
        # force toward nearest cluster element, ~1/r^2, magnet itself a bit stronger
        strength = np.where(j == 0, 1.6, 1.0) * K_of(max(t, 0))
        g = np.maximum(gap[np.arange(len(idx)), j], 14.0)
        acc = u * (strength / (g + 40.0) ** 2)[:, None]
        # mutual repulsion among free balls (soft contact)
        if len(idx) > 1:
            dd = P[:, None, :] - P[None, :, :]
            ds = np.hypot(dd[..., 0], dd[..., 1]) + np.eye(len(idx)) * 1e9
            ov = np.maximum(0, 2 * R - ds)
            push = (dd / ds[..., None]) * (ov * 3000.0)[..., None]
            acc += push.sum(1)
        v = vel[idx] + acc * DT
        v *= math.exp(-1.6 * DT)          # rolling friction
        sp = np.hypot(v[:, 0], v[:, 1])
        cap = 2600.0
        v *= np.minimum(1.0, cap / np.maximum(sp, 1e-6))[:, None]
        P = P + v * DT
        # walls
        for k, lo, hi in ((0, X0 + R, X1 - R), (1, Y0 + R, Y1 - R)):
            lo_m = P[:, k] < lo
            hi_m = P[:, k] > hi
            P[lo_m, k] = lo; v[lo_m, k] = abs(v[lo_m, k]) * 0.3
            P[hi_m, k] = hi; v[hi_m, k] = -abs(v[hi_m, k]) * 0.3
        pos[idx] = P
        vel[idx] = v
        # capture: touching any cluster element
        d = P[:, None, :] - C[None, :, :]
        dist = np.hypot(d[..., 0], d[..., 1])
        touch = dist - CR[None, :] - R
        hits = np.nonzero(touch.min(1) < 0)[0]
        hits = hits[np.argsort(touch.min(1)[hits])]
        for h in hits:
            b = idx[h]
            # re-check against the possibly updated cluster
            Cn = np.array(cl_pos); CRn = np.array(cl_rad)
            dn = pos[b] - Cn
            dist_n = np.hypot(dn[:, 0], dn[:, 1])
            tn = dist_n - CRn - R
            jj = int(np.argmin(tn))
            if tn[jj] >= 0:
                continue
            uu = dn[jj] / max(dist_n[jj], 1e-6)
            newp = Cn[jj] + uu * (CRn[jj] + R)
            # push out of other cluster members if overlapping
            for _ in range(3):
                dn2 = newp - Cn
                dd2 = np.hypot(dn2[:, 0], dn2[:, 1])
                ov = CRn + R - dd2
                ov[jj] = -1
                k = int(np.argmax(ov))
                if ov[k] <= 0.5:
                    break
                newp = newp + dn2[k] / max(dd2[k], 1e-6) * ov[k]
            pos[b] = newp
            speed = float(np.hypot(*vel[b]))
            vel[b] = 0
            free[b] = False
            cap_t[b] = t
            cl_idx_of[b] = len(cl_pos)
            cl_pos.append(newp.copy()); cl_rad.append(R); cl_par.append(jj); cl_ball.append(b)
            events.append((t, float(newp[0]), float(newp[1]), speed))
    # final pulse: path length from the magnet through the tree
    depth = np.zeros(len(cl_pos))
    for c in range(1, len(cl_pos)):
        p = cl_par[c]
        depth[c] = depth[p] + float(np.hypot(*(np.array(cl_pos[c]) - np.array(cl_pos[p]))))
    wave_t = np.full(N, np.inf)
    for c in range(1, len(cl_pos)):
        wave_t[cl_ball[c]] = depth[c] / WAVE_V
    t0 = float(np.sort(cap_t)[2]) - 0.35   # video starts just before the 3rd click
    return dict(frames=frames, events=events, cap_t=cap_t, end_t=end_t, wave_t=wave_t,
                final_pos=pos.copy(), seed=seed, t0=t0)


# ---------------------------------------------------------------- timeline
LAST_HOLD = 0.55     # pause after last click before the pulse
TAIL = 2.2           # after the pulse reaches the tips


def timeline(sim):
    end = sim['end_t']
    wstart = end + LAST_HOLD
    wlen = float(np.max(sim['wave_t']))
    total = wstart + wlen + TAIL - sim['t0']   # video length
    return end, wstart, wlen, total


# ---------------------------------------------------------------- drawing
def sphere_sprite(rad, base, hi, lo, s=S):
    n = int(math.ceil(rad * s * 2)) + 4
    ss = 4
    m = n * ss
    yy, xx = np.mgrid[0:m, 0:m].astype(np.float32)
    c = m / 2
    rr = rad * s * ss
    dx, dy = (xx - c) / rr, (yy - c) / rr
    r2 = dx * dx + dy * dy
    inside = r2 <= 1
    z = np.sqrt(np.clip(1 - r2, 0, 1))
    L = np.array([-0.45, -0.6, 0.66]); L /= np.linalg.norm(L)
    lam = np.clip(dx * L[0] + dy * L[1] + z * L[2], 0, 1)
    # reflection vector for specular
    rz = 2 * z * z - 1
    spec = np.clip((2 * lam * z - L[2]), 0, 1) ** 1
    hx, hy = dx + 0.38, dy + 0.42
    spot = np.exp(-(hx * hx + hy * hy) / 0.035)
    rim = np.clip((r2 - 0.7) / 0.3, 0, 1) * np.clip(dy + 0.2, 0, 1) * 0.35   # bounce light from below
    base = np.array(base, np.float32); hi = np.array(hi, np.float32); lo = np.array(lo, np.float32)
    col = lo[None, None] + (base - lo)[None, None] * lam[..., None] ** 0.9
    # environment band reflection (chrome look)
    band = np.exp(-((dy + 0.05 - 0.25 * dx) ** 2) / 0.02) * 0.25
    col = col + (hi - col) * np.clip(spot * 0.95 + band + rim, 0, 1)[..., None]
    a = np.clip((1 - np.sqrt(r2)) * rr / 1.0 + 0.5, 0, 1)
    img = np.dstack([np.clip(col, 0, 255), a * 255]).astype(np.uint8)
    im = Image.fromarray(img, 'RGBA').resize((n, n), Image.LANCZOS)
    return im


def shadow_sprite(rad, s=S):
    n = int(math.ceil(rad * s * 3.2))
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = n / 2
    d = np.hypot(xx - c, (yy - c) * 1.1) / (rad * s)
    a = np.clip(1.25 - d, 0, 1) ** 1.6 * 120
    img = np.zeros((n, n, 4), np.uint8)
    img[..., 3] = a.astype(np.uint8)
    return Image.fromarray(img, 'RGBA').filter(ImageFilter.GaussianBlur(rad * s * 0.18))


def glow_sprite(rad, color, s=S):
    n = int(math.ceil(rad * s * 6))
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = n / 2
    d = np.hypot(xx - c, yy - c) / (rad * s)
    a = np.exp(-d * d / 3.0)
    img = np.zeros((n, n, 4), np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = color
    img[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(img, 'RGBA')


def background():
    yy, xx = np.mgrid[0:H * S, 0:W * S].astype(np.float32)
    cx, cy = MX * S, MY * S
    d = np.hypot(xx - cx, (yy - cy) * 0.85) / (H * S * 0.6)
    v = np.clip(1 - d, 0, 1) ** 1.4
    r = 13 + 17 * v; g = 14 + 17 * v; b = 18 + 20 * v
    # fine brushed grain
    rng = np.random.default_rng(1)
    grain = rng.normal(0, 1.2, (H * S, W * S)).astype(np.float32)
    img = np.dstack([r + grain, g + grain, b + grain])
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGB').convert('RGBA')


G = {}


def font(sz):
    for f in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',):
        if os.path.exists(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


def init_worker(seed):
    if 'sim' in G:          # already built in the parent (fork)
        return
    sim = simulate(seed)
    G['sim'] = sim
    G['tl'] = timeline(sim)
    G['bg'] = background()
    G['ball'] = sphere_sprite(R, (190, 196, 206), (255, 255, 255), (38, 42, 52))
    G['ballw'] = sphere_sprite(R, (255, 236, 190), (255, 255, 255), (120, 90, 50))
    G['mag'] = sphere_sprite(MR, (215, 40, 50), (255, 225, 220), (60, 6, 12))
    G['sh'] = shadow_sprite(R)
    G['shm'] = shadow_sprite(MR)
    G['glow'] = glow_sprite(R, (255, 210, 140))
    G['mglow'] = glow_sprite(MR, (255, 60, 60))
    G['f_q'] = font(50 * S)
    G['f_n'] = font(118 * S)


def paste_c(img, spr, x, y, ox=0, oy=0):
    w, h = spr.size
    img.alpha_composite(spr, (int(round(x * S - w / 2 + ox)), int(round(y * S - h / 2 + oy))))


def state_at(t):
    sim = G['sim']
    frames = sim['frames']
    end, wstart, wlen, total = G['tl']
    if t <= frames[-1][0]:
        i = int(round(t * FPS))
        i = max(0, min(len(frames) - 1, i))
        return frames[i]
    return frames[-1]


def render(fi):
    sim = G['sim']
    end, wstart, wlen, total = G['tl']
    t = fi / FPS + sim['t0']
    ft, pos, free = state_at(t)
    img = G['bg'].copy()
    cap_t = sim['cap_t']
    wave_t = sim['wave_t']
    # shadows
    so = 5 * S
    paste_c(img, G['shm'], MX, MY, so, so * 1.3)
    for i in range(N):
        paste_c(img, G['sh'], pos[i, 0], pos[i, 1], so * 0.6, so * 0.8)
    # magnet glow pulse
    wt = t - wstart
    mg = G['mglow'].copy()
    ga = 0.35 + 0.15 * math.sin(t * 3.0)
    if wt > -0.05:
        ga = 0.5 + 0.5 * math.exp(-max(wt, 0) * 2.0)
    mg.putalpha(mg.getchannel('A').point(lambda v: int(v * ga)))
    paste_c(img, mg, MX, MY)
    # balls
    glow_layer = []
    for i in range(N):
        flash = 0.0
        if not free[i]:
            dtc = t - cap_t[i]
            if 0 <= dtc < 0.18:
                flash = max(flash, 1 - dtc / 0.18) * 0.8
            if wt >= 0:
                dw = wt - wave_t[i]
                if dw >= 0:
                    flash = max(flash, 0.62 + 0.38 * math.exp(-dw * 3.2))   # the pulse leaves it gold
        if flash > 0.02:
            spr = Image.blend(G['ball'], G['ballw'], min(1, flash))
            paste_c(img, spr, pos[i, 0], pos[i, 1])
            glow_layer.append((i, flash))
        else:
            paste_c(img, G['ball'], pos[i, 0], pos[i, 1])
    paste_c(img, G['mag'], MX, MY)
    if glow_layer:
        gl = Image.new('RGBA', img.size, (0, 0, 0, 0))
        for i, f in glow_layer:
            g = G['glow']
            g2 = g.copy(); g2.putalpha(g.getchannel('A').point(lambda v: int(v * f * 0.55)))
            paste_c(gl, g2, pos[i, 0], pos[i, 1])
        img.alpha_composite(gl)
    # text
    d = ImageDraw.Draw(img)
    left = int(free.sum())
    q = "Can 1 magnet catch all 400?"
    tw = d.textlength(q, font=G['f_q'])
    d.text(((940 * S - tw) / 2, 175 * S), q, font=G['f_q'], fill=(236, 238, 242, 255))
    num = str(left)
    col = (236, 238, 242, 255) if left > 0 else (255, 214, 140, 255)
    tw = d.textlength(num, font=G['f_n'])
    d.text(((940 * S - tw) / 2, 245 * S), num, font=G['f_n'], fill=col)
    out = img.convert('RGB').resize((W, H), Image.LANCZOS)
    return out


def render_bytes(fi):
    return render(fi).tobytes()


# ---------------------------------------------------------------- audio
def synth_audio(sim, total):
    n = int(total * SR) + SR
    L = np.zeros(n); Rr = np.zeros(n)
    rng = np.random.default_rng(7)
    end, wstart, wlen, _ = timeline(sim)

    def add(sig, t, pan, gain):
        i = int(round((t - sim['t0']) * SR))
        if i < 0 or i >= n:
            return
        m = min(len(sig), n - i)
        L[i:i + m] += sig[:m] * gain * math.sqrt(1 - pan)
        Rr[i:i + m] += sig[:m] * gain * math.sqrt(pan)

    def click(speed, bright=1.0):
        dur = 0.09
        tt = np.arange(int(dur * SR)) / SR
        sig = np.zeros_like(tt)
        f0 = rng.uniform(2600, 3400) * bright
        for ratio, dec, a in ((1.0, 55, 1.0), (1.53, 80, 0.6), (2.41, 120, 0.4), (3.7, 180, 0.25)):
            sig += a * np.sin(2 * math.pi * f0 * ratio * tt + rng.uniform(0, 6)) * np.exp(-dec * tt)
        noise = rng.normal(0, 1, len(tt)) * np.exp(-tt * 900)
        sig = sig * 0.5 + noise * 0.6
        # body thunk
        sig += 0.35 * np.sin(2 * math.pi * rng.uniform(380, 520) * tt) * np.exp(-tt * 70)
        return sig

    # capture clicks
    for (t, x, y, sp) in sim['events']:
        g = 0.18 + 0.32 * min(1.0, sp / 900.0)
        add(click(sp), t, np.clip(x / W, 0.15, 0.85), g)
    # rolling hiss ~ total free speed
    frames = sim['frames']
    env = np.zeros(len(frames))
    prev = None
    for k, (t, pos, free) in enumerate(frames):
        if prev is not None:
            v = np.hypot(*(pos - prev).T) * FPS
            env[k] = np.sqrt(np.sum(np.minimum(v[free], 1500)) / 4.0e5)
        prev = pos
    tt_env = np.arange(len(frames)) / FPS
    nn = n
    e = np.interp(np.arange(nn) / SR + sim['t0'], tt_env, env, right=0)
    noise = rng.normal(0, 1, nn)
    # simple lowpass via moving average twice
    k = 18
    noise = np.convolve(noise, np.ones(k) / k, 'same')
    noise = np.convolve(noise, np.ones(k) / k, 'same')
    hiss = noise * e * 0.9
    L[:nn] += hiss; Rr[:nn] += hiss
    # final pulse: tick per ball as the light passes, high and soft
    for i in np.argsort(sim['wave_t']):
        tw = wstart + sim['wave_t'][i]
        x = sim['final_pos'][i, 0]
        add(click(300, bright=1.35), tw, np.clip(x / W, 0.1, 0.9), 0.07)
    # thump + metallic shimmer at the pulse start
    tt = np.arange(int(2.5 * SR)) / SR
    thump = np.sin(2 * math.pi * (55 + 40 * np.exp(-tt * 12)) * tt) * np.exp(-tt * 3.5)
    add(thump, wstart, 0.5, 0.75)
    shim = np.zeros_like(tt)
    for f, a in ((1870, 1.0), (2913, 0.7), (4377, 0.5), (6120, 0.35), (1123, 0.5)):
        shim += a * np.sin(2 * math.pi * f * tt + rng.uniform(0, 6)) * np.exp(-tt * 1.6)
    shim *= (1 - np.exp(-tt * 300))
    add(shim, wstart, 0.5, 0.10)
    # soft reverb: a few delayed copies
    for dl, g in ((0.031, 0.25), (0.047, 0.18), (0.071, 0.12), (0.113, 0.08)):
        di = int(dl * SR)
        L[di:] += np.copy(Rr[:-di]) * g
        Rr[di:] += np.copy(L[:-di]) * g
    st = np.stack([L, Rr], 1)[:int(total * SR)]
    st *= 10 ** (-1 / 20) / max(1e-6, np.max(np.abs(st)))
    return (st * 32767).astype(np.int16)


# ---------------------------------------------------------------- main
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
            sim = simulate(s)
            end, ws, wl, tot = timeline(sim)
            last = sorted(sim['cap_t'])[-5:]
            print(s, 'end', round(end, 2), 'total', round(tot + PRE, 2), 'last gaps', np.round(np.diff(last), 2))
        return
    init_worker(a.seed)
    sim = G['sim']
    end, ws, wl, tot = G['tl']
    nfr = int(tot * FPS)
    ct = np.sort(sim['cap_t'])
    print('t0', sim['t0'], 'end', end, 'wave', wl, 'video', tot, 'frames', nfr)
    print('captured at 25/50/75/90%:', [round(ct[int(N * q) - 1], 2) for q in (0.25, 0.5, 0.75, 0.9)])
    if a.frames:
        os.makedirs(a.outdir, exist_ok=True)
        for f in a.frames.split(','):
            fi = int(float(f) * (nfr - 1))
            render(fi).save(os.path.join(a.outdir, f'k_{fi:05d}.png'))
        return
    if a.out:
        audio = synth_audio(sim, tot)
        wav = a.out + '.wav'
        with wave.open(wav, 'wb') as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(audio.tobytes())
        p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                              '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', wav,
                              '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p',
                              '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', a.out],
                             stdin=subprocess.PIPE)
        with Pool(os.cpu_count(), initializer=init_worker, initargs=(a.seed,)) as pool:
            for b in pool.imap(render_bytes, range(nfr), chunksize=8):
                p.stdin.write(b)
        p.stdin.close(); p.wait()
        os.remove(wav)
        print('wrote', a.out)


if __name__ == '__main__':
    main()
