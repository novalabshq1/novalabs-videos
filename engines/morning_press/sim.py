"""morning_press simulation, NO rendering. run(seed, cfg) -> dict with events (+ frames if record=True)."""
import ctypes as C, numpy as np, math, os, subprocess
import mechanisms as M

HERE = os.path.dirname(os.path.abspath(__file__))
SO = os.path.join(HERE, 'core.so')
if not os.path.exists(SO) or os.path.getmtime(SO) < os.path.getmtime(os.path.join(HERE, 'core.c')):
    subprocess.check_call(['gcc', '-O2', '-shared', '-fPIC', os.path.join(HERE, 'core.c'), '-o', SO, '-lm'])
LIB = C.CDLL(SO)
dp = np.ctypeslib.ndpointer(np.float64, flags='C'); ip = np.ctypeslib.ndpointer(np.int32, flags='C')
LIB.step.argtypes = [C.c_int, dp, dp, dp, dp, dp, ip, C.c_double, C.c_double, C.c_double, C.c_double, C.c_double,
                     C.c_int, dp, C.c_int, dp, C.c_double, C.c_double, C.c_int, dp, ip]
LIB.step.restype = C.c_int

CX, CY, R = M.CX, M.CY, M.R
V = 320.0; DT = 1 / 240; FPS = 60; R0 = 26.0; RMIN = 15.0; SHRINK = 0.88
COLORS = ['#3DDC5A', '#FFD60A', '#FF8A00', '#FF3B30', '#FF4FA3', '#A44BFF', '#2F7BFF', '#19E3FF']
NLV = len(COLORS)
FILL = 0.50
# rhythm (s): close, hold, reopen, pause  (~0.62 s per hit)
T_CLOSE, T_HOLD, T_OPEN, T_PAUSE = 0.15, 0.05, 0.24, 0.18
END_HOLD = 2.5
CAP = 1400
ITERS = 6
ITERS_DENSE = 14
DENSE_N = 200   # more solver iterations (and slower grow-in of new balls) once the circle gets crowded
DEBUG = 0
GROW0 = 0.35; T_GROW = 0.10; T_GROW_DENSE = 0.18


def ease_close(s):  # accelerating slam
    return s * s, 2 * s


def ease_open(s):   # smooth retreat
    return 1 - (3 * s * s - 2 * s ** 3), -(6 * s - 6 * s * s)


def default_cfg():
    return dict(mech='press', mech_kw={}, slit=True, slit_w=34.0, tmax=57.5)


def run(seed, cfg=None, record=False, early=None):
    global DEBUG
    cfg = cfg or default_cfg()
    rng = np.random.default_rng(seed)
    mech = M.MECHS[cfg['mech']](**cfg.get('mech_kw', {}))
    x = np.zeros(CAP); y = np.zeros(CAP); vx = np.zeros(CAP); vy = np.zeros(CAP); r = np.zeros(CAP)
    lv = np.zeros(CAP, np.int32); flag = np.zeros(CAP, np.int32); ry = np.zeros(CAP); rt = np.zeros(CAP); tb = np.full(CAP, -9.0)
    bid = np.zeros(CAP, np.int64); born = np.zeros(CAP); next_id = 0
    n = 0
    # start: 2 green balls, one on each side of the mechanism, random direction
    for side in (-1, 1):
        a = rng.uniform(0, 2 * math.pi)
        x[n] = CX + side * rng.uniform(230, 300); y[n] = CY + rng.uniform(-120, 120)
        vx[n] = V * math.cos(a); vy[n] = V * math.sin(a); r[n] = R0; rt[n] = R0; lv[n] = 0; bid[n] = next_id; born[n] = 0.0; next_id += 1; n += 1
    slit_a = 0.0; slit_h = -1.0
    if cfg.get('slit'):
        # random spot on the left/upper-left/lower-left part (away from the blocks and from the right UI band)
        slit_a = rng.uniform(math.radians(120), math.radians(240)) if rng.random() < 0.8 else \
            rng.choice([-1, 1]) * rng.uniform(math.radians(25), math.radians(50))
        slit_h = cfg['slit_w'] / 2
    stats = np.zeros(4); whi = np.zeros(4096, np.int32)
    phase = 'open'; ph_t = 0.0; u = 0.0; du = 0.0
    events = dict(hits=[], crush=[], wall=[], escape=[], spawn_overlap=0, max_overlap=0.0)
    frames = []
    full_t = None; t = 0.0; step_i = 0; caught_idx = np.zeros(0, int)
    last_wall = -1
    out_alive = []
    while True:
        # ---- mechanism state machine
        if phase == 'open' or phase == 'pause':
            if phase == 'pause' and ph_t >= T_PAUSE:
                phase = 'open'; ph_t = 0.0
            if phase == 'open' and full_t is None:
                act = (flag[:n] & 2) == 0
                z = mech.in_zone(x[:n], y[:n]) & act
                if z.any():
                    caught_idx = np.nonzero(z)[0]; flag[caught_idx] |= 1
                    phase = 'close'; ph_t = 0.0
                    events['hits'].append(dict(t0=t, n=int(len(caught_idx))))
                    y0c = y[caught_idx].copy()
            u, du = 0.0, 0.0
        if phase == 'close':
            s = min(1.0, ph_t / T_CLOSE); u, du = ease_close(s); du /= T_CLOSE
            if s >= 1.0:
                # CRUSH all caught balls
                u = 1.0; du = 0.0
                hit = events['hits'][-1]; hit['tc'] = t; hit['crushed'] = int(len(caught_idx))
                keep = np.ones(n, bool); newb = []
                for k, i in enumerate(caught_idx):
                    L = int(lv[i]); L2 = min(L + 1, NLV - 1); rc = max(RMIN, rt[i] * SHRINK)
                    events['crush'].append((t, float(x[i]), float(y[i]), L, L2))
                    keep[i] = False
                    for side in (-1, 1):
                        newb.append((float(y0c[k]), rc, L2, side))
                # compact
                idx = np.nonzero(keep)[0]; m = len(idx)
                for arr in (x, y, vx, vy, r, lv, flag, ry, rt, tb, bid, born):
                    arr[:m] = arr[idx]
                n = m
                for (yy0, rc, L2, side) in newb:
                    cand = np.array(mech.spawn_candidates(CX, yy0, rc, side))
                    cand = cand[np.hypot(cand[:, 0] - CX, cand[:, 1] - CY) <= R - rc - 1][:600]
                    # child "grows in" from GROW0*rc to rc in T_GROW s, so it never lands deep inside another ball
                    r0c = GROW0 * rc
                    if n:
                        d = np.hypot(x[:n][None, :] - cand[:, 0:1], y[:n][None, :] - cand[:, 1:2]) - r[:n][None, :] - r0c
                        ovs = np.maximum(0, -d.min(1))
                        okk = np.nonzero(ovs == 0)[0]
                        k_ = int(okk[0]) if len(okk) else int(np.argmin(ovs)); bov = ovs[k_]
                    else:
                        k_ = 0; bov = 0.0
                    best = tuple(cand[k_])
                    if bov > 0: events['spawn_overlap'] += 1
                    dvec = mech.eject_dir(side, rng)
                    x[n], y[n] = best; vx[n], vy[n] = V * dvec; r[n] = r0c; rt[n] = rc; tb[n] = t; lv[n] = L2; flag[n] = 0; bid[n] = next_id; born[n] = t; next_id += 1; n += 1
                caught_idx = np.zeros(0, int)
                phase = 'hold'; ph_t = 0.0
                area = np.sum(np.pi * rt[:n][(flag[:n] & 2) == 0] ** 2)
                hit['n_after'] = n; hit['fill'] = float(area / (math.pi * R * R)); hit['lv'] = np.bincount(lv[:n], minlength=NLV).tolist()
                if area >= FILL * math.pi * R * R and full_t is None:
                    full_t = t
        elif phase == 'hold':
            u, du = 1.0, 0.0
            if ph_t >= T_HOLD: phase = 'reopen'; ph_t = 0.0
        if phase == 'reopen':
            s = min(1.0, ph_t / T_OPEN); u, du = ease_open(s); du /= T_OPEN
            if s >= 1.0:
                u, du = 0.0, 0.0; phase = 'pause' if full_t is None else 'stopped'; ph_t = 0.0
        if phase == 'stopped':
            u, du = 0.0, 0.0
        # ---- physics
        tg = T_GROW if n < DENSE_N else T_GROW_DENSE
        r[:n] = np.where(tb[:n] > -1, rt[:n] * np.minimum(1.0, GROW0 + (1 - GROW0) * (t - tb[:n]) / tg), rt[:n])
        pl = mech.polys(u, du)
        pk = []
        for (vv, pvx, pvy, w, px, py) in pl:
            pk += [len(vv), pvx, pvy, w, px, py] + list(vv.ravel())
        pk = np.array(pk, np.float64)
        segs = np.array(mech.cage() if phase == 'close' else [(0, 0, 0, 0)], np.float64).ravel()
        nseg = len(mech.cage()) if phase == 'close' else 0
        xs0, ys0 = x[:n].copy(), y[:n].copy()
        xs, ys, vxs, vys, rs, fs = x[:n].copy(), y[:n].copy(), vx[:n].copy(), vy[:n].copy(), r[:n].copy(), flag[:n].copy()
        nwh = LIB.step(n, xs, ys, vxs, vys, rs, fs, CX, CY, R, slit_a, slit_h, len(pl), pk, nseg, segs, V, DT, ITERS if n < DENSE_N else ITERS_DENSE, stats, whi)
        x[:n], y[:n], vx[:n], vy[:n], flag[:n] = xs, ys, vxs, vys, fs
        if stats[2] > events['max_overlap']:
            i_, j_ = int(stats[1]), int(stats[3])
            events['max_overlap'] = float(stats[2]); events['max_ov_info'] = (round(t, 3), phase, int(flag[i_]), int(flag[j_]), round(float(x[i_])), round(float(y[i_])), round(float(r[i_]),1), round(float(r[j_]),1))
        ry[:n] = r[:n]
        if phase == 'close' and len(caught_idx):
            ci = caught_idx
            x[ci], y[ci], vy[ci], ry[ci] = mech.squash(x[ci], y[ci], vy[ci], r[ci], u)
        if DEBUG and phase == 'close':
            fr_ = ((flag[:n] & 3) == 0) & (np.abs(x[:n] - CX) < mech.HW - 1) & (np.abs(y[:n] - CY) < mech.face(u) - 1)
            if fr_.any():
                i_ = np.nonzero(fr_)[0][0]
                print('INTRUDER t=%.3f u=%.2f pos=(%.1f,%.1f) r=%.1f prev=(%.1f,%.1f) tb=%.2f' % (t, u, x[i_], y[i_], r[i_], xs0[i_], ys0[i_], tb[i_])); DEBUG -= 1
        if nwh and t - last_wall >= 0.06:
            events['wall'].append(t); last_wall = t
        # escapes
        newout = np.nonzero(((flag[:n] & 2) != 0) & ((flag[:n] & 4) == 0))[0]
        for i in newout:
            flag[i] |= 4
            events['escape'].append(dict(t=t, x=float(x[i]), y=float(y[i]), lv=int(lv[i]), r=float(r[i])))
            if early and early.get('max_escape') is not None and len(events['escape']) > early['max_escape']:
                return dict(ok=False, why='too many escapes', events=events, seed=seed)
        # drop escaped balls far off screen
        far = ((flag[:n] & 2) != 0) & ((x[:n] < -100) | (x[:n] > 1180) | (y[:n] < -100) | (y[:n] > 2020))
        if far.any():
            idx = np.nonzero(~far)[0]; m = len(idx)
            ci_map = None
            for arr in (x, y, vx, vy, r, lv, flag, ry, rt, tb, bid, born):
                arr[:m] = arr[idx]
            if len(caught_idx):
                remap = -np.ones(n, int); remap[idx] = np.arange(m); caught_idx = remap[caught_idx]
            n = m
        if record and step_i % 4 == 0:
            frames.append(dict(t=t, u=u, x=x[:n].astype(np.float32), y=y[:n].astype(np.float32),
                               r=r[:n].astype(np.float32), ry=ry[:n].astype(np.float32), lv=lv[:n].copy(),
                               caught=(flag[:n] & 1).astype(bool), id=bid[:n].copy()))
        t += DT; ph_t += DT; step_i += 1
        if full_t is not None and t >= full_t + END_HOLD:
            break
        if t > cfg['tmax']:
            return dict(ok=False, why='timeout', events=events, seed=seed, n=n)
        if early and early.get('tmin_full') and full_t is not None and full_t < early['tmin_full']:
            return dict(ok=False, why='too fast %.1f' % full_t, events=events, seed=seed)
    res = dict(ok=True, seed=seed, full_t=full_t, end_t=t, events=events, n=n, slit_a=slit_a, slit_h=slit_h,
               levels=np.bincount(lv[:n], minlength=NLV).tolist(),
               balls=[(int(bid[i]), int(lv[i]), float(born[i])) for i in range(n)])
    if record: res['frames'] = frames
    return res


if __name__ == '__main__':
    import sys, time
    t0 = time.time(); res = run(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    ev = res['events']
    print('ok', res['ok'], res.get('why'), 'full_t', res.get('full_t'), 'n', res.get('n'), 'hits', len(ev['hits']),
          'escapes', [round(e['t'], 2) for e in ev['escape']], 'levels', res.get('levels'),
          'spawn_ov', ev['spawn_overlap'], 'maxov %.2f' % ev['max_overlap'], 'wall', len(ev['wall']), '%.1fs' % (time.time() - t0))
