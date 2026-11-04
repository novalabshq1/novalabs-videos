"""Shrinking Exit — one ball in a rotating ring; every bounce makes the exit smaller.
Usage:
  python3 shrinking-exit.py search A B          -> list seeds escaping in the target window
  python3 shrinking-exit.py render SEED out.mp4 -> video (no audio) + events json
  python3 shrinking-exit.py audio events.json out.wav
Background A (pure black). Sound mode: sound effects only.
"""
import math, sys, json, random, subprocess, ctypes, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'engines', 'spike_escape'))
W, H, FPS, SUB = 1080, 1920, 60, 10
CX, CY = 540.0, 1075.0
RO, RW = 450.0, 14.0             # outer radius, stroke width -> 900 px wide
RC = RO - RW / 2; RI = RO - RW   # centre line, inner face
CAP = RW / 2
BR = 24.0                        # ball radius
G = 1500.0
G0 = math.radians(50); GMIN = math.radians(9.2); SHR = 0.97
TITLE = b"Every bounce shrinks the exit"
T_MIN, T_MAX = 45.0, 51.0

def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi

def omega(t):
    return 0.9 + 0.9 * min(t / 50.0, 1.0)

def simulate(seed, tmax=60.0, record=False):
    rng = random.Random(seed)
    ang = rng.uniform(0, 2 * math.pi); sp = rng.uniform(500, 900)
    x, y = CX + rng.uniform(-60, 60), CY + rng.uniform(-150, 50)
    vx, vy = sp * math.cos(ang), sp * math.sin(ang)
    phi = rng.uniform(0, 2 * math.pi)   # gap centre angle
    gt = G0; gd = G0
    inside = True; esc_t = None; bounces = 0; last_b = -1
    dt = 1.0 / (FPS * SUB); t = 0.0
    frames = []; events = []; near = 0
    nf = int(tmax * FPS)
    for fi in range(nf):
        if record:
            frames.append((t, x, y, phi, gd, bounces))
        for s in range(SUB):
            w = omega(t)
            vy += G * dt; x += vx * dt; y += vy * dt
            phi += w * dt
            gd += (gt - gd) * min(1.0, dt / 0.12)
            dx, dy = x - CX, y - CY; d = math.hypot(dx, dy); th = math.atan2(dy, dx)
            delta = abs(wrap(th - phi))
            hit = None
            # caps at the two gap edges
            for sgn in (-1, 1):
                ea = phi + sgn * gd / 2
                ex, ey = CX + RC * math.cos(ea), CY + RC * math.sin(ea)
                cx_, cy_ = x - ex, y - ey; cd = math.hypot(cx_, cy_)
                if cd < BR + CAP and cd > 1e-6:
                    nx, ny = cx_ / cd, cy_ / cd
                    wx, wy = -w * (ey - CY), w * (ex - CX)   # cap velocity
                    rvx, rvy = vx - wx, vy - wy
                    vn = rvx * nx + rvy * ny
                    if vn < 0:
                        rvx -= 2 * vn * nx; rvy -= 2 * vn * ny
                        vx, vy = rvx + wx, rvy + wy
                        hit = ('cap', -vn)
                    x = ex + nx * (BR + CAP); y = ey + ny * (BR + CAP)
            dx, dy = x - CX, y - CY; d = math.hypot(dx, dy)
            if delta > gd / 2:
                nx, ny = dx / d, dy / d; vr = vx * nx + vy * ny
                if inside and d + BR > RI and d < RC:
                    if vr > 0:
                        vx -= 2 * vr * nx; vy -= 2 * vr * ny; hit = ('wall', vr)
                    x = CX + nx * (RI - BR); y = CY + ny * (RI - BR)
                elif not inside and d - BR < RO and d > RC:
                    if vr < 0:
                        vx -= 2 * vr * nx; vy -= 2 * vr * ny; hit = ('wall', -vr)
                    x = CX + nx * (RO + BR); y = CY + ny * (RO + BR)
            elif inside and d + BR > RI:
                # inside the gap mouth: a near miss is the ball's center within the opening
                pass
            if inside and d - BR > RO + 1:
                inside = False; esc_t = t
                events.append((t, 'escape', 1.0, x, y))
            if hit and inside and t - last_b > 0.04:
                last_b = t; bounces += 1
                gt = max(GMIN, gt * SHR)
                events.append((t, hit[0], min(1.0, hit[1] / 1400.0), x, y))
            elif hit and not inside and t - last_b > 0.04:
                last_b = t; events.append((t, hit[0], min(1.0, hit[1] / 1400.0), x, y))
            t += dt
        if esc_t is not None and not record:
            break
    return dict(esc_t=esc_t, bounces=bounces, frames=frames, events=events)

def search(a, b):
    for s in range(a, b):
        r = simulate(s, tmax=T_MAX + 0.5)
        if r['esc_t'] and T_MIN <= r['esc_t'] <= T_MAX:
            print(s, round(r['esc_t'], 2), r['bounces'], flush=True)

HUE = [(1.00, 0.18, 0.25), (0.62, 0.20, 1.00), (0.10, 0.45, 1.00)]  # red -> violet -> blue
def ringcol(u):
    u = u * 2; i = min(int(u), 1); f = u - i
    a, b = HUE[i], HUE[i + 1]
    return tuple(a[k] + (b[k] - a[k]) * f for k in range(3))

def render(seed, out):
    import cr
    END = 2.3
    pre = simulate(seed, tmax=T_MAX + 1)
    esc = pre['esc_t']; total = esc + END
    r = simulate(seed, tmax=total, record=True)
    frames, events = r['frames'], r['events']
    rng = random.Random(seed * 7 + 1)
    surf = cr.surface_create(0, W, H); c = cr.create(surf)
    stride = cr.get_stride(surf)
    cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
    te = cr.TE(); cr.text_extents(c, TITLE, ctypes.byref(te))
    assert te.w <= 900, te.w
    TX = (W - te.w) / 2 - te.xb; TY = 440
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}',
                           '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16',
                           '-pix_fmt', 'yuv420p', out], stdin=subprocess.PIPE)
    # shatter fragments, created at escape
    frags = None; sparks = []
    shatter_t = esc + 0.35
    NSEG = 240
    for fi, (t, x, y, phi, gd, nb) in enumerate(frames):
        cr.identity_matrix(c); cr.set_rgb(c, 0, 0, 0); cr.paint(c)
        cr.set_line_width(c, RW)
        if t < shatter_t:
            a0 = phi + gd / 2; span = 2 * math.pi - gd
            cr.set_line_cap(c, 0)
            for k in range(NSEG):
                u0 = k / NSEG; u1 = (k + 1) / NSEG
                cr.new_path(c)
                cr.arc(c, CX, CY, RC, a0 + span * u0, a0 + span * min(1, u1 + 0.002))
                cr.set_rgb(c, *ringcol((u0 + u1) / 2)); cr.stroke(c)
            cr.set_line_cap(c, 1)
            for (aa, uu) in ((a0, 0.0), (a0 + span, 1.0)):
                cr.new_path(c); cr.arc(c, CX + RC * math.cos(aa), CY + RC * math.sin(aa), CAP, 0, 2 * math.pi)
                cr.set_rgb(c, *ringcol(uu)); cr.fill(c)
            last = (phi, gd)
        else:
            if frags is None:
                frags = []; ph, g = last
                a0 = ph + g / 2; span = 2 * math.pi - g; n = 70
                for k in range(n):
                    u0 = k / n; u1 = (k + 1) / n
                    am = a0 + span * (u0 + u1) / 2
                    s = rng.uniform(120, 380)
                    frags.append([a0 + span * u0, a0 + span * u1, ringcol((u0 + u1) / 2),
                                  s * math.cos(am) + rng.uniform(-80, 80), s * math.sin(am) + rng.uniform(-80, 80),
                                  rng.uniform(-6, 6)])
            dtf = t - shatter_t
            cr.set_line_cap(c, 1)
            for (b0, b1, col, fvx, fvy, rot) in frags:
                ox = fvx * dtf; oy = fvy * dtf + 0.5 * 1500 * dtf * dtf
                cr.save(c); cr.translate(c, CX + ox, CY + oy)
                am = (b0 + b1) / 2; mx, my = RC * math.cos(am), RC * math.sin(am)
                cr.translate(c, mx, my); 
                import ctypes as _c
                cr.translate(c, -mx, -my)
                cr.new_path(c); cr.arc(c, 0, 0, RC, b0 + rot * dtf * 0.02, b1 + rot * dtf * 0.02)
                cr.set_rgb(c, *col); cr.stroke(c); cr.restore(c)
        # trail
        for j in range(1, 9):
            k = fi - j * 1
            if k < 0: break
            tx, ty = frames[k][1], frames[k][2]
            cr.new_path(c); cr.arc(c, tx, ty, BR * (1 - j / 10), 0, 2 * math.pi)
            cr.set_rgba(c, 1.0, 0.85, 0.1, 0.22 * (1 - j / 9)); cr.fill(c)
        if -60 < y < H + 60:
            cr.new_path(c); cr.arc(c, x, y, BR, 0, 2 * math.pi); cr.set_rgb(c, 1.0, 0.84, 0.05); cr.fill(c)
        # escape sparks
        if t >= esc and not sparks:
            ex, ey = [(e[3], e[4]) for e in events if e[1] == 'escape'][0]
            for _ in range(36):
                a = rng.uniform(0, 2 * math.pi); s = rng.uniform(150, 600)
                sparks.append((ex, ey, s * math.cos(a), s * math.sin(a), rng.uniform(2.5, 5)))
        for (sx, sy, svx, svy, sr) in sparks:
            dts = t - esc
            if dts > 1.2: break
            px = sx + svx * dts; py = sy + svy * dts + 0.5 * 900 * dts * dts
            cr.new_path(c); cr.arc(c, px, py, sr * (1 - dts / 1.2), 0, 2 * math.pi)
            cr.set_rgb(c, 1.0, 0.84, 0.05); cr.fill(c)
        cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
        cr.move_to(c, TX, TY); cr.set_rgb(c, 1, 1, 1); cr.show_text(c, TITLE)
        cr.flush(surf)
        ff.stdin.write(ctypes.string_at(cr.get_data(surf), stride * H))
    ff.stdin.close(); ff.wait()
    ev = [list(e) for e in events if e[0] <= total]
    ev.append([shatter_t, 'shatter', 1.0, CX, CY])
    json.dump(dict(events=ev, duration=len(frames) / FPS, esc=esc,
                   frames=[[f[0], f[1], f[2], f[3], f[4]] for f in frames]), open(out + '.json', 'w'))
    print('escape', esc, 'duration', len(frames) / FPS, 'bounces', r['bounces'])

def audio(evfile, out):
    import numpy as np, wave
    d = json.load(open(evfile)); SR = 48000
    N = int((d['duration'] + 0.5) * SR); buf = np.zeros(N)
    rng = np.random.default_rng(3)
    def add(t, sig):
        i = int(round(t * SR)); j = min(N, i + len(sig))
        if i < N: buf[i:j] += sig[:j - i]
    def env(n, a, dec):
        tt = np.arange(n) / SR
        return np.minimum(1, tt / a) * np.exp(-tt / dec)
    def knock(amp, body, bright):
        n = int(0.12 * SR); tt = np.arange(n) / SR
        f = body * (1 + 0.6 * np.exp(-tt / 0.006))
        tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.0005, 0.035)
        nz = rng.standard_normal(n) * env(n, 0.0002, 0.004)
        nz = np.convolve(nz, np.ones(3) / 3, 'same') * bright
        return amp * (0.8 * tone + nz)
    def tick(amp):
        n = int(0.025 * SR); nz = rng.standard_normal(n) * env(n, 0.0001, 0.0025)
        nz = nz - np.convolve(nz, np.ones(4) / 4, 'same')
        return amp * nz
    def whoosh(dur, amp):
        n = int(dur * SR); nz = rng.standard_normal(n); tt = np.arange(n) / SR
        out = np.zeros(n); a = 0.0; y = 0.0
        cut = 0.02 + 0.25 * np.sin(np.pi * tt / dur) ** 2
        for i in range(n):
            y += cut[i] * (nz[i] - y); out[i] = y
        return amp * out * np.sin(np.pi * tt / dur) ** 1.5
    def crunch(amp):
        n = int(0.9 * SR); sig = np.zeros(n)
        for _ in range(55):
            k = int(rng.uniform(0, 0.35) ** 1.6 * SR); m = int(0.03 * SR)
            g = rng.standard_normal(m) * env(m, 0.0002, rng.uniform(0.003, 0.01))
            sig[k:k + m] += g[:max(0, min(m, n - k))] * rng.uniform(0.3, 1)
        tt = np.arange(n) / SR
        thump = np.sin(2 * np.pi * (55 + 60 * np.exp(-tt / 0.05)) * tt) * env(n, 0.001, 0.25)
        return amp * (0.5 * sig + 0.9 * thump)
    nb = 0
    for (t, kind, inten, x, y) in d['events']:
        if kind in ('wall', 'cap'):
            nb += 1
            v = 0.35 + 0.65 * inten
            body = 170 + rng.uniform(-12, 12) + (60 if kind == 'cap' else 0)
            add(t, knock(0.55 * v, body, 1.2 if kind == 'cap' else 0.7))
            # ratchet click of the exit closing a notch
            add(t + 0.07, tick(0.25)); add(t + 0.10, tick(0.18))
        elif kind == 'escape':
            add(t - 0.05, whoosh(0.7, 0.5)); add(t, knock(0.8, 120, 1.5))
        elif kind == 'shatter':
            add(t, crunch(0.9))
    # soft friction hiss when the ball skims near the gap mouth: none (keep it clean)
    buf = np.tanh(buf * 1.2) / np.tanh(1.2)
    buf /= max(1e-9, np.abs(buf).max()) / 0.89
    pcm = (buf * 32767).astype(np.int16)
    st = np.stack([pcm, pcm], 1)
    wv = wave.open(out, 'wb'); wv.setnchannels(2); wv.setsampwidth(2); wv.setframerate(SR)
    wv.writeframes(st.tobytes()); wv.close()

if __name__ == '__main__':
    m = sys.argv[1]
    if m == 'search': search(int(sys.argv[2]), int(sys.argv[3]))
    elif m == 'render': render(int(sys.argv[2]), sys.argv[3])
    elif m == 'audio': audio(sys.argv[2], sys.argv[3])
