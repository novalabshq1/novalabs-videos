# ESCAPE — CLONES : chaque balle morte fait apparaître 2 nouvelles balles au point de départ ; il faut qu'UNE seule sorte.
# Géométrie, lancer et physique identiques au moteur spike_escape (anneau fixe, ouverture PILE EN BAS).
import numpy as np, math, colorsys
import cfg
E = cfg.apply(20.0)
SPAWN_GAP = 0.30      # délai minimal entre deux apparitions au point de départ (s)
MAX_T = 60.0

def setup(gap_deg):
    global E
    E = cfg.apply(gap_deg)

def run(seed, record=False):
    rng = np.random.default_rng(seed)
    CX, CY, RI, RO, BR, DT = E.CX, E.CY, E.RI, E.RO, E.BR, E.DT
    tris = E.spike_tris(E.ring_angle(0))
    sang = np.array([(a + E.GAP_AT) for a in E.SPIKES])
    # spike edges as arrays for vectorised distance
    A = np.array([[t[i] for i in range(3)] for t in tris])          # (S,3,2)
    P0 = A; P1 = np.roll(A, -1, axis=1)
    phi = E.ring_angle(0)
    caps = []
    for side in (-1, 1):
        ea = phi + side * E.GAP / 2
        caps.append(((CX + RI * math.cos(ea), CY + RI * math.sin(ea)), (CX + (RO + 2) * math.cos(ea), CY + (RO + 2) * math.sin(ea))))
    tips = [(CX + (RI - E.SPK_H * 0.5) * math.cos(phi + s * E.GAP / 2), CY + (RI - E.SPK_H * 0.5) * math.sin(phi + s * E.GAP / 2)) for s in (-1, 1)]
    live = []; dead = []; events = []; frames = []; launches = []; lives = []
    queue = 1; next_ok = 0.0; nball = 0
    t = 0.0; step = 0; escaped = None; end_t = None
    def spawn():
        nonlocal nball
        nball += 1
        a = math.radians(E.LAUNCH_DEG + rng.uniform(-E.LAUNCH_JIT, E.LAUNCH_JIT))
        h = (E.HUE0 + 0.381966 * (nball - 1)) % 1.0
        col = tuple(float(x) for x in colorsys.hsv_to_rgb(h, 0.85, 1.0))
        launches.append((t, CX, CY - 60.0, math.degrees(a), E.V0))
        events.append((t, 'spawn', 0.0))
        live.append(dict(p=np.array([CX, CY - 60.0]), v=E.V0 * np.array([math.cos(a), math.sin(a)]), col=col, t0=t, id=nball, near=1e9, st='alive'))
    while True:
        # spawner (stops after the escape)
        if escaped is None and queue > 0 and t >= next_ok:
            free = all(math.hypot(b['p'][0] - CX, b['p'][1] - (CY - 60)) > 2 * BR + 2 for b in live)
            if free:
                spawn(); queue -= 1; next_ok = t + SPAWN_GAP
        for b in live:
            if b['st'] == 'escaped':
                b['v'][1] += E.G * DT; b['p'] = b['p'] + b['v'] * DT; continue
            b['v'][1] += E.G * DT; b['p'] = b['p'] + b['v'] * DT
        # live-live collisions (equal masses, elastic)
        al = [b for b in live if b['st'] == 'alive']
        n = len(al)
        if n > 1:
            P = np.array([b['p'] for b in al]); D = P[:, None, :] - P[None, :, :]
            dist = np.hypot(D[..., 0], D[..., 1]); iu = np.triu_indices(n, 1)
            close = np.nonzero(dist[iu] < 2 * BR)[0]
            for k in close:
                i, j = iu[0][k], iu[1][k]; bi, bj = al[i], al[j]
                d = bi['p'] - bj['p']; dd = math.hypot(*d) + 1e-9; nn = d / dd
                rv = (bi['v'] - bj['v']) @ nn
                if rv < 0:
                    bi['v'] = bi['v'] - rv * nn; bj['v'] = bj['v'] + rv * nn
                    events.append((t, 'tok', min(1.0, -rv / 900)))
                ov = 2 * BR - dd
                bi['p'] = bi['p'] + nn * ov / 2; bj['p'] = bj['p'] - nn * ov / 2
        newly_dead = []
        for b in al:
            rel = b['p'] - (CX, CY); r = math.hypot(*rel); ang = math.atan2(rel[1], rel[0])
            gap = abs((ang - phi + math.pi) % (2 * math.pi) - math.pi) < E.GAP / 2
            if r > RI - BR and not gap and r < RO:
                nv = rel / r; vn = b['v'] @ nv
                if vn > 0:
                    b['v'] = b['v'] - 2 * vn * nv; events.append((t, 'wall', min(1.0, vn / 900)))
                b['p'] = np.array([CX, CY]) + nv * (RI - BR)
            for tp in tips:
                b['near'] = min(b['near'], math.hypot(b['p'][0] - tp[0], b['p'][1] - tp[1]))
            for a0, a1 in caps:
                d, q = E.seg_dist(b['p'], a0, a1)
                if d < BR:
                    nv = (b['p'] - q) / (d + 1e-9); vn = b['v'] @ nv
                    if vn < 0:
                        b['v'] = b['v'] - 2 * vn * nv; events.append((t, 'wall', min(1.0, -vn / 900))); events.append((t, 'cap', 0.0))
                    b['p'] = np.array(q) + nv * BR
            if dead:
                Dp = np.array([(x, y) for x, y, _, _ in dead]); d = b['p'][None, :] - Dp; dist = np.hypot(d[:, 0], d[:, 1])
                for k in np.nonzero(dist < 2 * BR)[0]:
                    nv = d[k] / dist[k]; vn = b['v'] @ nv
                    if vn < 0:
                        b['v'] = b['v'] - 2 * vn * nv; events.append((t, 'tok', min(1.0, -vn / 900)))
                    b['p'] = Dp[k] + nv * 2 * BR
            if r > RI - E.SPK_H - BR - 2:
                ab = P1 - P0; ap = b['p'][None, None, :] - P0
                tt = np.clip((ap * ab).sum(-1) / (ab * ab).sum(-1), 0, 1)
                q = P0 + ab * tt[..., None]; dd = np.hypot(*(b['p'][None, None, :] - q).transpose(2, 0, 1))
                if dd.min() < BR:
                    b['st'] = 'dead'; newly_dead.append(b)
                    dg = abs((ang - phi + math.pi) % (2 * math.pi) - math.pi) - E.GAP / 2
                    events.append((t, 'die', float(dg))); events.append((t, 'trymin', b['near']))
                    lives.append((b['id'], b['t0'], t, 'dead'))
                    continue
            if r > RO + BR + 4 and escaped is None:
                b['st'] = 'escaped'; escaped = t; end_t = t + E.END_HOLD
                events.append((t, 'escape', 0.0)); lives.append((b['id'], b['t0'], t, 'escaped'))
            if b['st'] == 'alive' and t - b['t0'] > E.TRY_TIMEOUT:
                return dict(ok=False, reason='stuck')
        for b in newly_dead:
            dead.append((b['p'][0], b['p'][1], b['col'], t))
            if escaped is None: queue += 2
        live = [x for x in live if x['st'] != 'dead']
        live = [b for b in live if not (b['st'] == 'escaped' and b['p'][1] > E.H + 200)]
        t += DT; step += 1
        if record and step % E.SUB == 0:
            frames.append(dict(t=t, balls=[(b['p'].copy(), b['col'], b['st'], b['t0']) for b in live], dead=list(dead)))
        if end_t is not None and t >= end_t: break
        if t > MAX_T: return dict(ok=False, reason='too long')
    return dict(ok=True, balls=nball, escaped_t=escaped, end_t=end_t, events=events, frames=frames, dead=dead,
                launches=launches, lives=lives, nlive_max=max((len(f['balls']) for f in frames), default=0))
