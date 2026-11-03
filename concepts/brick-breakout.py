# Every bounce breaks a brick — a ball inside a rotating ring of bricks.
# Each wall contact destroys the brick it touched. One missing brick is narrower
# than the ball, so it needs a 2-brick gap to escape.
# usage: python3 brick-breakout.py sim SEED            -> prints escape time
#        python3 brick-breakout.py search A B          -> list seeds
#        python3 brick-breakout.py render SEED out.mp4 -> video (no audio) + events.npy
import math, sys, ctypes, subprocess, os
import numpy as np
W, H, CX, CY = 1080, 1920, 540.0, 1075.0
RO = 450.0; THK = 30.0; RI = RO - THK
N = int(os.environ.get("NB", 110)); BR = float(os.environ.get("BRR", 26)); G = 1500.0
FPS = 60; SUB = 12; DT = 1.0 / (FPS * SUB)
SEP = math.radians(0.55)          # visual seam between bricks
def omega(t): return 0.35 + 0.9 * min(1.0, t / 45.0)   # ring spin speeds up

def closest_on_brick(px, py, a0, a1):
    r = math.hypot(px, py); a = math.atan2(py, px)
    d = (a - a0) % (2 * math.pi); span = (a1 - a0) % (2 * math.pi)
    if d <= span:
        rr = min(max(r, RI), RO); return rr * math.cos(a), rr * math.sin(a)
    best = None
    for e in (a0, a1):
        ux, uy = math.cos(e), math.sin(e)
        rr = min(max(px * ux + py * uy, RI), RO)
        q = (rr * ux, rr * uy); dd = (q[0] - px) ** 2 + (q[1] - py) ** 2
        if best is None or dd < best[0]: best = (dd, q)
    return best[1]

def run(seed, record=False, tmax=70.0):
    rng = np.random.default_rng(seed)
    alive = [True] * N; broke_t = [None] * N
    x, y = rng.uniform(-60, 60), rng.uniform(-120, 0)
    a = rng.uniform(0, 2 * math.pi); s = rng.uniform(650, 850)
    vx, vy = s * math.cos(a), s * math.sin(a)
    phi = rng.uniform(0, 2 * math.pi); t = 0.0
    events = []; frames = []; esc_t = None; cool = 0.0
    nf = 0
    while t < tmax:
        for _ in range(SUB):
            phi += omega(t) * DT
            vy += G * DT; x += vx * DT; y += vy * DT; t += DT; cool -= DT
            r = math.hypot(x, y)
            if esc_t is None and r > RO + BR + 2: esc_t = t; events.append((t, 'escape', 0))
            if esc_t is not None or r < RI - BR - 1: continue
            # collide with bricks near the ball angle
            ab = math.atan2(y, x); k0 = int(((ab - phi) % (2 * math.pi)) / (2 * math.pi / N))
            hit = None
            for k in (k0 - 2, k0 - 1, k0, k0 + 1, k0 + 2):
                k %= N
                if not alive[k]: continue
                b0 = phi + k * 2 * math.pi / N; b1 = b0 + 2 * math.pi / N
                qx, qy = closest_on_brick(x, y, b0, b1)
                dx, dy = x - qx, y - qy; d = math.hypot(dx, dy)
                if d < BR and (hit is None or d < hit[0]): hit = (d, k, dx, dy)
            if hit:
                d, k, dx, dy = hit
                if d < 1e-6: dx, dy, d = -x, -y, math.hypot(x, y)
                nx, ny = dx / d, dy / d
                x += nx * (BR - d); y += ny * (BR - d)
                vn = vx * nx + vy * ny
                if vn < 0:
                    vx -= 2 * vn * nx; vy -= 2 * vn * ny
                    alive[k] = False; broke_t[k] = t
                    events.append((t, 'break', k))
        nf += 1
        if record:
            frames.append((t, phi, x, y, list(alive)))
        if esc_t is not None and t > esc_t + 3.5: break
    return dict(esc_t=esc_t, end=t, events=events, frames=frames, broke_t=broke_t,
                nbroken=sum(1 for v in alive if not v))

if __name__ == '__main__' and sys.argv[1] == 'sim':
    r = run(int(sys.argv[2])); print(r['esc_t'], r['nbroken'], len(r['events']))
if __name__ == '__main__' and sys.argv[1] == 'search':
    for sd in range(int(sys.argv[2]), int(sys.argv[3])):
        r = run(sd, tmax=62)
        if r['esc_t'] and 44 < r['esc_t'] < 54: print(sd, round(r['esc_t'], 1), r['nbroken'], flush=True)

# ---------------------------------------------------------------- render
if __name__ == '__main__' and sys.argv[1] == 'render':
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'engines', 'spike_escape'))
    import cr
    SEED = int(sys.argv[2]); OUT = sys.argv[3]
    TITLE = b"EVERY BOUNCE BREAKS A BRICK"
    res = run(SEED, record=True); esc = res['esc_t']
    frames = res['frames']; print('esc', esc, 'broken', res['nbroken'], 'frames', len(frames), flush=True)
    rng = np.random.default_rng(7)
    def hue(u):  # rainbow along the ring, saturated flat colours
        h = (u % 1.0) * 6; i = int(h); f = h - i
        q, tt = 1 - f, f
        return [(1, tt, 0), (q, 1, 0), (0, 1, tt), (0, q, 1), (tt, 0, 1), (1, 0, q)][i % 6]
    COL = [hue(k / N) for k in range(N)]
    # cascade payoff: remaining bricks pop one after another after the escape
    alive_end = frames[-1][4]
    rest = [k for k in range(N) if alive_end[k]]
    pop_t = {}
    if esc is not None:
        # order around the ring starting from the escape angle
        fe = min(range(len(frames)), key=lambda i: abs(frames[i][0] - esc))
        ex, ey = frames[fe][2], frames[fe][3]; ephi = frames[fe][1]
        ka = ((math.atan2(ey, ex) - ephi) % (2 * math.pi)) / (2 * math.pi / N)
        rest.sort(key=lambda k: min((k - ka) % N, (ka - k) % N))
        for j, k in enumerate(rest): pop_t[k] = esc + 0.25 + j * 0.035
    breaks = [(e[0], e[2]) for e in res['events'] if e[1] == 'break'] + [(t, k) for k, t in pop_t.items()]
    def brick_center(k, phi):
        a = phi + (k + 0.5) * 2 * math.pi / N; r = (RI + RO) / 2
        return CX + r * math.cos(a), CY + r * math.sin(a), a
    phi_at = {round(f[0], 4): f[1] for f in frames}
    def phi_of(t):
        i = min(len(frames) - 1, max(0, int(round(t * FPS)) - 1)); return frames[i][1]
    parts = []
    for (tb, k) in breaks:
        bx, by, a = brick_center(k, phi_of(tb))
        for _ in range(7):
            aa = a + math.pi + rng.uniform(-1.3, 1.3) if rng.random() < 0.5 else a + rng.uniform(-1.0, 1.0)
            s = rng.uniform(120, 420)
            parts.append((tb, bx, by, s * math.cos(aa), s * math.sin(aa), rng.uniform(5, 9), COL[k], rng.uniform(0.45, 0.8)))
    np.save(os.path.splitext(OUT)[0] + '_events.npy',
            np.array([(t, k, 1 if k in pop_t and abs(pop_t[k] - t) < 1e-9 else 0) for t, k in breaks] + [(esc, -1, 2)]))
    surf = cr.surface_create(0, W, H); c = cr.create(surf); stride = cr.get_stride(surf)
    cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
    te = cr.TE(); cr.text_extents(c, TITLE, ctypes.byref(te))
    print('title width', te.w); TX = (W - te.w) / 2 - te.xb; TY = 440
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}',
                           '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16',
                           '-pix_fmt', 'yuv420p', OUT], stdin=subprocess.PIPE)
    step = 2 * math.pi / N; trail = []
    for fi, (t, phi, x, y, alive) in enumerate(frames):
        cr.identity_matrix(c); cr.set_rgb(c, 0, 0, 0); cr.paint(c)
        for k in range(N):
            b0 = phi + k * step + SEP / 2; b1 = phi + (k + 1) * step - SEP / 2
            on = alive[k] and not (k in pop_t and t >= pop_t[k])
            cr.new_path(c); cr.arc(c, CX, CY, RO, b0, b1); cr.arc_negative(c, CX, CY, RI, b1, b0); cr.close_path(c)
            if on:
                cr.set_rgb(c, *COL[k]); cr.fill(c)
            else:
                cr.set_line_width(c, 2.0); cr.set_rgb(c, 0x3A / 255, 0x3A / 255, 0x3A / 255); cr.stroke(c)
        if -60 < CY + y < H + 60:
            cr.new_path(c); cr.arc(c, CX + x, CY + y, BR, 0, 2 * math.pi); cr.set_rgb(c, 1, 1, 1); cr.fill(c)
        for (t0, x0, y0, vx, vy, r0, pc, life) in parts:
            dt = t - t0
            if dt < 0 or dt > life: continue
            px = x0 + vx * dt; py = y0 + vy * dt + 0.5 * G * dt * dt
            cr.new_path(c); cr.rectangle(c, px - r0 / 2, py - r0 / 2, r0 * (1 - 0.7 * dt / life), r0 * (1 - 0.7 * dt / life))
            cr.set_rgb(c, *pc); cr.fill(c)
        cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
        cr.move_to(c, TX, TY); cr.set_rgb(c, 1, 1, 1); cr.show_text(c, TITLE)
        cr.flush(surf)
        ff.stdin.write(ctypes.string_at(cr.get_data(surf), stride * H))
        if fi % 600 == 0: print('frame', fi, flush=True)
    ff.stdin.close(); ff.wait(); print('done', len(frames) / FPS)
