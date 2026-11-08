import esc_sim as E, cr, math, ctypes, subprocess, sys, numpy as np, cv2
E.RO = 490.0; E.RING_T = 16.0; E.RI = E.RO - E.RING_T; E.BR = 26.0
E.MAX_TRIES = 45; E.ROT = 0; E.NSPK = 88; E.SPK_HALF = math.pi / 88; E.SPK_H = 62; E.LEAN = 1.0
GAPD = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
E.GAP_AT = math.radians(90); E.G = 400; E.V0 = 360; E.GAP = math.radians(GAPD); E.SPIKES = E.spike_angles()
if len(sys.argv) > 5: E.TS_H = float(sys.argv[5]); E.TS_HALF = math.radians(float(sys.argv[6]))
SEED = int(sys.argv[1]); OUT = sys.argv[2]
from scream import Screamer, NFR as SC_N, DUR as SC_DUR
TITLE = b"EVERY DEATH GROWS A SPIKE"
ZOOM = 1.04   # camera zoom validated by Yanis (physics unchanged)
W, H, CX, CY, RO, RI, BR = E.W, E.H, E.CX, E.CY, E.RO, E.RI, E.BR

res = E.run(SEED, record=True)
assert res['ok'], res
frames = res['frames']
print('tries', res['tries'], 'end', res['end_t'], 'frames', len(frames), flush=True)
KIND = {'wall': 0, 'tok': 1, 'die': 2, 'spawn': 3, 'escape': 4, 'cap': 5, 'trymin': 6, 'launch': 7, 'trapkill': 8}
np.save('esc_events.npy', np.array([(t, KIND[k], x) for t, k, x in res['events']]))
# ---- screamer moment: 45-70% of the video, ball calmly mid-flight, not in the first 10 s / last 8 s / escape
DURV = len(frames) / E.FPS
busy = [e[0] for e in res['events'] if e[1] in ('die', 'spawn', 'escape', 'tok', 'cap', 'wall')]
cands = []
for k in range(int(0.45 * DURV * 60), int(0.70 * DURV * 60)):
    T = k / 60
    if T < 10 or T + SC_DUR > DURV - 8 or T + SC_DUR > res['escaped_t'] - 0.5: continue
    if any(T - 0.35 < b < T + SC_DUR + 0.2 for b in busy): continue
    cands.append(T)
assert cands, 'no calm moment for the screamer'
SC_T = min(cands, key=lambda T: abs(T - 0.57 * DURV))
SC_F0 = int(round(SC_T * E.FPS))
print('screamer at %.2f s (%.0f%% of %.1f s)' % (SC_F0 / E.FPS, 100 * SC_F0 / len(frames), DURV), flush=True)
open('screamer_t.txt', 'w').write('%.4f' % (SC_F0 / E.FPS))
subprocess.run(['python3', 'audio_esc.py', '%.4f' % DURV, '%.4f' % (SC_F0 / E.FPS)], check=True)
screamer = Screamer()

surf = cr.surface_create(0, W, H); c = cr.create(surf); stride = cr.get_stride(surf)
cr.set_line_join(c, 1); cr.set_line_cap(c, 1)
BG = (0.0, 0.0, 0.0)
rng = np.random.default_rng(11)
stars = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.8, 1.8), rng.uniform(0.25, 0.75),
          rng.uniform(-6, 6), rng.uniform(-3, 3)) for _ in range(0)]
C1 = np.array([1.00, 0.58, 0.10]); CM = np.array([1.00, 0.20, 0.52]); C2 = np.array([0.55, 0.28, 1.00])   # orange -> hot pink -> purple

def ringcol(u):  # u in [0,1] along the ring (ring-local)
    return tuple(C1 * (1 - 2 * u) + CM * 2 * u) if u < 0.5 else tuple(CM * (2 - 2 * u) + C2 * (2 * u - 1))

events = res['events']
deaths = [(e[0]) for e in events if e[1] == 'die']
spawns = [e[0] for e in events if e[1] == 'spawn']
esc_t = res['escaped_t']
parts = []
for fr_i, (dx, dy, col, td) in enumerate(res['dead']):
    for _ in range(22):
        a = rng.uniform(0, 2 * math.pi); s = rng.uniform(80, 380)
        parts.append((td, dx, dy, s * math.cos(a), s * math.sin(a), rng.uniform(2.5, 5), col, 0.55))
# escape confetti: position from frame at esc_t
fe = min(range(len(frames)), key=lambda i: abs(frames[i]['t'] - esc_t))
ep, ecol, _ = frames[fe]['ball']
for _ in range(70):
    a = rng.uniform(0, 2 * math.pi); s = rng.uniform(150, 650)
    parts.append((esc_t, ep[0], ep[1], s * math.cos(a), s * math.sin(a), rng.uniform(3, 6.5), ecol, 1.0))

cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
te = cr.TE(); cr.text_extents(c, TITLE, ctypes.byref(te))
TX = (W - te.w) / 2 - te.xb; TY = 440

ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}',
                       '-r', str(E.FPS), '-i', '-', '-i', 'esc_audio.wav',
                       '-c:v', 'libx264', '-profile:v', 'high', '-level', '4.2', '-pix_fmt', 'yuv420p', '-preset', 'slow',
                       '-crf', '14', '-maxrate', '25M', '-bufsize', '50M', '-g', '120', '-colorspace', 'bt709',
                       '-color_primaries', 'bt709', '-color_trc', 'bt709', '-c:a', 'aac', '-b:a', '320k', '-ar', '48000',
                       '-movflags', '+faststart', '-shortest', OUT], stdin=subprocess.PIPE)
KEYS = set(int(x) for x in sys.argv[4].split(',')) if len(sys.argv) > 4 else set()
NSEG = 200
for fi, fr in enumerate(frames):
    t = fr['t']; phi = fr['phi']
    if SC_F0 <= fi < SC_F0 + SC_N:            # hard cut to the screamer, the simulation keeps running underneath
        sf = screamer.frame(fi - SC_F0)
        bgra = np.dstack([sf, np.full(sf.shape[:2], 255, np.uint8)])
        ff.stdin.write(bgra.tobytes())
        if fi in KEYS: cv2.imwrite(f'key_{fi:05d}.png', sf)
        continue
    cr.set_rgb(c, *BG); cr.paint(c)
    cr.identity_matrix(c); cr.translate(c, CX, CY); cr.scale(c, ZOOM, ZOOM); cr.translate(c, -CX, -CY)
    for (sx, sy, sr, sa, vx, vy) in stars:
        x = (sx + vx * t) % W; y = (sy + vy * t) % H
        cr.new_path(c); cr.arc(c, x, y, sr, 0, 2 * math.pi); cr.set_rgba(c, 0.75, 0.85, 1.0, sa); cr.fill(c)
    # ring: arc from gap edge to gap edge, colour along its length
    a0 = phi + E.GAP / 2; span = 2 * math.pi - E.GAP
    for k in range(NSEG):
        u0, u1 = k / NSEG, (k + 1) / NSEG
        b0, b1 = a0 + span * u0, a0 + span * u1 + 0.002
        cr.new_path(c)
        cr.arc(c, CX, CY, RI + 6, b0, b1)
        cr.line_to(c, CX + RI * math.cos(b1), CY + RI * math.sin(b1))
        cr.arc_negative(c, CX, CY, RI, b1, b0)
        cr.close_path(c)
        cr.set_rgb(c, *ringcol((u0 + u1) / 2)); cr.fill(c)
    # spikes
    for a, tri in zip(E.SPIKES, E.spike_tris(phi)):
        u = ((a - E.GAP / 2) % (2 * math.pi)) / span
        col = ringcol(min(1, max(0, u)))
        cr.new_path(c); cr.move_to(c, *tri[0]); cr.line_to(c, *tri[1]); cr.line_to(c, *tri[2]); cr.close_path(c)
        cr.set_rgb(c, col[0] * 0.10, col[1] * 0.10, col[2] * 0.10); cr.fill_preserve(c)
        cr.set_line_width(c, 2.6); cr.set_rgb(c, *col); cr.stroke(c)
    # dead balls (grey obstacles)
    for (dx, dy, col, td) in fr['dead']:
        # SPIKE TRAP: the new spike grows out of the dead ball (0.05 -> 0.25 s), same style as the ring spikes
        g_ = min(1, max(0, (t - td - 0.05) / 0.20)); g_ = 1 - (1 - g_) ** 3
        if g_ > 0:
            b1, tp, b2 = E.trap_tri(dx, dy)
            mx, my = (b1[0] + b2[0]) / 2, (b1[1] + b2[1]) / 2
            tp = (mx + (tp[0] - mx) * g_, my + (tp[1] - my) * g_)
            ua = math.atan2(dy - CY, dx - CX)
            uu = (((ua - (math.pi / 2 + E.GAP / 2)) % (2 * math.pi)) / span)
            scol = ringcol(min(1, max(0, uu)))
            cr.new_path(c); cr.move_to(c, *b1); cr.line_to(c, *tp); cr.line_to(c, *b2); cr.close_path(c)
            cr.set_rgb(c, scol[0] * 0.10, scol[1] * 0.10, scol[2] * 0.10); cr.fill_preserve(c)
            cr.set_line_width(c, 2.6); cr.set_rgb(c, *scol); cr.stroke(c)
        s = min(1, (t - td) / 0.15)
        g = 58 / 255   # #3A3A3A
        rgb = tuple(col[i] * (1 - s) + g * s for i in range(3))
        cr.new_path(c); cr.arc(c, dx, dy, BR, 0, 2 * math.pi); cr.set_rgb(c, *rgb); cr.fill(c)
    # live / escaping ball
    p, col, st = fr['ball']
    if st != 'dead':
        last_sp = max([s for s in spawns if s <= t], default=0)
        sc = min(1, (t - last_sp) / 0.12) if st == 'alive' else 1
        rr = BR * (0.4 + 0.6 * sc)
        if -100 < p[1] < H + 100:
            cr.new_path(c); cr.arc(c, p[0], p[1], rr, 0, 2 * math.pi); cr.set_rgb(c, *col); cr.fill(c)
    # particles
    for (t0, x0, y0, vx, vy, r0, pcol, life) in parts:
        dt = t - t0
        if dt < 0 or dt > life: continue
        k = (1 - math.exp(-3 * dt)) / 3
        x, y = x0 + vx * k, y0 + vy * k + 150 * dt * dt
        cr.new_path(c); cr.arc(c, x, y, r0 * (1 - dt / life), 0, 2 * math.pi)
        cr.set_rgba(c, *pcol, 1 - dt / life); cr.fill(c)
    cr.identity_matrix(c)
    cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
    cr.move_to(c, TX, TY); cr.set_rgb(c, 1, 1, 1); cr.show_text(c, TITLE)
    cr.flush(surf)
    buf = ctypes.string_at(cr.get_data(surf), stride * H)
    ff.stdin.write(buf)
    if fi in KEYS: cv2.imwrite(f'key_{fi:05d}.png', np.frombuffer(buf, np.uint8).reshape(H, stride // 4, 4)[:, :W, :3])
    if fi % 600 == 0: print('frame', fi, flush=True)
ff.stdin.close(); ff.wait(); print('done')
