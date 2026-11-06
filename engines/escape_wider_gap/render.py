# ESCAPE - WIDER GAP : every dead ball widens the opening (always centred at the bottom, ring never moves).
# Usage: python3 render.py SEED OUT.mp4 [GAP0_DEG] [STEP_DEG]
# Runs the sim, writes esc_events.npy + sim_log.json, builds esc_audio.wav, then encodes the final TikTok-quality mp4.
import os, esc_sim as E, cr, math, ctypes, subprocess, sys, json, numpy as np
SEED = int(sys.argv[1]); OUT = sys.argv[2]
G0 = float(sys.argv[3]) if len(sys.argv) > 3 else 14.0
ST = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
E.setup(G0, ST)
TITLE = b"EVERY DEATH WIDENS THE GAP"
ZOOM = 1.04
W, H, CX, CY, RI, BR = E.W, E.H, E.CX, E.CY, E.RI, E.BR
GAP_AT = E.GAP_AT
C1 = np.array([0.10, 0.90, 0.95]); CM = np.array([0.30, 0.42, 1.00]); C2 = np.array([0.98, 0.30, 0.80])
GREY = (0x3A / 255,) * 3
TWEEN = 0.30

res = E.run(SEED, record=True)
assert res['ok'], res
frames = res['frames']; events = res['events']
print('tries', res['tries'], 'end', res['end_t'], 'gap_end', math.degrees(res['gaps'][-1][1]), flush=True)
KIND = {'wall': 0, 'tok': 1, 'die': 2, 'spawn': 3, 'escape': 4, 'cap': 5, 'trymin': 6, 'widen': 7}
np.save('esc_events.npy', np.array([(t, KIND[k], x) for t, k, x in events]))
json.dump(dict(seed=SEED, gap0=G0, step=ST, tries=res['tries'], end_t=res['end_t'], escaped_t=res['escaped_t'],
               gaps=[(t, math.degrees(g)) for t, g in res['gaps']],
               deaths=[(t, x, y) for t, x, y, _ in res['deaths_log']],
               removed=[(t, d[0], d[1]) for t, d in res['removed']],
               spawns=[e[0] for e in events if e[1] == 'spawn'],
               traj=[(f['t'], float(f['ball'][0][0]), float(f['ball'][0][1]), f['ball'][2], math.degrees(f['gap']),
                      [(d[0], d[1]) for d in f['dead']]) for f in frames]),
          open('sim_log.json', 'w'))
DUR = len(frames) / E.FPS
subprocess.run(['python3', 'audio_esc.py', str(DUR)], check=True)

gaps = res['gaps']
def gap_disp(t):
    g = gaps[0][1]
    for (tw, gn), (_, gp) in zip(gaps[1:], gaps[:-1]):
        if t >= tw:
            u = min(1.0, (t - tw) / TWEEN); u = 1 - (1 - u) ** 3
            g = gp + (gn - gp) * u
    return g

# every spike that exists at the start, with the time it gets swallowed by the opening
SPK0 = list(E.SPIKES)
def spike_removed_at(a):
    d = abs((a - 0 + math.pi) % (2 * math.pi) - math.pi)
    for tw, g in gaps:
        if d < g / 2 + E.SPK_HALF * 0.95:
            return tw
    return None
SPK_RT = [spike_removed_at(a) for a in SPK0]

def ringcol(u):
    return tuple(C1 * (1 - 2 * u) + CM * 2 * u) if u < 0.5 else tuple(CM * (2 - 2 * u) + C2 * (2 * u - 1))

rng = np.random.default_rng(11)
spawns = [e[0] for e in events if e[1] == 'spawn']
esc_t = res['escaped_t']
parts = []
for (td, dx, dy, col) in res['deaths_log']:
    for _ in range(22):
        a = rng.uniform(0, 2 * math.pi); s = rng.uniform(80, 380)
        parts.append((td, dx, dy, s * math.cos(a), s * math.sin(a), rng.uniform(2.5, 5), col, 0.55))
removed_balls = [(tr, d) for tr, d in res['removed']]
for tr, d in removed_balls:
    for _ in range(12):
        a = rng.uniform(0, 2 * math.pi); s = rng.uniform(60, 220)
        parts.append((tr, d[0], d[1], s * math.cos(a), s * math.sin(a), rng.uniform(2, 4), GREY, 0.4))
fe = min(range(len(frames)), key=lambda i: abs(frames[i]['t'] - esc_t))
ep, ecol, _ = frames[fe]['ball']
for _ in range(70):
    a = rng.uniform(0, 2 * math.pi); s = rng.uniform(150, 650)
    parts.append((esc_t, ep[0], ep[1], s * math.cos(a), s * math.sin(a), rng.uniform(3, 6.5), ecol, 1.0))

surf = cr.surface_create(0, W, H); c = cr.create(surf); stride = cr.get_stride(surf)
cr.set_line_join(c, 1); cr.set_line_cap(c, 1)
cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
te = cr.TE(); cr.text_extents(c, TITLE, ctypes.byref(te))
assert te.w <= 900, te.w
TX = (W - te.w) / 2 - te.xb; TY = 440
print('title width', te.w, flush=True)

ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}',
                       '-r', str(E.FPS), '-i', '-', '-i', 'esc_audio.wav',
                       '-c:v', 'libx264', '-profile:v', 'high', '-level', '4.2', '-pix_fmt', 'yuv420p', '-preset', 'slow',
                       '-crf', os.environ.get('CRF', '14'), *(['-x264-params', os.environ['X264']] if os.environ.get('X264') else []), '-maxrate', '25M', '-bufsize', '50M', '-g', '120',
                       '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
                       '-c:a', 'aac', '-b:a', '320k', '-ar', '48000', '-movflags', '+faststart', '-shortest', OUT],
                      stdin=subprocess.PIPE)
NSEG = 240
KEY = set(int(x) for x in sys.argv[5].split(',')) if len(sys.argv) > 5 else set()
for fi, fr in enumerate(frames):
    t = fr['t']
    gd = gap_disp(t)
    cr.identity_matrix(c); cr.set_rgb(c, 0, 0, 0); cr.paint(c)
    cr.translate(c, CX, CY); cr.scale(c, ZOOM, ZOOM); cr.translate(c, -CX, -CY)
    # ring: arc from one edge of the opening to the other, hue gradient along it (colours fixed to ring position)
    full = 2 * math.pi
    a_start = GAP_AT + gd / 2; span = full - gd
    for k in range(NSEG):
        u0, u1 = k / NSEG, (k + 1) / NSEG
        b0, b1 = a_start + span * u0, a_start + span * u1 + 0.002
        if k == NSEG - 1: b1 = a_start + span
        cr.new_path(c)
        cr.arc(c, CX, CY, RI + 6, b0, b1)
        cr.arc_negative(c, CX, CY, RI, b1, b0)
        cr.close_path(c)
        um = ((b0 + b1) / 2 - GAP_AT) % full / full
        cr.set_rgb(c, *ringcol(min(1, max(0, (um - 0.02) / 0.96)))); cr.fill(c)
    # spikes (saw teeth); swallowed spikes sink into the ring
    for a, rt in zip(SPK0, SPK_RT):
        sc = 1.0
        if rt is not None and t >= rt:
            sc = 1 - (t - rt) / 0.22
            if sc <= 0: continue
        aa = a + GAP_AT
        b1 = (CX + RI * math.cos(aa - E.SPK_HALF), CY + RI * math.sin(aa - E.SPK_HALF))
        b2 = (CX + RI * math.cos(aa + E.SPK_HALF), CY + RI * math.sin(aa + E.SPK_HALF))
        ta = aa + E.LEAN * E.SPK_HALF
        tp = (CX + (RI - E.SPK_H * sc) * math.cos(ta), CY + (RI - E.SPK_H * sc) * math.sin(ta))
        col = ringcol(min(1, max(0, ((aa - GAP_AT) % full / full - 0.02) / 0.96)))
        cr.new_path(c); cr.move_to(c, *b1); cr.line_to(c, *tp); cr.line_to(c, *b2); cr.close_path(c)
        cr.set_rgb(c, col[0] * 0.10, col[1] * 0.10, col[2] * 0.10); cr.fill_preserve(c)
        cr.set_line_width(c, 2.5); cr.set_rgb(c, *col); cr.stroke(c)
    # grey balls: still stuck ones + the ones popping away when the gap swallows their spike
    shown = [(d[0], d[1], d[2], d[3], None) for d in fr['dead']]
    shown += [(d[0], d[1], d[2], d[3], tr) for tr, d in removed_balls if tr <= t < tr + 0.15]
    for (dx, dy, col, td, tr) in shown:
        s = min(1, (t - td) / 0.15)
        rgb = tuple(col[i] * (1 - s) + GREY[i] * s for i in range(3))
        rr = BR if tr is None else BR * (1 - (t - tr) / 0.15)
        cr.new_path(c); cr.arc(c, dx, dy, rr, 0, 2 * math.pi); cr.set_rgb(c, *rgb); cr.fill(c)
    p, col, st = fr['ball']
    if st != 'dead':
        last_sp = max([s for s in spawns if s <= t], default=0)
        sc = min(1, (t - last_sp) / 0.12) if st == 'alive' else 1
        rr = BR * (0.4 + 0.6 * sc)
        if -100 < p[1] < H + 100:
            cr.new_path(c); cr.arc(c, p[0], p[1], rr, 0, 2 * math.pi); cr.set_rgb(c, *col); cr.fill(c)
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
    if fi in KEY:
        np.save(f'key_{fi:05d}.npy', np.frombuffer(buf, np.uint8).reshape(H, W, 4)[:, :, :3])
    ff.stdin.write(buf)
    if fi % 600 == 0: print('frame', fi, flush=True)
ff.stdin.close(); ff.wait(); print('done')
