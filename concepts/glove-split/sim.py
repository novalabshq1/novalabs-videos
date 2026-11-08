"""Glove Split — simulation (MATIN 2026-11-08, format « l'échelle de couleurs »).
Two boxing gloves on an arm spin at constant speed in the centre of a circle.
Every ball punched by a glove splits into 2 balls of the NEXT colour of the ladder
(white -> green -> yellow -> orange -> red -> pink -> violet -> blue -> cyan), radius x0.85.
Cyan never splits. At NEXP balls the ring cracks, then bursts: every ball flies out.
Usage: OMEGA=1.6 NEXP=200 python3 sim.py SEED out.npz
"""
import sys, os, numpy as np

FPS = 60
SUB = 8
DT = 1.0 / (FPS * SUB)
CX, CY = 540.0, 1075.0
R_OUT = 450.0               # outer edge of the white ring (diameter 900)
RING_W = 5.0
R_IN = R_OUT - RING_W       # 445
G = 900.0                   # gravity px/s^2
NCOL = 9
RAD = np.array([max(30.0 * 0.85 ** k, 9.0) for k in range(NCOL)])
# mechanism geometry (local frame: u along the arm, v perpendicular, +v = rotation direction)
ARM_L, ARM_HW = 300.0, 13.0
HUB_R = 38.0
FIST_U, FIST_R = 338.0, 60.0
THUMB_U, THUMB_V, THUMB_R = 318.0, 50.0, 22.0
CUFF_U0, CUFF_U1, CUFF_HW = 262.0, 300.0, 36.0
OMEGA = float(os.environ.get("OMEGA", "1.3"))
NEXP = int(os.environ.get("NEXP", "200"))
IMMUNE = float(os.environ.get("IMMUNE", "3.4"))
IMM0 = float(os.environ.get("IMM0", "3.4"))   # immunity of the first colours (green..yellow) so 1->2->4->8 fits in 8 s
PUNCH = float(os.environ.get("PUNCH", "760"))
SPLIT_ANG = np.radians(24.0)
REST_W, REST_B = 0.96, 0.95
VMAX = 1500.0
CRACK_T = 0.6
MAXN = 300


def mech_circles(theta):
    """glove collision circles (x, y, r) and cuff capsules for both gloves, world frame"""
    out = []
    for s in (0, 1):
        a = theta + s * np.pi
        ca, sa = np.cos(a), np.sin(a)
        # local -> world: u*(ca,sa) + v*(-sa,ca); +v must be the direction of motion (omega>0 -> ccw in math, cw on screen y-down)
        def w(u, v):
            return CX + u * ca - v * sa, CY + u * sa + v * ca
        out.append((w(FIST_U, 0), FIST_R, s))
        out.append((w(THUMB_U, THUMB_V), THUMB_R, s))
    return out


def seg_contact(P, rb, ax, ay, bx, by, hw):
    """capsule a-b of half width hw vs balls P (n,2). returns pen, nx, ny, closest point"""
    ex, ey = bx - ax, by - ay; L2 = ex * ex + ey * ey
    t = np.clip(((P[:, 0] - ax) * ex + (P[:, 1] - ay) * ey) / L2, 0, 1)
    qx, qy = ax + t * ex, ay + t * ey
    dx, dy = P[:, 0] - qx, P[:, 1] - qy
    d = np.hypot(dx, dy); dd = np.maximum(d, 1e-9)
    return rb + hw - d, dx / dd, dy / dd, qx, qy


def main(seed, out, t_max=60.0, store=True):
    rng = np.random.default_rng(seed)
    pos = np.zeros((MAXN, 2)); vel = np.zeros((MAXN, 2))
    col = np.zeros(MAXN, np.int16); imm = np.zeros(MAXN)
    theta = rng.uniform(0, 2 * np.pi)
    n = 1
    pos[0] = (CX + rng.uniform(-60, 60), CY - 300)
    vel[0] = (rng.uniform(-120, 120), 0)
    t = 0.0
    F_pos, F_col, F_n, F_th = [], [], [], []
    events = []       # (t, kind, x, y, a, b)  kinds: 0 split(parent col), 1 wall bounce, 2 ball-ball, 3 glove hit(no split), 4 crack, 5 boom
    splits = []       # (t, parent_col, child1_col, child2_col, n_after)
    t_crack = None; t_boom = None
    wall_viol = 0
    for fi in range(int(t_max * FPS)):
        for s in range(SUB):
            t += DT
            theta += OMEGA * DT
            P = pos[:n]; V = vel[:n]; rb = RAD[col[:n]]
            V[:, 1] += G * DT
            P += V * DT
            imm[:n] -= DT
            # ---- ball-ball (off after the burst: everything flies free)
            if n > 1 and t_boom is None:
                dx = P[:, None, 0] - P[None, :, 0]; dy = P[:, None, 1] - P[None, :, 1]
                rs = rb[:, None] + rb[None, :]
                d2 = dx * dx + dy * dy
                ii, jj = np.nonzero(np.triu(d2 < rs * rs, 1))
                if len(ii):
                    dd = np.sqrt(d2[ii, jj]) + 1e-9
                    nx = dx[ii, jj] / dd; ny = dy[ii, jj] / dd
                    mi = rb[ii] ** 2; mj = rb[jj] ** 2; wi = mj / (mi + mj); wj = mi / (mi + mj)
                    corr = rs[ii, jj] - dd
                    np.add.at(P[:, 0], ii, nx * corr * wi); np.add.at(P[:, 1], ii, ny * corr * wi)
                    np.add.at(P[:, 0], jj, -nx * corr * wj); np.add.at(P[:, 1], jj, -ny * corr * wj)
                    vn = (V[ii, 0] - V[jj, 0]) * nx + (V[ii, 1] - V[jj, 1]) * ny
                    app = vn < 0
                    J = np.where(app, -(1 + REST_B) * vn, 0)
                    np.add.at(V[:, 0], ii, J * nx * wi); np.add.at(V[:, 1], ii, J * ny * wi)
                    np.add.at(V[:, 0], jj, -J * nx * wj); np.add.at(V[:, 1], jj, -J * ny * wj)
                    for q in np.nonzero(app & (vn < -350))[0][:2]:
                        events.append((t, 2, P[ii[q], 0], P[ii[q], 1], float(-vn[q]), 0))
            # ---- mechanism: arm + hub + cuffs (a touch also splits)
            to_split = []
            ca, sa = np.cos(theta), np.sin(theta)
            for (ax, ay, bx, by, hw) in ((CX - ARM_L * ca, CY - ARM_L * sa, CX + ARM_L * ca, CY + ARM_L * sa, ARM_HW),
                                         (CX, CY, CX, CY + 1e-3, HUB_R),
                                         (CX + CUFF_U0 * ca, CY + CUFF_U0 * sa, CX + CUFF_U1 * ca, CY + CUFF_U1 * sa, CUFF_HW),
                                         (CX - CUFF_U0 * ca, CY - CUFF_U0 * sa, CX - CUFF_U1 * ca, CY - CUFF_U1 * sa, CUFF_HW)) if t_boom is None else ():
                pen, nx, ny, qx, qy = seg_contact(P, rb, ax, ay, bx, by, hw)
                hit = np.nonzero(pen > 0)[0]
                if len(hit):
                    P[hit, 0] += nx[hit] * pen[hit]; P[hit, 1] += ny[hit] * pen[hit]
                    # surface velocity omega x r
                    sx = -OMEGA * (qy[hit] - CY); sy = OMEGA * (qx[hit] - CX)
                    rvn = (V[hit, 0] - sx) * nx[hit] + (V[hit, 1] - sy) * ny[hit]
                    for q, b in enumerate(hit):
                        if rvn[q] < 0:
                            V[b, 0] -= (1 + REST_W) * rvn[q] * nx[hit[q]]; V[b, 1] -= (1 + REST_W) * rvn[q] * ny[hit[q]]
                            if imm[b] <= 0 and col[b] < NCOL - 1 and t_crack is None:
                                to_split.append(b)
                            elif imm[b] <= 0:
                                events.append((t, 3, P[b, 0], P[b, 1], float(-rvn[q]), int(col[b])))
            # ---- gloves: punch -> split
            for (gx, gy), gr, side in (mech_circles(theta) if t_boom is None else []):
                dx = P[:, 0] - gx; dy = P[:, 1] - gy; d = np.hypot(dx, dy)
                pen = rb + gr - d
                hit = np.nonzero(pen > 0)[0]
                if not len(hit): continue
                dd = np.maximum(d[hit], 1e-9); nx = dx[hit] / dd; ny = dy[hit] / dd
                P[hit, 0] += nx * pen[hit]; P[hit, 1] += ny * pen[hit]
                cx_, cy_ = gx + nx * gr, gy + ny * gr
                sx = -OMEGA * (cy_ - CY); sy = OMEGA * (cx_ - CX)
                rvn = (V[hit, 0] - sx) * nx + (V[hit, 1] - sy) * ny
                for q, b in enumerate(hit):
                    if rvn[q] < 0:
                        V[b, 0] -= (1 + REST_W) * rvn[q] * nx[q]; V[b, 1] -= (1 + REST_W) * rvn[q] * ny[q]
                        vn_out = V[b, 0] * nx[q] + V[b, 1] * ny[q]
                        if vn_out < PUNCH:
                            V[b, 0] += (PUNCH - vn_out) * nx[q]; V[b, 1] += (PUNCH - vn_out) * ny[q]
                        if imm[b] <= 0 and col[b] < NCOL - 1 and t_crack is None:
                            to_split.append(b)
                        elif imm[b] <= 0:
                            events.append((t, 3, P[b, 0], P[b, 1], float(-rvn[q]), int(col[b])))
            # ---- wall (hard constraint, while the ring holds)
            if t_boom is None:
                rb = RAD[col[:n]]
                d = P - (CX, CY); r = np.hypot(d[:, 0], d[:, 1])
                lim = R_IN - rb
                o = np.nonzero(r > lim)[0]
                if len(o):
                    nx = d[o, 0] / r[o]; ny = d[o, 1] / r[o]
                    P[o, 0] = CX + nx * lim[o]; P[o, 1] = CY + ny * lim[o]
                    vn = V[o, 0] * nx + V[o, 1] * ny
                    k = vn > 0
                    V[o[k], 0] -= (1 + REST_W) * vn[k] * nx[k]; V[o[k], 1] -= (1 + REST_W) * vn[k] * ny[k]
                    for q in np.nonzero(k & (vn > 380))[0][:2]:
                        events.append((t, 1, P[o[q], 0], P[o[q], 1], float(vn[q]), int(col[o[q]])))
            # ---- splits
            for b in sorted(set(to_split)):
                if n >= MAXN: break
                c0 = int(col[b]); c1 = c0 + 1; r1 = RAD[c1]
                v = V[b].copy(); sp = max(np.hypot(*v), PUNCH)
                u = v / (np.hypot(*v) + 1e-9); pu = np.array([-u[1], u[0]])
                p0 = P[b].copy()
                kids = []
                for sgn, idx in ((1, b), (-1, n)):
                    ang = sgn * SPLIT_ANG
                    dirv = u * np.cos(ang) + pu * np.sin(ang)
                    pos[idx] = p0 + pu * sgn * r1 * 1.02
                    vel[idx] = dirv * sp
                    col[idx] = c1; imm[idx] = IMM0 if c1 <= 2 else IMMUNE
                    kids.append(c1)
                n += 1
                P = pos[:n]; V = vel[:n]
                splits.append((t, c0, kids[0], kids[1], n))
                events.append((t, 0, p0[0], p0[1], sp, c0))
            # ---- second positional pass (balls squeezed between a glove and the wall or by the crowd)
            if t_boom is None:
                P = pos[:n]; rb = RAD[col[:n]]
                for (ax, ay, bx, by, hw) in ((CX - ARM_L * ca, CY - ARM_L * sa, CX + ARM_L * ca, CY + ARM_L * sa, ARM_HW),
                                             (CX, CY, CX, CY + 1e-3, HUB_R),
                                             (CX + CUFF_U0 * ca, CY + CUFF_U0 * sa, CX + CUFF_U1 * ca, CY + CUFF_U1 * sa, CUFF_HW),
                                             (CX - CUFF_U0 * ca, CY - CUFF_U0 * sa, CX - CUFF_U1 * ca, CY - CUFF_U1 * sa, CUFF_HW)):
                    pen, nx, ny, _, _ = seg_contact(P, rb, ax, ay, bx, by, hw); h = pen > 0
                    P[h, 0] += nx[h] * pen[h]; P[h, 1] += ny[h] * pen[h]
                for (gx, gy), gr, _ in mech_circles(theta):
                    dx = P[:, 0] - gx; dy = P[:, 1] - gy; dd = np.maximum(np.hypot(dx, dy), 1e-9); pen = rb + gr - dd; h = pen > 0
                    P[h, 0] += dx[h] / dd[h] * pen[h]; P[h, 1] += dy[h] / dd[h] * pen[h]
                dd_ = P - (CX, CY); r = np.hypot(dd_[:, 0], dd_[:, 1]); lim = R_IN - rb; o = r > lim
                P[o, 0] = CX + dd_[o, 0] / r[o] * lim[o]; P[o, 1] = CY + dd_[o, 1] / r[o] * lim[o]
            P = pos[:n]; V = vel[:n]
            sp = np.hypot(V[:, 0], V[:, 1]); f = np.minimum(1, VMAX / np.maximum(sp, 1e-9))
            if t_boom is None:
                V *= f[:, None]
            if t_crack is None and n >= NEXP:
                t_crack = t; events.append((t, 4, CX, CY, 0, 0))
            if t_crack is not None and t_boom is None and t >= t_crack + CRACK_T:
                t_boom = t; events.append((t, 5, CX, CY, 0, 0))
                d = P - (CX, CY); r = np.hypot(d[:, 0], d[:, 1]) + 1e-9
                boost = rng.uniform(1300, 1700, n)
                V[:, 0] = d[:, 0] / r * boost + V[:, 0] * 0.3
                V[:, 1] = d[:, 1] / r * boost + V[:, 1] * 0.3 - 250
        # frame end: verify containment
        if t_boom is None:
            rb = RAD[col[:n]]
            r = np.hypot(pos[:n, 0] - CX, pos[:n, 1] - CY)
            wall_viol += int(np.sum(r + rb > R_IN + 0.5))
        if store:
            F_pos.append(pos[:n].astype(np.float32).copy()); F_col.append(col[:n].copy()); F_n.append(n); F_th.append(theta)
        if t_boom is not None and t > t_boom + 1.6:
            # all balls off screen?
            on = (pos[:n, 0] > -40) & (pos[:n, 0] < 1120) & (pos[:n, 1] > -40) & (pos[:n, 1] < 1960)
            if not on.any():
                break
    t_end = t + 1.5
    res = dict(splits=np.array(splits) if splits else np.zeros((0, 5)), t_crack=t_crack, t_boom=t_boom, t_end=t_end,
               wall_viol=wall_viol, n_final=n)
    if store:
        off = np.cumsum([0] + F_n)
        ev = np.array(events, dtype=float) if events else np.zeros((0, 6))
        np.savez_compressed(out, pos=np.concatenate(F_pos), col=np.concatenate(F_col), off=off, theta=np.array(F_th),
                            ev=ev, splits=res['splits'], t_crack=t_crack, t_boom=t_boom, t_end=t_end,
                            omega=OMEGA, wall_viol=wall_viol)
    return res


def palier_times(splits):
    """time each colour first appears"""
    out = {0: 0.0}
    for row in splits:
        c = int(row[2])
        if c not in out: out[c] = row[0]
    return out


if __name__ == "__main__":
    r = main(int(sys.argv[1]), sys.argv[2])
    pt = palier_times(r['splits'])
    print('paliers', {k: round(v, 2) for k, v in pt.items()}, 'crack', r['t_crack'], 'boom', r['t_boom'], 'end', round(r['t_end'], 2),
          'n', r['n_final'], 'viol', r['wall_viol'])
