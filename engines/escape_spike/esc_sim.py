import numpy as np, math

W, H = 1080, 1920
CX, CY = 540.0, 1075.0
RO = 450.0             # outer radius of ring (stroke outer edge)
RING_T = 16.0          # ring thickness
RI = RO - RING_T       # inner wall radius
BR = 24.0              # ball radius
FPS, SUB = 60, 8
DT = 1.0 / (FPS * SUB)
GAP = math.radians(46)         # opening width
NSPK = 22                      # spikes on the full ring (those in the gap are removed)
SPK_H = 78.0
SPK_HALF = math.radians(5.2)   # half angular width of a spike base
ROT = math.radians(48)         # ring rotation speed (rad/s)
G = 1100.0
V0 = 650.0
MAX_TRIES = 12
TRY_TIMEOUT = 12.0
LAUNCH_DEG = -80.0
SPREAD_DEG = 8.0
END_HOLD = 1.6

def spike_angles():
    out = []
    for k in range(NSPK):
        a = (k + 0.5) * 2 * math.pi / NSPK
        # gap centred on angle 0 (ring-local); keep spikes fully outside gap
        d = (a + math.pi) % (2 * math.pi) - math.pi
        if abs(d) < GAP / 2 + SPK_HALF * 0.95:
            continue
        out.append(a)
    return out
SPIKES = spike_angles()

GAP_AT = math.radians(90)
LEAN = 0.0
def ring_angle(t):
    return ROT * t + GAP_AT

def spike_tris(phi):
    tris = []
    for a in SPIKES:
        aa = a + phi
        b1 = (CX + RI * math.cos(aa - SPK_HALF), CY + RI * math.sin(aa - SPK_HALF))
        b2 = (CX + RI * math.cos(aa + SPK_HALF), CY + RI * math.sin(aa + SPK_HALF))
        ta = aa + LEAN * SPK_HALF
        tp = (CX + (RI - SPK_H) * math.cos(ta), CY + (RI - SPK_H) * math.sin(ta))
        tris.append((b1, tp, b2))
    return tris

def seg_dist(p, a, b):
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    qx, qy = ax + dx * t, ay + dy * t
    return math.hypot(p[0] - qx, p[1] - qy), (qx, qy)

def in_gap(ang, phi):
    d = (ang - phi + math.pi) % (2 * math.pi) - math.pi
    return abs(d) < GAP / 2

def run(seed, record=False):
    rng = np.random.default_rng(seed)
    palette = [(1.0, 0.92, 0.0), (1.0, 0.25, 0.65), (1.0, 0.55, 0.0), (0.2, 0.85, 1.0),
               (0.6, 1.0, 0.2), (0.75, 0.35, 1.0), (1.0, 0.35, 0.3), (0.3, 1.0, 0.75),
               (1.0, 0.75, 0.55), (0.35, 0.5, 1.0), (1.0, 0.45, 1.0), (0.85, 1.0, 0.45),
               (1.0, 0.15, 0.25), (0.0, 0.95, 0.95), (1.0, 0.65, 0.25), (0.95, 0.95, 0.95)]
    dead = []                  # (x, y, color, t_death)
    events = []
    frames = []
    t = 0.0; step = 0
    tries = 0; escaped_t = None; end_t = None
    ball = None
    def spawn():
        nonlocal tries
        tries += 1
        a = math.radians(LAUNCH_DEG + rng.uniform(-SPREAD_DEG, SPREAD_DEG))   # fixed launch: up, slightly right
        p = np.array([CX, CY - 60.0])
        events.append((t, 'launch', math.degrees(a)))
        return dict(p=p, v=V0 * np.array([math.cos(a), math.sin(a)]), col=palette[(tries - 1) % len(palette)],
                    t0=t, state='alive')
    ball = spawn(); events.append((t, 'spawn', 0))
    while True:
        phi = ring_angle(t)
        if ball is not None and ball['state'] == 'alive':
            b = ball
            b['v'][1] += G * DT
            b['p'] = b['p'] + b['v'] * DT
            rel = b['p'] - (CX, CY); r = math.hypot(*rel); ang = math.atan2(rel[1], rel[0])
            gap = in_gap(ang, phi)
            # ring inner wall
            if r > RI - BR and not gap and r < RO:
                n = rel / r; vn = b['v'] @ n
                if vn > 0:
                    b['v'] = b['v'] - 2 * vn * n
                    events.append((t, 'wall', min(1.0, vn / 900)))
                b['p'] = np.array([CX, CY]) + n * (RI - BR)
            # closeness to the opening (for near-miss detection)
            for side in (-1, 1):
                ea_ = phi + side * GAP / 2
                tip = (CX + (RI - SPK_H * 0.5) * math.cos(ea_), CY + (RI - SPK_H * 0.5) * math.sin(ea_))
                dd_ = math.hypot(b['p'][0] - tip[0], b['p'][1] - tip[1])
                b['near'] = min(b.get('near', 1e9), dd_)
            # gap end caps
            for side in (-1, 1):
                ea = phi + side * GAP / 2
                a0 = (CX + RI * math.cos(ea), CY + RI * math.sin(ea))
                a1 = (CX + (RO + 2) * math.cos(ea), CY + (RO + 2) * math.sin(ea))
                d, q = seg_dist(b['p'], a0, a1)
                if d < BR:
                    n = (b['p'] - q) / (d + 1e-9); vn = b['v'] @ n
                    if vn < 0:
                        b['v'] = b['v'] - 2 * vn * n
                        events.append((t, 'wall', min(1.0, -vn / 900)))
                        events.append((t, 'cap', 0))
                    b['p'] = np.array(q) + n * BR
            # dead balls
            for (dx_, dy_, _, _) in dead:
                d = b['p'] - (dx_, dy_); dist = math.hypot(*d)
                if dist < 2 * BR:
                    n = d / dist; vn = b['v'] @ n
                    if vn < 0:
                        b['v'] = b['v'] - 2 * vn * n
                        events.append((t, 'tok', min(1.0, -vn / 900)))
                    b['p'] = np.array([dx_, dy_]) + n * 2 * BR
            # spikes
            if r > RI - SPK_H - BR - 2:
                for tri in spike_tris(phi):
                    hit = False
                    for i in range(3):
                        dd, _ = seg_dist(b['p'], tri[i], tri[(i + 1) % 3])
                        if dd < BR: hit = True; break
                    if hit:
                        b['state'] = 'dead'
                        dead.append((b['p'][0], b['p'][1], b['col'], t))
                        dg = abs((ang - phi + math.pi) % (2 * math.pi) - math.pi) - GAP / 2
                        events.append((t, 'die', float(dg)))
                        break
            if b['state'] == 'alive' and r > RO + BR + 4:
                b['state'] = 'escaped'; escaped_t = t
                events.append((t, 'escape', 0))
            if b['state'] == 'alive' and t - b['t0'] > TRY_TIMEOUT:
                return dict(ok=False, reason='timeout')
            if b['state'] == 'dead':
                events.append((t, 'trymin', b.get('near', 1e9)))
                if tries >= MAX_TRIES:
                    return dict(ok=False, reason='no escape')
                ball = spawn(); events.append((t + 0.0, 'spawn', 0))
        elif ball is not None and ball['state'] == 'escaped':
            ball['v'][1] += G * DT
            ball['p'] = ball['p'] + ball['v'] * DT
            if end_t is None:
                end_t = escaped_t + END_HOLD
        t += DT; step += 1
        if record and step % SUB == 0:
            frames.append(dict(t=t, phi=ring_angle(t), ball=(ball['p'].copy(), ball['col'], ball['state']),
                               dead=list(dead)))
        if end_t is not None and t >= end_t:
            break
    return dict(ok=True, tries=tries, escaped_t=escaped_t, end_t=end_t, events=events, frames=frames, dead=dead)
