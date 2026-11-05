"""Every ball freezes where it hits.
Balls are launched from the centre of a circle. The moment a ball touches the wall
or a frozen ball, it freezes there. Launch rate keeps rising until the frozen
structure closes the centre; then every ball pops in a wave, centre outwards.

usage: python3.13 freeze-where-it-hits.py SEED OUTDIR   (sim + render + audio + mux)
"""
import sys, os, math, ctypes, subprocess, wave, colorsys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'engines', 'spike_escape'))
import cr

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 1
OUTDIR = sys.argv[2] if len(sys.argv) > 2 else '.'
SIM_ONLY = '--sim' in sys.argv
W, H, CX, CY, FPS = 1080, 1920, 540.0, 1075.0, 60
RO = 450.0; RING_T = 10.0; RI = RO - RING_T          # ring drawn from RI to RO (900 px outer diameter)
BR = 12.0; G = 520.0; SUB = 8; DT = 1.0 / (FPS * SUB)
TITLE = b"Every ball freezes where it hits"
rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------- simulation
def rate(t):            # launches per second: slow start, keeps accelerating
    return 1.6 + 0.0042 * t ** 2.25

frozen = []             # (x, y, t_freeze, hue, kind)
grid = {}
CELL = 2 * BR
def gkey(x, y): return (int(x // CELL), int(y // CELL))
def near_frozen(x, y, d):
    kx, ky = gkey(x, y); out = []
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for idx in grid.get((kx + i, ky + j), ()):
                fx, fy = frozen[idx][0], frozen[idx][1]
                if (fx - x) ** 2 + (fy - y) ** 2 < d * d: out.append(idx)
    return out

free = []               # dict(x,y,vx,vy,hue,t0)
events = []             # (t, kind, strength, pan)  kind: 0 wall-freeze, 1 ball-freeze, 2 free-free tick, 3 launch, 4 pop
frames = []
t = 0.0; acc = 2.0; nspawn = 0; end_t = None; blocked_t = None
HUE_SPAN = 0.92
while True:
    fi = len(frames)
    if blocked_t is None:
        acc += rate(t) / FPS
        while acc >= 1:
            acc -= 1
            if near_frozen(CX, CY, 2 * BR + 1) or any((b['x'] - CX) ** 2 + (b['y'] - CY) ** 2 < (2 * BR) ** 2 for b in free):
                if near_frozen(CX, CY, 2 * BR + 1): blocked_t = t
                break
            a = rng.uniform(0, 2 * math.pi); s = rng.uniform(520, 900)
            free.append(dict(x=CX, y=CY, vx=s * math.cos(a), vy=s * math.sin(a), hue=nspawn, t0=t))
            nspawn += 1; events.append((t, 3, 0.3, 0.5))
    for _ in range(SUB):
        for b in free:
            b['vy'] += G * DT; b['x'] += b['vx'] * DT; b['y'] += b['vy'] * DT
        # free-free elastic
        n = len(free)
        for i in range(n):
            bi = free[i]
            for j in range(i + 1, n):
                bj = free[j]
                dx = bj['x'] - bi['x']; dy = bj['y'] - bi['y']; d2 = dx * dx + dy * dy
                if d2 < (2 * BR) ** 2 and d2 > 1e-6:
                    d = math.sqrt(d2); nx, ny = dx / d, dy / d
                    rv = (bj['vx'] - bi['vx']) * nx + (bj['vy'] - bi['vy']) * ny
                    ov = 2 * BR - d
                    bi['x'] -= nx * ov / 2; bi['y'] -= ny * ov / 2; bj['x'] += nx * ov / 2; bj['y'] += ny * ov / 2
                    if rv < 0:
                        bi['vx'] += rv * nx; bi['vy'] += rv * ny; bj['vx'] -= rv * nx; bj['vy'] -= rv * ny
                        if -rv > 60: events.append((t, 2, min(1, -rv / 900), (bi['x'] - 90) / 900))
        keep = []
        for b in free:
            x, y = b['x'], b['y']; fz = None
            hit = near_frozen(x, y, 2 * BR)
            if hit:
                # stick to the nearest frozen ball, exactly tangent
                k = min(hit, key=lambda q: (frozen[q][0] - x) ** 2 + (frozen[q][1] - y) ** 2)
                fx, fy = frozen[k][0], frozen[k][1]; dx, dy = x - fx, y - fy; d = math.hypot(dx, dy) or 1
                x, y = fx + dx / d * 2 * BR, fy + dy / d * 2 * BR
                for _ in range(6):   # relax away from any other overlap
                    ok = True
                    for q in near_frozen(x, y, 2 * BR - 0.5):
                        ok = False; qx, qy = frozen[q][0], frozen[q][1]; dx, dy = x - qx, y - qy; d = math.hypot(dx, dy) or 1
                        x, y = qx + dx / d * 2 * BR, qy + dy / d * 2 * BR
                    if ok: break
                fz = 1
            rr = math.hypot(x - CX, y - CY)
            if rr > RI - BR:
                x = CX + (x - CX) / rr * (RI - BR); y = CY + (y - CY) / rr * (RI - BR); fz = 0 if fz is None else fz
            if fz is not None:
                sp = math.hypot(b['vx'], b['vy'])
                idx = len(frozen); frozen.append((x, y, t, b['hue'], fz))
                grid.setdefault(gkey(x, y), []).append(idx)
                events.append((t, fz, min(1, sp / 1100), (x - 90) / 900))
            else:
                keep.append(b)
        free = keep
        t += DT
    frames.append(([(b['x'], b['y'], b['hue']) for b in free], len(frozen)))
    if blocked_t is not None and not free and end_t is None: end_t = t
    if end_t is not None and t > end_t + 0.6: break
    if t > 62: break

NF = len(frozen)
print('seed', SEED, 'balls', NF, 'blocked', blocked_t, 'end', end_t, flush=True)
if SIM_ONLY or blocked_t is None: sys.exit(0)

# pop wave: centre outwards, 2.6 s
POP0 = t; WAVE = 2.6
maxd = max(math.hypot(f[0] - CX, f[1] - CY) for f in frozen)
pop_t = [POP0 + WAVE * (math.hypot(f[0] - CX, f[1] - CY) / maxd) ** 0.8 for f in frozen]
for i, f in enumerate(frozen): events.append((pop_t[i], 4, 0.6, (f[0] - 90) / 900))
TOTAL = POP0 + WAVE + 1.2
NFR = int(TOTAL * FPS)
print('duration', TOTAL, flush=True)

def col(h):
    hh = (0.0 + HUE_SPAN * h / max(1, nspawn - 1)) % 1.0
    return colorsys.hsv_to_rgb(hh, 0.9, 1.0)

parts = []
for i, f in enumerate(frozen):
    c0 = col(f[3])
    for k in range(5):
        a = rng.uniform(0, 2 * math.pi); s = rng.uniform(120, 360)
        parts.append((pop_t[i], f[0], f[1], s * math.cos(a), s * math.sin(a), rng.uniform(2.5, 4.5), c0, 0.45))
parts = sorted(parts)

# ---------------------------------------------------------------- render
surf = cr.surface_create(0, W, H); c = cr.create(surf); stride = cr.get_stride(surf)
cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
te = cr.TE(); cr.text_extents(c, TITLE, ctypes.byref(te))
TX = round((W - te.w) / 2 - te.xb); TY = 440
C1 = np.array([1.0, 0.18, 0.35]); CM = np.array([0.62, 0.22, 1.0]); C2 = np.array([0.10, 0.55, 1.0])
def ringcol(u):
    u = (math.sin(u * 2 * math.pi - math.pi / 2) + 1) / 2   # seamless loop around the ring
    return tuple(C1 * (1 - 2 * u) + CM * 2 * u) if u < 0.5 else tuple(CM * (2 - 2 * u) + C2 * (2 * u - 1))
NSEG = 240
vid = os.path.join(OUTDIR, 'video.mp4')
ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}',
                       '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16',
                       '-pix_fmt', 'yuv420p', vid], stdin=subprocess.PIPE)
for fi in range(NFR):
    tt = (fi + 1) / FPS
    cr.set_rgb(c, 0, 0, 0); cr.paint(c)
    for k in range(NSEG):
        b0 = 2 * math.pi * k / NSEG; b1 = 2 * math.pi * (k + 1) / NSEG + 0.003
        cr.new_path(c); cr.arc(c, CX, CY, RO, b0, b1); cr.arc_negative(c, CX, CY, RI, b1, b0); cr.close_path(c)
        cr.set_rgb(c, *ringcol(k / NSEG)); cr.fill(c)
    fl, nfz = frames[min(fi, len(frames) - 1)]
    for i in range(nfz):
        f = frozen[i]
        if tt >= pop_t[i]: continue
        c0 = col(f[3]); age = tt - f[2]
        if age < 0.09:  # brief lighter flash on freeze (flat colour, no glow)
            m = 1 - age / 0.09; c0 = tuple(v + (1 - v) * 0.6 * m for v in c0)
        r = BR
        if tt > pop_t[i] - 0.08: r = BR * (1 + 0.25 * (1 - (pop_t[i] - tt) / 0.08))
        cr.new_path(c); cr.arc(c, f[0], f[1], r, 0, 2 * math.pi); cr.set_rgb(c, *c0); cr.fill(c)
    for (x, y, h) in fl:
        cr.new_path(c); cr.arc(c, x, y, BR, 0, 2 * math.pi); cr.set_rgb(c, *col(h)); cr.fill(c)
    for (t0, x0, y0, vx, vy, r0, pc, life) in parts:
        if t0 > tt: break
        dt = tt - t0
        if dt > life: continue
        kk = (1 - math.exp(-4 * dt)) / 4
        x, y = x0 + vx * kk, y0 + vy * kk + 200 * dt * dt
        if math.hypot(x - CX, y - CY) > RI - r0: continue
        rp = r0 * (1 - 0.5 * dt / life)
        cr.new_path(c); cr.arc(c, x, y, rp, 0, 2 * math.pi); cr.set_rgb(c, *pc); cr.fill(c)
    cr.move_to(c, TX, TY); cr.set_rgb(c, 1, 1, 1); cr.show_text(c, TITLE)
    cr.flush(surf)
    ff.stdin.write(ctypes.string_at(cr.get_data(surf), stride * H))
    if fi % 600 == 0: print('frame', fi, '/', NFR, flush=True)
ff.stdin.close(); ff.wait()

# ---------------------------------------------------------------- audio (BRUITAGES only: no musical notes)
SR = 48000; N = int(TOTAL * SR) + SR; L = np.zeros(N); R = np.zeros(N)
arng = np.random.default_rng(7)
def add(sig, t0, g, pan):
    pan = min(1, max(0, pan)); i = int(t0 * SR); j = min(N, i + len(sig)); s = sig[:j - i] * g
    L[i:j] += s * math.sqrt(1 - pan); R[i:j] += s * math.sqrt(pan)
def bp_noise(n, fc, q):
    x = arng.standard_normal(n); y = np.zeros(n); w = 2 * math.pi * fc / SR; r = math.exp(-w / (2 * q))
    a1, a2 = 2 * r * math.cos(w), -r * r; y1 = y2 = 0.0
    for k in range(n):
        y0 = x[k] + a1 * y1 + a2 * y2; y[k] = y0; y2, y1 = y1, y0
    return y / (np.abs(y).max() + 1e-9)
BANK = {}
def bank(kind, m=10):
    if kind in BANK: return BANK[kind][arng.integers(m)]
    out = []
    for _ in range(m):
        if kind == 0:     # wall: woody knock + thump
            n = int(0.09 * SR); tt = np.arange(n) / SR
            s = bp_noise(n, arng.uniform(700, 1000), 9) * np.exp(-tt / 0.018)
            s += 0.8 * np.sin(2 * math.pi * (140 + 160 * np.exp(-tt / 0.01)) * tt) * np.exp(-tt / 0.03)
        elif kind == 1:   # stick on a frozen ball: crisp click/clack
            n = int(0.05 * SR); tt = np.arange(n) / SR
            s = bp_noise(n, arng.uniform(2200, 3400), 7) * np.exp(-tt / 0.007)
            s += 0.35 * bp_noise(n, arng.uniform(5000, 6500), 4) * np.exp(-tt / 0.002)
        elif kind == 2:   # free-free tick
            n = int(0.02 * SR); tt = np.arange(n) / SR
            s = bp_noise(n, arng.uniform(3500, 4500), 5) * np.exp(-tt / 0.003)
        elif kind == 3:   # launch: soft puff
            n = int(0.06 * SR); tt = np.arange(n) / SR
            s = bp_noise(n, arng.uniform(400, 700), 1.5) * np.exp(-tt / 0.015) * (1 - np.exp(-tt / 0.004))
        else:             # pop: bubble pop
            n = int(0.06 * SR); tt = np.arange(n) / SR
            f = arng.uniform(700, 1300) * (1 + 2.5 * tt / 0.06)
            s = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.012)
            s += 0.3 * bp_noise(n, 3000, 3) * np.exp(-tt / 0.003)
        s = s * (1 - np.exp(-np.arange(len(s)) / (0.0004 * SR)))
        out.append(s / (np.abs(s).max() + 1e-9))
    BANK[kind] = out; return out[arng.integers(m)]
GAIN = {0: 0.55, 1: 0.5, 2: 0.10, 3: 0.06, 4: 0.22}
for (t0, k, st, pan) in events:
    add(bank(k), t0, GAIN[k] * (0.45 + 0.55 * st), 0.2 + 0.6 * pan)
mix = np.stack([L, R], 1)[:int(TOTAL * SR)]
mix = np.tanh(mix * 1.2) / np.tanh(1.2); mix = mix / np.abs(mix).max() * 0.9
mix *= np.minimum(1, (len(mix) - np.arange(len(mix))) / (0.25 * SR))[:, None]
wav = os.path.join(OUTDIR, 'audio.wav')
w = wave.open(wav, 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
w.writeframes((mix * 32767).astype(np.int16).tobytes()); w.close()
np.save(os.path.join(OUTDIR, 'events.npy'), np.array([(e[0], e[1]) for e in events]))
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', vid, '-i', wav, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                '-shortest', os.path.join(OUTDIR, 'final.mp4')], check=True)
print('done', flush=True)
