"""COLOR RUSH — simulation sans rendu (identique pour les formats COULEURS et PAYS).

Règles exactes : voir engines/README.md (section color_rush).
Coordonnées relatives au centre du cercle (le rendu ajoute (540, 1075)).

    run(seed, n, ramp, flat=10, g=0.04, record=False, qc=False) -> dict
"""
import math
import random
import numpy as np

R = 450.0          # rayon de l'arène
BR = 32.0          # rayon des balles
V0 = 150.0         # vitesse de départ (px/s)
FPS = 60
PAUSE = 1.5        # pause finale sur la gagnante
TMAX = 69.0        # au-delà : partie trop longue, on abandonne (sauf record)
START_THREADS = 25


def smooth(x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return 3 * x * x - 2 * x * x * x


class Threads:
    """Tous les fils : angle d'ancrage sur le cercle + propriétaire."""

    def __init__(self):
        self.ang = np.zeros(0)
        self.own = np.zeros(0, dtype=np.int64)
        self.ax = np.zeros(0)
        self.ay = np.zeros(0)

    def add(self, angs, owner):
        angs = np.asarray(angs, dtype=float)
        self.ang = np.concatenate([self.ang, angs])
        self.own = np.concatenate([self.own, np.full(len(angs), owner, dtype=np.int64)])
        self.ax = np.concatenate([self.ax, R * np.cos(angs)])
        self.ay = np.concatenate([self.ay, R * np.sin(angs)])

    def keep(self, mask):
        self.ang = self.ang[mask]
        self.own = self.own[mask]
        self.ax = self.ax[mask]
        self.ay = self.ay[mask]

    def count(self, n):
        return np.bincount(self.own, minlength=n)


def seg_dist2(px, py, threads, pos):
    """Distance² (nb, N) entre chaque centre de balle et chaque fil."""
    Ax = pos[threads.own, 0]
    Ay = pos[threads.own, 1]
    ABx = threads.ax - Ax
    ABy = threads.ay - Ay
    L2 = ABx * ABx + ABy * ABy + 1e-9
    APx = px[:, None] - Ax[None, :]
    APy = py[:, None] - Ay[None, :]
    t = np.clip((APx * ABx + APy * ABy) / L2, 0.0, 1.0)
    dx = APx - t * ABx
    dy = APy - t * ABy
    return dx * dx + dy * dy


def run(seed, n, ramp, flat=10.0, g=0.04, record=False, qc=False):
    rng = random.Random(seed)
    pos = np.zeros((n, 2))
    dirs = np.zeros((n, 2))
    th = Threads()
    for k in range(n):
        a = math.radians(-90 + k * 360.0 / n + rng.uniform(-6, 6))
        pos[k] = (0.8 * R * math.cos(a), 0.8 * R * math.sin(a))
        d = a + math.pi + math.radians(rng.uniform(-8, 8))
        dirs[k] = (math.cos(d), math.sin(d))
        fan = a + np.radians(np.linspace(-25, 25, START_THREADS))
        th.add(fan, k)
    alive = np.ones(n, dtype=bool)
    t = 0.0
    lnv = 0.0
    elim = []            # (temps, balle)
    t2 = None
    t_win = None
    winner = None
    events = []          # (temps, type, x, y, balle) type: wall / ball / death / win
    frames = []          # snapshots par image (record)
    breaks = []          # (temps, owner, angle, ox, oy) fils cassés (record)
    leader_samples = []  # (t, counts)
    next_frame = 0.0
    frame_idx = 0
    sub = [[] for _ in range(n)]
    qc_log = dict(min_gap=1e9, max_out=-1e9, wall_adds=[], dead_counts=[], steps=0,
                  v_frames=[], violations=0)
    next_sample = 0.0
    v_pause_start = None

    while True:
        v = V0 * math.exp(lnv)
        if t_win is not None:
            # pause finale : la gagnante ralentit en douceur puis s'arrête
            k = smooth((t - t_win) / 0.4)
            v_eff = v * (1 - k)
        else:
            v_eff = v
        # --- snapshot image
        if record and t >= next_frame - 1e-9:
            cnt = th.count(n)
            frames.append(dict(t=t, pos=pos.copy(), alive=alive.copy(), v=v_eff,
                               ang=th.ang.copy(), own=th.own.copy(), cnt=cnt,
                               sub=[np.array(s) if s else np.zeros((0, 2)) for s in sub]))
            sub = [[] for _ in range(n)]
            frame_idx += 1
            next_frame = frame_idx / FPS
        if qc and t >= len(qc_log['v_frames']) / FPS - 1e-9:
            qc_log['v_frames'].append(v_eff)
        if t_win is not None and t >= t_win + PAUSE - 1e-9:
            break
        if not record and t > TMAX:
            return None
        if record and t > 200:
            break
        if t >= next_sample:
            leader_samples.append((t, th.count(n).copy()))
            next_sample += 0.5

        dt = min(1.0 / 120, 3.0 / max(v_eff, 1e-6))
        # grille temporelle alignée sur les images (identique dans tous les modes)
        nf = (math.floor(t * FPS + 1e-7) + 1) / FPS
        dt = min(dt, nf - t)
        dt = max(dt, 1e-7)

        # --- déplacement
        idx = np.nonzero(alive)[0]
        pos[idx] += dirs[idx] * v_eff * dt
        # --- mur
        for b in idx:
            r = math.hypot(pos[b, 0], pos[b, 1])
            if r > R - BR:
                nx, ny = pos[b, 0] / r, pos[b, 1] / r
                pos[b] = (nx * (R - BR), ny * (R - BR))
                dx, dy = dirs[b]
                dn = dx * nx + dy * ny
                if dn > 0:
                    rx, ry = dx - 2 * dn * nx, dy - 2 * dn * ny
                    j = math.radians(rng.uniform(-5, 5))
                    c, s = math.cos(j), math.sin(j)
                    jx, jy = rx * c - ry * s, rx * s + ry * c
                    if jx * nx + jy * ny > -0.05:   # garde une direction vers l'intérieur
                        jx, jy = rx, ry
                    m = math.hypot(jx, jy)
                    dirs[b] = (jx / m, jy / m)
                    kk = rng.randint(10, 15)
                    ca = math.atan2(ny, nx)
                    angs = ca + np.radians((np.arange(kk) - (kk - 1) / 2.0) * 1.0)
                    before = int((th.own == b).sum())
                    th.add(angs, b)
                    if qc:
                        qc_log['wall_adds'].append(int((th.own == b).sum()) - before)
                    events.append((t + dt, 'wall', nx * R, ny * R, int(b)))
        # --- chocs entre balles (élastique, puis même vitesse pour toutes)
        for ii in range(len(idx)):
            for jj in range(ii + 1, len(idx)):
                a, b = idx[ii], idx[jj]
                dx = pos[b, 0] - pos[a, 0]
                dy = pos[b, 1] - pos[a, 1]
                d = math.hypot(dx, dy)
                if d < 2 * BR and d > 1e-9:
                    nx, ny = dx / d, dy / d
                    va = dirs[a, 0] * nx + dirs[a, 1] * ny
                    vb = dirs[b, 0] * nx + dirs[b, 1] * ny
                    over = 2 * BR - d
                    pos[a] -= (nx * over / 2, ny * over / 2)
                    pos[b] += (nx * over / 2, ny * over / 2)
                    if va - vb > 0:
                        dirs[a] += (vb - va) * np.array([nx, ny])
                        dirs[b] += (va - vb) * np.array([nx, ny])
                        for q in (a, b):
                            m = math.hypot(*dirs[q])
                            if m < 1e-6:
                                dirs[q] = (-nx, -ny) if q == a else (nx, ny)
                            else:
                                dirs[q] /= m
                        events.append((t + dt, 'ball', (pos[a, 0] + pos[b, 0]) / 2,
                                       (pos[a, 1] + pos[b, 1]) / 2, int(a)))
            # re-clamp dans le cercle après séparation
        for b in idx:
            r = math.hypot(pos[b, 0], pos[b, 1])
            if r > R - BR:
                pos[b] *= (R - BR) / r
        t += dt
        if record:
            for b in idx:
                sub[b].append(pos[b].copy())

        # --- fils adverses : casse immédiate si distance < 32 px
        if len(th.own):
            d2 = seg_dist2(pos[idx, 0], pos[idx, 1], th, pos)
            hit = (d2 < BR * BR) & (th.own[None, :] != idx[:, None])
            broken = hit.any(axis=0)
            if broken.any():
                if record:
                    for q in np.nonzero(broken)[0]:
                        o = th.own[q]
                        breaks.append((t, int(o), float(th.ang[q]), float(pos[o, 0]), float(pos[o, 1])))
                th.keep(~broken)
            if qc:
                qc_log['steps'] += 1
                if len(th.own):
                    d2b = seg_dist2(pos[idx, 0], pos[idx, 1], th, pos)
                    opp = th.own[None, :] != idx[:, None]
                    if opp.any():
                        mg = math.sqrt(d2b[opp].min())
                        qc_log['min_gap'] = min(qc_log['min_gap'], mg)
                        if mg < BR:
                            qc_log['violations'] += 1
                qc_log['max_out'] = max(qc_log['max_out'],
                                        float(np.hypot(pos[idx, 0], pos[idx, 1]).max()) + BR - R)
        # --- morts
        if t_win is None:
            cnt = th.count(n)
            for b in idx:
                if cnt[b] == 0:
                    alive[b] = False
                    elim.append((t, int(b)))
                    if qc:
                        qc_log['dead_counts'].append(int(cnt[b]))
                    events.append((t, 'death', pos[b, 0], pos[b, 1], int(b)))
            na = int(alive.sum())
            if na <= 2 and t2 is None:
                t2 = t
            if na == 1:
                t_win = t
                winner = int(np.nonzero(alive)[0][0])
                events.append((t, 'win', pos[winner, 0], pos[winner, 1], winner))
            elif na == 0:
                # double élimination simultanée : partie invalide
                return None if not record else dict(invalid=True)
        # --- vitesse (taux de croissance intégré)
        if t_win is None and t >= flat:
            rate = g + 0.012 * len(elim)
            if t2 is not None:
                rate += ramp * smooth((t - t2) / 6.0)
            lnv += rate * dt

    v_end = V0 * math.exp(lnv)
    res = dict(seed=seed, n=n, ramp=ramp, flat=flat, g=g, elim=elim, t2=t2, t_win=t_win,
               winner=winner, duration=t_win + PAUSE, v_end=v_end, mult=v_end / V0,
               leader=leader_samples, events=events)
    if record:
        res['frames'] = frames
        res['breaks'] = breaks
    if qc:
        res['qc'] = qc_log
    return res


if __name__ == '__main__':
    import sys, time
    s = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    t0 = time.time()
    r = run(s, 5, 0.45)
    print(time.time() - t0, None if r is None else {k: r[k] for k in ('elim', 't2', 't_win', 'mult', 'duration')})
