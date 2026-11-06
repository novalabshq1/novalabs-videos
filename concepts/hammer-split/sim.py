"""Hammer Split — simulation.
A giant hammer spins around the centre of a circle. Every ball it hits splits in 2.
When ~400 balls fill the circle, the ring cracks and explodes.
Usage: python3 sim.py SEED out.npz
"""
import sys, os, numpy as np

FPS = 60
SUB = 10
DT = 1.0 / (FPS * SUB)
CX, CY = 540.0, 1075.0
R_OUT = 450.0          # outer edge of ring stroke (width 900)
RING_W = 5.0
R_IN = R_OUT - RING_W  # 445
BR = 16.0              # ball radius
WALL = R_IN - BR
# hammer geometry in hammer frame (x = along handle, y = tangential)
HUB_R = 34.0
HANDLE_L, HANDLE_HW = 262.0, 15.0
HEAD_X0, HEAD_X1, HEAD_HW = 255.0, float(os.environ.get("HX1","372")), 80.0
CAP = 400
import os
COOLDOWN = float(os.environ.get("CD", "0.4"))
VT = 640.0
MAXN = 460

def omega_at(t):
    # spins up slowly: 1.7 rad/s -> 2.6 rad/s
    return 1.7 + 0.9 * min(t / 40.0, 1.0)

def rect_closest(lx, ly, x0, x1, hw):
    qx = np.clip(lx, x0, x1); qy = np.clip(ly, -hw, hw)
    return qx, qy

def main(seed, out, t_max=56.0):
    rng = np.random.default_rng(seed)
    pos = np.zeros((MAXN, 2)); vel = np.zeros((MAXN, 2))
    col = np.zeros(MAXN, np.int16); cd = np.zeros(MAXN)
    n = 1
    pos[0] = (CX - 120, CY + 330); a0 = rng.uniform(0, 2 * np.pi)
    vel[0] = (VT * np.cos(-1.2), VT * np.sin(-1.2))
    col[0] = 0
    theta = rng.uniform(0, 2 * np.pi)
    t = 0.0
    frames_pos, frames_col, frames_n, thetas = [], [], [], []
    events = []  # (time, kind, x, y, strength)
    exploded_t = None
    boom_done = False
    nframes = int(t_max * FPS)
    for fi in range(nframes):
        for s in range(SUB):
            om = omega_at(t)
            theta += om * DT
            P = pos[:n]; V = vel[:n]
            P += V * DT
            cd[:n] -= DT
            # --- wall
            if not boom_done:
                d = P - (CX, CY); r = np.hypot(d[:, 0], d[:, 1])
                hit = r > WALL
                if hit.any():
                    nn = d[hit] / r[hit, None]
                    vn = (V[hit] * nn).sum(1)
                    out_ = vn > 0
                    V[hit] -= (2 * np.where(out_, vn, 0))[:, None] * nn
                    P[hit] = (CX, CY) + nn * WALL
                    hk_ = np.nonzero(hit)[0]
                    for q in np.nonzero(out_)[0]:
                        events.append((t, 'wall', P[hk_[q], 0], P[hk_[q], 1], float(vn[q])))
            # --- hammer
            c, s_ = np.cos(theta), np.sin(theta)
            d = P - (CX, CY)
            lx = d[:, 0] * c + d[:, 1] * s_
            ly = -d[:, 0] * s_ + d[:, 1] * c
            best_pen = np.zeros(n); bnx = np.zeros(n); bny = np.zeros(n); bqx = np.zeros(n); bqy = np.zeros(n); head = np.zeros(n, bool)
            for kind, (x0, x1, hw) in (('head', (HEAD_X0, HEAD_X1, HEAD_HW)), ('handle', (0.0, HANDLE_L, HANDLE_HW))):
                qx, qy = rect_closest(lx, ly, x0, x1, hw)
                ex, ey = lx - qx, ly - qy
                dist = np.hypot(ex, ey)
                inside = dist < 1e-9
                # inside the rect: push out along nearest face
                if inside.any():
                    ii = np.nonzero(inside)[0]
                    dl = np.stack([lx[ii] - x0, x1 - lx[ii], ly[ii] + hw, hw - ly[ii]], 1)
                    m = dl.argmin(1)
                    nxs = np.array([-1, 1, 0, 0.])[m]; nys = np.array([0, 0, -1, 1.])[m]
                    ex[ii] = nxs; ey[ii] = nys; dist[ii] = -dl[np.arange(len(ii)), m]
                pen = BR - dist
                nx = np.where(inside, ex, ex / np.maximum(dist, 1e-9)); ny = np.where(inside, ey, ey / np.maximum(dist, 1e-9))
                better = (pen > 0) & (pen > best_pen)
                best_pen = np.where(better, pen, best_pen)
                bnx = np.where(better, nx, bnx); bny = np.where(better, ny, bny)
                bqx = np.where(better, qx, bqx); bqy = np.where(better, qy, bqy)
                if kind == 'head': head = head | better
                else: head = head & ~better
            # hub
            dist = np.hypot(lx, ly); pen = BR + HUB_R - dist
            better = (pen > 0) & (pen > best_pen)
            best_pen = np.where(better, pen, best_pen)
            bnx = np.where(better, lx / np.maximum(dist, 1e-9), bnx); bny = np.where(better, ly / np.maximum(dist, 1e-9), bny)
            bqx = np.where(better, bnx * HUB_R, bqx); bqy = np.where(better, bny * HUB_R, bqy)
            hk = np.nonzero(best_pen > 0)[0]
            new_balls = []
            for k in hk:
                nwx = bnx[k] * c - bny[k] * s_; nwy = bnx[k] * s_ + bny[k] * c
                qwx = bqx[k] * c - bqy[k] * s_; qwy = bqx[k] * s_ + bqy[k] * c
                sv = np.array([-om * qwy, om * qwx])  # surface velocity
                nrm = np.array([nwx, nwy])
                P[k] += nrm * (best_pen[k] + 0.01)
                rel = V[k] - sv; vn = rel @ nrm
                if vn < 0:
                    V[k] = sv + rel - 2.0 * vn * nrm
                    sp = np.hypot(*V[k])
                    if sp < VT * 1.05: V[k] *= VT * 1.05 / sp
                    strength = float(-vn)
                    split = cd[k] <= 0 and n + len(new_balls) < CAP and exploded_t is None
                    events.append((t, 'bonk', P[k, 0], P[k, 1], strength))
                    if split:
                        new_balls.append(k)
            for k in new_balls:
                j = n; n += 1
                v = vel[k].copy(); ang = 0.42
                ca, sa = np.cos(ang), np.sin(ang)
                vel[k] = (v[0] * ca - v[1] * sa, v[0] * sa + v[1] * ca)
                vel[j] = (v[0] * ca + v[1] * sa, -v[0] * sa + v[1] * ca)
                perp = np.array([-v[1], v[0]]) / max(np.hypot(*v), 1e-9)
                pos[j] = pos[k] - perp * (BR + 0.5); pos[k] = pos[k] + perp * (BR + 0.5)
                for q in (k, j):
                    dd = pos[q] - (CX, CY); rr = np.hypot(*dd)
                    if rr > WALL: pos[q] = (CX, CY) + dd / rr * WALL
                col[j] = (col[k] + 1 + rng.integers(0, 6)) % 7
                cd[k] = COOLDOWN; cd[j] = COOLDOWN
                events.append((t, 'split', pos[k, 0], pos[k, 1], float(n)))
            P = pos[:n]; V = vel[:n]
            # --- ball-ball
            if n > 1:
                dx = P[:, None, 0] - P[None, :, 0]; dy = P[:, None, 1] - P[None, :, 1]
                d2 = dx * dx + dy * dy
                iu = np.triu_indices(n, 1) if n < 60 else None
                mask = d2 < (2 * BR) ** 2
                np.fill_diagonal(mask, False)
                ii, jj = np.nonzero(np.triu(mask))
                if len(ii):
                    ddx = dx[ii, jj]; ddy = dy[ii, jj]; dd = np.sqrt(d2[ii, jj]) + 1e-9
                    nx = ddx / dd; ny = ddy / dd
                    pen = 2 * BR - dd
                    corr = 0.5 * pen
                    np.add.at(P[:, 0], ii, nx * corr); np.add.at(P[:, 1], ii, ny * corr)
                    np.add.at(P[:, 0], jj, -nx * corr); np.add.at(P[:, 1], jj, -ny * corr)
                    rvx = V[ii, 0] - V[jj, 0]; rvy = V[ii, 1] - V[jj, 1]
                    vn = rvx * nx + rvy * ny
                    app = vn < 0
                    imp = np.where(app, vn, 0)
                    np.add.at(V[:, 0], ii, -imp * nx); np.add.at(V[:, 1], ii, -imp * ny)
                    np.add.at(V[:, 0], jj, imp * nx); np.add.at(V[:, 1], jj, imp * ny)
                    for a in np.nonzero(app & (vn < -250))[0][:3]:
                        events.append((t, 'clack', P[ii[a], 0], P[ii[a], 1], float(-vn[a])))
            t += DT
        # speed regulation once per frame (gentle)
        if not boom_done:
            sp = np.hypot(vel[:n, 0], vel[:n, 1]) + 1e-9
            f = 1 + 0.04 * (VT / sp - 1)
            vel[:n] *= f[:, None]
        if exploded_t is None and n >= CAP:
            exploded_t = t + 2.6   # cracks for 2.6 s then BOOM
            events.append((t, 'crack_start', CX, CY, 0))
        if exploded_t is not None and t >= exploded_t and not boom_done:
            boom_done = True
            events.append((t, 'boom', CX, CY, 0))
            d = pos[:n] - (CX, CY); r = np.hypot(d[:, 0], d[:, 1])[:, None] + 1e-9
            vel[:n] = vel[:n] * 0.6 + d / r * rng.uniform(700, 1300, (n, 1))
        frames_pos.append(pos[:n].astype(np.float32).copy())
        frames_col.append(col[:n].copy()); frames_n.append(n); thetas.append(theta)
        if exploded_t is not None and t > exploded_t + 4.5:
            break
    # flatten
    off = np.cumsum([0] + frames_n)
    np.savez_compressed(out, pos=np.concatenate(frames_pos), col=np.concatenate(frames_col),
                        off=off, theta=np.array(thetas), exploded=exploded_t or -1,
                        ev_t=np.array([e[0] for e in events]), ev_k=np.array([e[1] for e in events]),
                        ev_x=np.array([e[2] for e in events]), ev_y=np.array([e[3] for e in events]),
                        ev_s=np.array([e[4] for e in events]))
    print('frames', len(frames_n), 'final n', n, 'explode at', exploded_t)
    for sec in range(0, int(len(frames_n) / FPS) + 1, 3):
        print(sec, frames_n[min(sec * FPS, len(frames_n) - 1)])

if __name__ == '__main__':
    main(int(sys.argv[1]), sys.argv[2])
