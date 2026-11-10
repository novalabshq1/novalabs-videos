# ESCAPE (evening format) — GROW rule (every bounce makes the ball bigger, bigger than the opening = burst) + screamer. One pass: sim -> audio -> frames -> final TikTok-quality mp4.
# Usage: python3 render_escape.py SEED GAP_DEG OUT.mp4
import cfg, cr, face, math, ctypes, subprocess, sys, json, wave, numpy as np, cv2
SEED = int(sys.argv[1]); GAPD = float(sys.argv[2]); OUT = sys.argv[3]
E = cfg.setup(GAPD, 8.0)
if len(sys.argv) > 4: E.GROWF = float(sys.argv[4])
TITLE = b"EACH BOUNCE MAKES IT BIGGER"
ZOOM = 1.04
W, H, CX, CY, RO, RI, BR, FPS = E.W, E.H, E.CX, E.CY, E.RO, E.RI, E.BR, E.FPS
# ring colours of the night (gap edge -> gap edge)
C1 = np.array([1.00, 0.86, 0.12]); CM = np.array([1.00, 0.45, 0.10]); C2 = np.array([0.95, 0.12, 0.42])
SCR_DUR = 0.6

res = E.run(SEED, record=True)
assert res['ok'], res
frames = res['frames']; events = res['events']; DUR = len(frames) / FPS
spawns = [e[0] for e in events if e[1] == 'spawn']; esc_t = res['escaped_t']

# ---------- screamer moment: 45-70 % of the video, >10 s, not in the last 8 s, ball in calm mid-flight
lo, hi = max(0.45 * DUR, 10.0), min(0.70 * DUR, DUR - 8 - SCR_DUR, esc_t - 2.0)
coll = [e[0] for e in events if e[1] in ('wall', 'tok', 'cap', 'die', 'spawn', 'burst', 'grow')]
best = None
for k in range(int(lo * FPS), int(hi * FPS)):
    t = k / FPS
    gap_ok = all(abs(c - t) > 0.45 and not (t <= c <= t + SCR_DUR + 0.25) for c in coll)
    if not gap_ok: continue
    sc = abs(t - 0.6 * DUR)
    if best is None or sc < best[0]: best = (sc, t)
assert best, 'no calm moment for the screamer'
T_SCR = best[1]
print('duration', round(DUR, 2), 'tries', res['tries'], 'screamer at', round(T_SCR, 3), f'({T_SCR / DUR:.0%})', flush=True)

# ---------- logs
log = dict(seed=SEED, gap_deg=GAPD, duration=DUR, tries=res['tries'], escaped_t=esc_t, screamer_t=T_SCR,
           launches=res['launches'], deaths=[(round(e[0], 3), round(e[2], 4)) for e in events if e[1] == 'die'],
           dead=[(round(d[0], 1), round(d[1], 1), round(d[4], 1)) for d in res['dead']],
           bursts=[(round(d[3], 3), round(d[0], 1), round(d[1], 1), round(d[4], 1)) for d in res['bursts']], growf=E.GROWF, burst_r=E.rburst())
json.dump(log, open('run_log.json', 'w'), indent=1)

# ---------- audio
SR = 48000; N = int(DUR * SR); L = np.zeros(N); R = np.zeros(N); rng = np.random.default_rng(5)
def add(sig, t, g, pan=0.5):
    i = int(t * SR)
    if i >= N: return
    j = min(N, i + len(sig)); s = sig[:j - i] * g
    L[i:j] += s * np.sqrt(1 - pan); R[i:j] += s * np.sqrt(pan)
def env(n, tau, att=0.0006):
    t = np.arange(n) / SR; return np.exp(-t / tau) * (1 - np.exp(-t / att)), t
def tok(f, tau=0.045):   # wood / marimba knock
    e, t = env(int(0.16 * SR), tau)
    return (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * 3.93 * f * t) * np.exp(-t / 0.008)) * e \
        + 0.10 * rng.standard_normal(len(t)) * np.exp(-t / 0.0015)
def die():
    n = int(0.3 * SR); t = np.arange(n) / SR
    fr = 120 + 700 * np.exp(-t / 0.02)
    s = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t / 0.07)
    nz = np.convolve(rng.standard_normal(n), np.ones(5) / 5, 'same') * np.exp(-t / 0.012)
    return 0.8 * s + 0.6 * nz
def pop():
    e, t = env(int(0.10 * SR), 0.03)
    return np.sin(2 * np.pi * np.cumsum(500 + 600 * (1 - np.exp(-t / 0.03))) / SR) * e
def escape():
    n = int(1.6 * SR); t = np.arange(n) / SR
    out = 0.35 * np.convolve(rng.standard_normal(n) * np.exp(-((t - 0.25) / 0.18) ** 2), np.ones(8) / 8, 'same')
    for k, f in enumerate([523.25, 659.25, 783.99, 1046.5]):
        i = int((0.05 + 0.07 * k) * SR); tt = np.arange(n - i) / SR
        out[i:] += (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt / 0.45) * (1 - np.exp(-tt / 0.003)) * 0.5
    return out
def grow(r):   # tiny rising 'bloop' (pitch drops as the ball gets bigger)
    n = int(0.09 * SR); t = np.arange(n) / SR; f0 = 900 * 26 / r
    return np.sin(2 * np.pi * np.cumsum(f0 * (1 + 0.6 * t / 0.09)) / SR) * np.exp(-t / 0.03) * (1 - np.exp(-t / 0.002))
def burst():  # balloon pop: sharp noise crack + low thump
    n = int(0.35 * SR); t = np.arange(n) / SR
    nz = rng.standard_normal(n) * np.exp(-t / 0.018)
    return 0.9 * nz + 0.7 * np.sin(2 * np.pi * np.cumsum(160 * np.exp(-t / 0.05) + 60) / SR) * np.exp(-t / 0.09)
penta = [261.63, 293.66, 329.63, 392.0, 440.0, 523.25, 587.33]
caps = {round(e[0], 4) for e in events if e[1] == 'cap'}
for t, k, x in events:
    if k == 'tok': add(tok(penta[rng.integers(len(penta))]), t, 0.15 + 0.45 * x, rng.uniform(0.3, 0.7))
    elif k == 'cap': add(tok(penta[rng.integers(4, 7)] * 2, 0.035), t, 0.35, 0.5)
    elif k == 'wall' and round(t, 4) not in caps: add(tok(penta[rng.integers(len(penta))] * 2), t, 0.12 + 0.3 * x)
    elif k == 'die': add(die(), t, 0.6)
    elif k == 'spawn': add(pop(), t, 0.12)
    elif k == 'escape': add(escape(), t, 0.55)
    elif k == 'grow': add(grow(x), t, 0.07)
    elif k == 'burst': add(burst(), t, 0.7)
mix = np.stack([L, R], 1)
mix = np.tanh(mix * 1.3) / np.tanh(1.3)
mix = mix / np.abs(mix).max() * 10 ** (-8 / 20)          # game: peak -8 dBFS
# scream: 4 detuned saws rising +35 %, 38 Hz vibrato, noise, 55 Hz hit, tanh distortion, 4 ms attack, -1 dBFS
m = int(SCR_DUR * SR); t = np.arange(m) / SR
rise = 1 + 0.35 * (t / SCR_DUR); vib = 1 + 0.025 * np.sin(2 * np.pi * 38 * t)
scr = np.zeros(m)
for f in (620, 655, 940, 1310):
    ph = np.cumsum(f * rise * vib) / SR + rng.random()
    scr += 2 * (ph % 1.0) - 1
scr += 1.2 * np.convolve(rng.standard_normal(m), [0.5, 0.5], 'same')
scr += 3.0 * np.sin(2 * np.pi * 55 * t) * np.exp(-t / 0.15)
scr = np.tanh(1.8 * scr)
scr *= np.minimum(1, t / 0.004) * np.minimum(1, (SCR_DUR - t) / 0.008)
scr = scr / np.abs(scr).max() * 10 ** (-1 / 20)
i0 = int(round(T_SCR * SR)); duck = np.ones(N); duck[i0:i0 + m] = 0.05
mix = mix * duck[:, None]; mix[i0:i0 + m] += np.stack([scr, scr * 0.97], 1)[:N - i0]
mix *= np.minimum(1, (N - np.arange(N)) / (0.3 * SR))[:, None]
w = wave.open('escape_audio.wav', 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()

# ---------- screamer base image (variant of the night)
FACE = face.make(seed=SEED + 17, tilt=6.0, smile=1.5, gaze=(0.12, -0.05))
FH, FW = FACE.shape[:2]; VIEW_W = 1040.0          # base view: 1040 px of the face image across the 1080 screen
srng = np.random.default_rng(SEED + 99)
def scream_frame(tau):
    z = 1.55 - 0.45 * min(1, tau / 0.05) if tau < 0.05 else 1.10 + 0.07 * (tau - 0.05) / (SCR_DUR - 0.05)
    s = W / VIEW_W * z
    dx, dy = np.clip(srng.normal(0, 9, 2), -18, 18); rot = float(np.clip(srng.normal(0, 1), -2, 2))
    M = cv2.getRotationMatrix2D((FW / 2, FH / 2), rot, s)
    M[0, 2] += W / 2 - FW / 2 + dx; M[1, 2] += H / 2 - FH / 2 + dy
    img = cv2.warpAffine(FACE, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    sh = int(srng.integers(4, 15))
    img[..., 2] = np.roll(img[..., 2], sh, axis=1)   # red channel offset
    out = np.empty((H, W, 4), np.uint8); out[..., :3] = img; out[..., 3] = 255
    return out.tobytes()

# ---------- game renderer (validated spike_escape look)
surf = cr.surface_create(0, W, H); c = cr.create(surf); stride = cr.get_stride(surf)
cr.set_line_join(c, 1); cr.set_line_cap(c, 1)
def ringcol(u):
    return tuple(C1 * (1 - 2 * u) + CM * 2 * u) if u < 0.5 else tuple(CM * (2 - 2 * u) + C2 * (2 * u - 1))
prng = np.random.default_rng(11); parts = []
for (dx, dy, col, td, dr) in res['dead']:
    for _ in range(22):
        a = prng.uniform(0, 2 * math.pi); s = prng.uniform(80, 380)
        parts.append((td, dx, dy, s * math.cos(a), s * math.sin(a), prng.uniform(2.5, 5), col, 0.55))
for (dx, dy, col, td, dr) in res['bursts']:      # burst: big ring of fragments, nothing left behind
    for _ in range(60):
        a = prng.uniform(0, 2 * math.pi); s = prng.uniform(200, 700); r0 = dr * prng.uniform(0.85, 1.0)
        parts.append((td, dx + r0 * math.cos(a), dy + r0 * math.sin(a), s * math.cos(a), s * math.sin(a), prng.uniform(3, 7), col, 0.7))
rdisp = []; prev = None                                  # smooth growth on screen (~0.08 s)
for fr in frames:
    rr = fr['ball'][3]
    prev = rr if (prev is None or rr < prev - 1e-6) else prev + (rr - prev) * 0.35
    rdisp.append(prev)
fe = min(range(len(frames)), key=lambda i: abs(frames[i]['t'] - esc_t))
ep, ecol, _, _ = frames[fe]['ball']
for _ in range(70):
    a = prng.uniform(0, 2 * math.pi); s = prng.uniform(150, 650)
    parts.append((esc_t, ep[0], ep[1], s * math.cos(a), s * math.sin(a), prng.uniform(3, 6.5), ecol, 1.0))
cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
te = cr.TE(); cr.text_extents(c, TITLE, ctypes.byref(te))
TX = (W - te.w) / 2 - te.xb; TY = 440
print('title width', te.w, flush=True)

ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}', '-r', str(FPS),
    '-i', '-', '-i', 'escape_audio.wav', '-map', '0:v', '-map', '1:a',
    '-c:v', 'libx264', '-profile:v', 'high', '-level', '4.2', '-pix_fmt', 'yuv420p', '-preset', 'slow', '-crf', '14',
    '-maxrate', '25M', '-bufsize', '50M', '-g', '120', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
    '-c:a', 'aac', '-b:a', '320k', '-ar', '48000', '-movflags', '+faststart', '-shortest', OUT], stdin=subprocess.PIPE)
NSEG = 200; f0 = int(round(T_SCR * FPS)); f1 = f0 + int(round(SCR_DUR * FPS))
for fi, fr in enumerate(frames):
    if f0 <= fi < f1:                       # dry cut to the face, simulation keeps running underneath
        ff.stdin.write(scream_frame((fi - f0) / FPS)); continue
    t = fr['t']; phi = fr['phi']
    cr.identity_matrix(c); cr.set_rgb(c, 0, 0, 0); cr.paint(c)
    cr.translate(c, CX, CY); cr.scale(c, ZOOM, ZOOM); cr.translate(c, -CX, -CY)
    a0 = phi + E.GAP / 2; span = 2 * math.pi - E.GAP
    for k in range(NSEG):
        u0, u1 = k / NSEG, (k + 1) / NSEG
        b0, b1 = a0 + span * u0, a0 + span * u1 + (0.002 if k < NSEG - 1 else 0)
        cr.new_path(c); cr.arc(c, CX, CY, RI + 6, b0, b1)
        cr.line_to(c, CX + RI * math.cos(b1), CY + RI * math.sin(b1))
        cr.arc_negative(c, CX, CY, RI, b1, b0); cr.close_path(c)
        cr.set_rgb(c, *ringcol((u0 + u1) / 2)); cr.fill(c)
    for a, tri in zip(E.SPIKES, E.spike_tris(phi)):
        u = ((a - E.GAP / 2) % (2 * math.pi)) / span
        col = ringcol(min(1, max(0, u)))
        cr.new_path(c); cr.move_to(c, *tri[0]); cr.line_to(c, *tri[1]); cr.line_to(c, *tri[2]); cr.close_path(c)
        cr.set_rgb(c, col[0] * 0.10, col[1] * 0.10, col[2] * 0.10); cr.fill_preserve(c)
        cr.set_line_width(c, 2.7); cr.set_rgb(c, *col); cr.stroke(c)
    for (dx, dy, col, td, dr) in fr['dead']:
        s = min(1, (t - td) / 0.15); g = 0x3A / 255
        cr.new_path(c); cr.arc(c, dx, dy, dr, 0, 2 * math.pi)
        cr.set_rgb(c, *[col[i] * (1 - s) + g * s for i in range(3)]); cr.fill(c)
    p, col, st, _ = fr['ball']; BRd = rdisp[fi]
    if st != 'dead':
        last_sp = max([s for s in spawns if s <= t], default=0)
        sc = min(1, (t - last_sp) / 0.12) if st == 'alive' else 1
        if -100 < p[1] < H + 100:
            cr.new_path(c); cr.arc(c, p[0], p[1], BRd * (0.4 + 0.6 * sc), 0, 2 * math.pi); cr.set_rgb(c, *col); cr.fill(c)
    for (t0, x0, y0, vx, vy, r0, pcol, life) in parts:
        dt = t - t0
        if dt < 0 or dt > life: continue
        k = (1 - math.exp(-3 * dt)) / 3
        cr.new_path(c); cr.arc(c, x0 + vx * k, y0 + vy * k + 150 * dt * dt, r0 * (1 - dt / life), 0, 2 * math.pi)
        cr.set_rgba(c, *pcol, 1 - dt / life); cr.fill(c)
    cr.identity_matrix(c)
    cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
    cr.move_to(c, TX, TY); cr.set_rgb(c, 1, 1, 1); cr.show_text(c, TITLE)
    cr.flush(surf)
    ff.stdin.write(ctypes.string_at(cr.get_data(surf), stride * H))
    if fi % 600 == 0: print('frame', fi, flush=True)
ff.stdin.close(); ff.wait(); print('done', OUT)
