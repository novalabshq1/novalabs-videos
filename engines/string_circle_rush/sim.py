import numpy as np, math

W, H = 1080, 1920
CX, CY, R = 540.0, 1075.0, 450.0
BR = 32.0            # ball radius
FPS, SUB = 60, 4
DT = 1.0 / (FPS * SUB)
END_HOLD = 1.5
MAX_T = 70.0
POSF = 0.7
SPREAD = 32
JIT = 0.9
PLOW_K = 10**9

class Country:
    def __init__(s, name, color, ang, n0, rng, speed):
        s.name, s.color = name, color
        a = math.radians(ang)
        s.p = np.array([CX + POSF * R * math.cos(a), CY + POSF * R * math.sin(a)])
        spread = math.radians(SPREAD)
        angs = np.linspace(a - spread, a + spread, n0)
        s.anchors = np.stack([CX + R * np.cos(angs), CY + R * np.sin(angs)], 1)
        d = a + math.pi + rng.uniform(-JIT, JIT)   # head inward
        s.v = speed * np.array([math.cos(d), math.sin(d)])
        s.alive = True

def seg_cut_mask(ball_p, owner_p, anchors):
    """strings owner_p->anchor whose (trimmed) segment is within BR of ball_p"""
    if len(anchors) == 0:
        return np.zeros(0, bool)
    d = anchors - owner_p
    L = np.linalg.norm(d, axis=1) + 1e-9
    u = d / L[:, None]
    start = 2 * BR + 2.0           # ignore the part hugging the owner ball
    t = np.clip(((ball_p - owner_p) * u).sum(1), start, None)
    t = np.minimum(t, L)
    q = owner_p + u * t[:, None]
    dist = np.linalg.norm(q - ball_p, axis=1)
    return (dist < BR) & (L > start)

def smooth(x):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    return 3 * x * x - 2 * x ** 3

def rate(t, t2):
    # RUSH: continuous growth rate (1/s); t2 = moment only 2 balls remain
    return 0.008 + (0.25 * smooth((t - t2) / 6.0) if t2 is not None else 0.0)

WALL_N = 10          # RUSH: +10 strings per wall contact
WALL_STEP = 1.0      # degrees between them

def run(spec, seed, speed, n0, record=False):
    rng = np.random.default_rng(seed)
    cs = [Country(n, c, a, n0, rng, speed) for (n, c, a) in spec]
    v0 = float(speed)
    lnv = 0.0            # RUSH: ln(v / v0), integrated growth rate
    events = []          # (t, kind, extra)
    frames = []
    trails = []          # RUSH: per frame, per ball list of sub-step positions
    speeds = []          # RUSH: speed at each frame
    walls = []           # RUSH: (t, ball index, strings before, strings after)
    counts_log = []
    t = 0.0; end_t = None; t2 = None
    snaps = []           # (t0, from_xy, anchor_xy, color)
    deaths = []          # (t0, xy, color, strings_left)
    fidx = 1
    max_step_px = 0.0
    cur_tr = [[c.p.copy()] for c in cs]
    while True:
        speed = v0 * math.exp(lnv)
        t_next = fidx / FPS
        DT = min(1.0 / 120, 3.0 / speed, t_next - t)
        if DT <= 1e-12: DT = 1e-12
        # --- physics substep
        for ci, c in enumerate(cs):
            if not c.alive: continue
            c.p = c.p + c.v * DT
            max_step_px = max(max_step_px, float(np.linalg.norm(c.v)) * DT)
            rel = c.p - (CX, CY); dist = math.hypot(*rel)
            if dist > R - BR:
                n = rel / dist
                vn = c.v @ n
                if vn > 0:
                    v = c.v - 2 * vn * n
                    th = rng.uniform(-math.radians(5), math.radians(5))
                    cs_, sn = math.cos(th), math.sin(th)
                    v = np.array([v[0] * cs_ - v[1] * sn, v[0] * sn + v[1] * cs_])
                    if v @ n > -0.15 * speed:   # keep clearly inward
                        v = v - (v @ n + 0.15 * speed) * n
                    c.v = v / np.linalg.norm(v) * speed
                    c.plow = 0
                    ca = math.atan2(n[1], n[0])
                    offs = np.radians((np.arange(WALL_N) - (WALL_N - 1) / 2) * WALL_STEP)
                    new = np.stack([CX + R * np.cos(ca + offs), CY + R * np.sin(ca + offs)], 1)
                    before = len(c.anchors)
                    c.anchors = np.vstack([c.anchors, new])
                    walls.append((t, ci, before, len(c.anchors)))
                    events.append((t, 'pluck', len(c.anchors)))
                c.p = np.array([CX, CY]) + n * (R - BR)
        alive = [c for c in cs if c.alive]
        for i in range(len(alive)):
            for j in range(i + 1, len(alive)):
                a, b = alive[i], alive[j]
                d = b.p - a.p; dist = math.hypot(*d)
                if dist < 2 * BR and dist > 1e-6:
                    n = d / dist
                    rv = (a.v - b.v) @ n
                    if rv > 0:
                        a.v = a.v - rv * n; b.v = b.v + rv * n
                        a.v = a.v / np.linalg.norm(a.v) * speed
                        b.v = b.v / np.linalg.norm(b.v) * speed
                        events.append((t, 'tok', 0))
                    ov = 2 * BR - dist
                    a.p -= n * ov / 2; b.p += n * ov / 2
        for a in alive:
            for b in alive:
                if a is b or not b.alive: continue
                m = seg_cut_mask(a.p, b.p, b.anchors)
                if m.any():
                    for an in b.anchors[m]:
                        snaps.append((t, b.p.copy(), an.copy(), b.color))
                    k = int(m.sum())
                    for j in range(k):
                        events.append((t, 'snap', j))
                    a.plow = getattr(a, 'plow', 0) + k
                    b.anchors = b.anchors[~m]
                    if len(b.anchors) == 0:
                        b.alive = False
                        deaths.append((t, b.p.copy(), b.color, len(b.anchors)))
                        events.append((t, 'pop', 0))
        t += DT
        nalive = sum(c.alive for c in cs)
        if nalive == 2 and t2 is None:
            t2 = t
        # RUSH: integrate growth rate, same speed for every living ball
        lnv += rate(t, t2) * DT
        sp = v0 * math.exp(lnv)
        for c in cs:
            if c.alive:
                c.v = c.v / np.linalg.norm(c.v) * sp
            cur_tr[cs.index(c)].append(c.p.copy())
        if t >= t_next - 1e-9:
            t = t_next
            fidx += 1
            counts_log.append([len(c.anchors) if c.alive else 0 for c in cs])
            speeds.append(sp)
            if record:
                frames.append([(c.p.copy(), c.anchors.copy(), c.alive) for c in cs])
                trails.append([np.array(tr) for tr in cur_tr])
            cur_tr = [[c.p.copy()] for c in cs]
        if nalive <= 1 and end_t is None:
            end_t = t
            events.append((t, 'win', 0))
        if end_t is not None and t >= end_t + END_HOLD:
            break
        if t > MAX_T:
            break
    winner = next((c.name for c in cs if c.alive), None) if end_t else None
    return dict(end_t=end_t, events=events, frames=frames, counts=np.array(counts_log),
                snaps=snaps, deaths=deaths, winner=winner, cs=cs, t2=t2, trails=trails,
                speeds=np.array(speeds), walls=walls, max_step_px=max_step_px)

def score(res):
    if res['end_t'] is None: return None
    total = res['end_t'] + END_HOLD
    if not (40 <= total <= 60): return None
    if res['deaths'][0][0] < 15: return None
    cnt = res['counts']
    leaders = []
    for row in cnt:
        mx = row.max()
        if (row == mx).sum() == 1:
            ld = int(row.argmax())
            if not leaders or leaders[-1] != ld: leaders.append(ld)
    changes = len(leaders) - 1
    if changes < 3: return None
    # winner not obvious 10 s before the end
    f10 = int((res['end_t'] - 10) * FPS)
    row = cnt[f10]
    names = [c.name for c in res['cs']]
    w = names.index(res['winner'])
    others = [row[i] for i in range(len(row)) if i != w and row[i] > 0]
    if not others: return None
    if row[w] > 1.3 * max(others): return None
    return changes
