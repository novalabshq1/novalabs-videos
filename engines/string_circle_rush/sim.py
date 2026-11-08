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
# --- RUSH changes (only these vs the validated engine) ---
WALL_GAIN = 10       # strings gained per wall contact, ~1 deg apart around the contact
WALL_STEP = 1.0      # degrees between those anchors
BASE_RATE, DUEL_RATE, DUEL_RAMP = 0.008, 0.25, 6.0

def smooth(x):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    return 3 * x * x - 2 * x ** 3

def rate(t, t2):
    return BASE_RATE + (DUEL_RATE * smooth((t - t2) / DUEL_RAMP) if t2 is not None else 0.0)

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

def run(spec, seed, speed, n0, record=False, check=False):
    rng = np.random.default_rng(seed)
    cs = [Country(n, c, a, n0, rng, speed) for (n, c, a) in spec]
    events = []          # (t, kind, extra)
    frames = []
    counts_log = []
    t = 0.0; step = 0; end_t = None
    snaps = []           # (t0, from_xy, anchor_xy, color)
    deaths = []          # (t0, xy, color)
    v0 = speed
    t2 = None
    speeds = []          # speed at each frame
    trails = []          # per frame: per ball list of substep positions
    stats = dict(wall=[], minclear=1e9, maxstep=0.0)
    fdt = 1.0 / FPS
    ftrail = [[] for _ in cs]
    nsub_frame = None
    sub_i = 0
    while True:
        # --- adaptive substep: dt = min(1/120, 3 px / speed), integer split of the frame
        if sub_i == 0:
            nsub_frame = max(2, math.ceil(fdt / min(1 / 120, 3.0 / (speed * 1.01))))
        DT = fdt / nsub_frame
        speed = speed * math.exp(rate(t, t2) * DT)
        for c in cs:
            if c.alive: c.v = c.v / np.linalg.norm(c.v) * speed
        # --- physics substep
        for c in cs:
            if not c.alive: continue
            c.p = c.p + c.v * DT
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
                    ca = math.atan2(n[1], n[0])
                    offs = (np.arange(WALL_GAIN) - (WALL_GAIN - 1) / 2) * math.radians(WALL_STEP)
                    new = np.stack([CX + R * np.cos(ca + offs), CY + R * np.sin(ca + offs)], 1)
                    c.plow = 0
                    before = len(c.anchors)
                    c.anchors = np.vstack([c.anchors, new])
                    stats['wall'].append((t, before, len(c.anchors)))
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
                    if a.plow >= PLOW_K:
                        a.plow = 0
                        # bounce off the (first) string like an elastic
                        an = b.anchors[m][0]
                        d = an - b.p; d = d / (np.linalg.norm(d) + 1e-9)
                        nrm = np.array([-d[1], d[0]])
                        if (a.p - b.p) @ nrm < 0: nrm = -nrm
                        vn = a.v @ nrm
                        if vn < 0:
                            a.v = a.v - 2 * vn * nrm
                            a.v = a.v / np.linalg.norm(a.v) * speed
                    b.anchors = b.anchors[~m]
                    if len(b.anchors) == 0:
                        b.alive = False
                        deaths.append((t, b.p.copy(), b.color))
                        events.append((t, 'pop', 0))
        if check:
            for a in cs:
                if not a.alive: continue
                for b in cs:
                    if a is b or not b.alive or len(b.anchors) == 0: continue
                    d = b.anchors - b.p; L = np.linalg.norm(d, axis=1) + 1e-9; u = d / L[:, None]
                    st = 2 * BR + 2.0
                    tt = np.minimum(np.clip(((a.p - b.p) * u).sum(1), st, None), L)
                    q = b.p + u * tt[:, None]
                    dd = np.linalg.norm(q - a.p, axis=1)[L > st]
                    if len(dd): stats['minclear'] = min(stats['minclear'], float(dd.min()))
            stats['maxstep'] = max(stats['maxstep'], speed * DT)
        for k_, c in enumerate(cs):
            if c.alive: ftrail[k_].append(c.p.copy())
        nalive_now = sum(c.alive for c in cs)
        if nalive_now <= 2 and t2 is None:
            t2 = t
        t += DT; step += 1
        sub_i += 1
        if sub_i == nsub_frame:
            sub_i = 0
            counts_log.append([len(c.anchors) if c.alive else 0 for c in cs])
            speeds.append(speed)
            if record:
                frames.append([(c.p.copy(), c.anchors.copy(), c.alive) for c in cs])
                trails.append([np.array(x) if len(x) else np.zeros((0, 2)) for x in ftrail])
            ftrail = [[] for _ in cs]
        nalive = sum(c.alive for c in cs)
        if nalive <= 1 and end_t is None:
            end_t = t
            events.append((t, 'win', 0))
        if end_t is not None and t >= end_t + END_HOLD - 1e-9 and sub_i == 0:
            break
        if t > MAX_T and sub_i == 0:
            break
    winner = next((c.name for c in cs if c.alive), None) if end_t else None
    return dict(end_t=end_t, events=events, frames=frames, counts=np.array(counts_log),
                snaps=snaps, deaths=deaths, winner=winner, cs=cs, speeds=np.array(speeds),
                trails=trails, t2=t2, v0=v0, stats=stats, nframes=len(counts_log))

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
