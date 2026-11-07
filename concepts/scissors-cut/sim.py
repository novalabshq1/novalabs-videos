"""Scissors Cut — simulation (MATIN 2026-11-07).
A pair of scissors spins slowly in the centre of a circle and snaps open/closed.
Every ball caught between the closing blades is cut into 4 new balls.
At ~400 balls the ring cracks and explodes.
Usage: python3 sim.py SEED out.npz
"""
import sys, os, numpy as np

FPS = 60
SUB = 8
DT = 1.0 / (FPS * SUB)
CX, CY = 540.0, 1075.0
R_OUT = 450.0
RING_W = 5.0
R_IN = R_OUT - RING_W
BR = 15.0
WALL = R_IN - BR
# scissors geometry (local frame of each half: u along the blade, v perpendicular)
BL = 372.0            # blade length from pivot
HW0, HWT = 24.0, 7.0  # blade half-width at pivot / tip
ARM_L, ARM_HW = 150.0, 12.0
LOOP_D, LOOP_R, LOOP_HOLE = 205.0, 50.0, 27.0
HANDLE_OFF = np.radians(26.0)
HUB_R = 44.0
PHI_MIN, PHI_MAX = np.radians(2.5), np.radians(float(os.environ.get("PHIMAX", "27")))
CAP = 400
VT = 600.0
MAXN = 480
OMEGA = float(os.environ.get("OMEGA", "0.55"))

def period(t):
    # snap rhythm speeds up: 1.35 s -> 0.75 s
    return 1.35 - 0.60 * min(t / 38.0, 1.0)

def ease(x):  # smoothstep
    return x * x * (3 - 2 * x)

def phi_of(p):
    """phase p in [0,1): open (0-.55), hold (.55-.78), snap closed (.78-.88), hold closed."""
    if p < 0.55:
        return PHI_MIN + (PHI_MAX - PHI_MIN) * ease(p / 0.55), 0
    if p < 0.78:
        return PHI_MAX, 1
    if p < 0.88:
        x = (p - 0.78) / 0.10
        return PHI_MAX - (PHI_MAX - PHI_MIN) * x * x, 2   # accelerating snap
    return PHI_MIN, 3

def parts(theta, phi):
    """list of (kind, side, angle, u0, u1, hw0, hw1) capsules + discs."""
    aA, aB = theta + phi, theta - phi
    hA, hB = aA + np.pi + HANDLE_OFF, aB + np.pi - HANDLE_OFF
    return aA, aB, hA, hB

def caps_contact(lx, ly, u0, u1, h0, h1):
    uc = np.clip(lx, u0, u1)
    hw = h0 + (h1 - h0) * (uc - u0) / (u1 - u0)
    ex, ey = lx - uc, ly
    d = np.hypot(ex, ey)
    pen = BR + hw - d
    dd = np.maximum(d, 1e-9)
    nx = np.where(d > 1e-9, ex / dd, 0.0); ny = np.where(d > 1e-9, ey / dd, 1.0)
    return pen, nx, ny, uc

def main(seed, out, t_max=62.0):
    rng = np.random.default_rng(seed)
    pos = np.zeros((MAXN, 2)); vel = np.zeros((MAXN, 2))
    col = np.zeros(MAXN, np.int16); cd = np.zeros(MAXN); ghost = np.zeros(MAXN, bool); age = np.zeros(MAXN)
    theta = rng.uniform(0, 2 * np.pi)
    # first ball sits inside the open wedge, moving outward-ish: first cut within ~1 s
    n = 1
    r0 = 230.0
    pos[0] = (CX + r0 * np.cos(theta), CY + r0 * np.sin(theta))
    a = theta + rng.uniform(-0.5, 0.5) + np.pi * 0.5
    vel[0] = (VT * np.cos(a), VT * np.sin(a))
    col[0] = 0
    ph = 0.25          # start already half open
    t = 0.0
    frames_pos, frames_col, frames_n, thetas, phis, frames_gh = [], [], [], [], [], []
    events = []
    exploded_t = None; boom_done = False; snapped_final = False
    phi_prev, _ = phi_of(ph)
    for fi in range(int(t_max * FPS)):
        for s in range(SUB):
            ph += DT / period(t)
            if exploded_t is not None and not boom_done and ph < 0.97:
                ph = min(ph, 0.77)          # freeze wide open while the ring cracks
            if boom_done and not snapped_final and ph < 0.78:
                ph = max(ph, 0.78); snapped_final = True   # one last snap right at the boom
            if ph >= 1.0:
                ph -= 1.0
            phi, stage = phi_of(ph)
            dphi = (phi - phi_prev) / DT
            if phi_prev > PHI_MIN + 1e-6 and phi <= PHI_MIN + 1e-9:
                events.append((t, 'clac', CX, CY, 0.0))
            phi_prev = phi
            theta += OMEGA * DT
            P = pos[:n]; V = vel[:n]
            P += V * DT
            cd[:n] -= DT; age[:n] += DT
            # --- ball-ball
            if n > 1:
                dx = P[:, None, 0] - P[None, :, 0]; dy = P[:, None, 1] - P[None, :, 1]
                d2 = dx * dx + dy * dy
                mask = np.triu(d2 < (2 * BR) ** 2, 1)
                ii, jj = np.nonzero(mask)
                if len(ii):
                    ddx = dx[ii, jj]; ddy = dy[ii, jj]; dd = np.sqrt(d2[ii, jj]) + 1e-9
                    nx = ddx / dd; ny = ddy / dd
                    corr = 0.5 * (2 * BR - dd)
                    np.add.at(P[:, 0], ii, nx * corr); np.add.at(P[:, 1], ii, ny * corr)
                    np.add.at(P[:, 0], jj, -nx * corr); np.add.at(P[:, 1], jj, -ny * corr)
                    rvx = V[ii, 0] - V[jj, 0]; rvy = V[ii, 1] - V[jj, 1]
                    vn = rvx * nx + rvy * ny
                    app = vn < 0
                    imp = np.where(app, vn, 0)
                    np.add.at(V[:, 0], ii, -imp * nx); np.add.at(V[:, 1], ii, -imp * ny)
                    np.add.at(V[:, 0], jj, imp * nx); np.add.at(V[:, 1], jj, imp * ny)
                    for q in np.nonzero(app & (vn < -300))[0][:2]:
                        events.append((t, 'clack', P[ii[q], 0], P[ii[q], 1], float(-vn[q])))
            # --- wall
            if not boom_done:
                d = P - (CX, CY); r = np.hypot(d[:, 0], d[:, 1])
                hit = r > WALL
                if hit.any():
                    hk_ = np.nonzero(hit)[0]
                    nn = d[hit] / r[hit, None]
                    vn = (V[hit] * nn).sum(1)
                    V[hit] -= (2 * np.maximum(vn, 0))[:, None] * nn
                    P[hit] = (CX, CY) + nn * WALL
                    for q in np.nonzero(vn > 80)[0]:
                        events.append((t, 'wall', P[hk_[q], 0], P[hk_[q], 1], float(vn[q])))
            # --- scissors
            aA, aB, hA, hB = parts(theta, phi)
            omA, omB = OMEGA + dphi, OMEGA - dphi
            d = P - (CX, CY)
            best = np.zeros(n); bnx = np.zeros(n); bny = np.zeros(n); bom = np.zeros(n)
            cut_side = np.zeros(n, np.int8)   # 1 if touching a blade's inner edge
            for (ang, om, inner_sign, isblade, u0, u1, h0, h1) in (
                    (aA, omA, -1, True, 0.0, BL, HW0, HWT), (aB, omB, 1, True, 0.0, BL, HW0, HWT),
                    (hA, omA, 0, False, 0.0, ARM_L, ARM_HW, ARM_HW), (hB, omB, 0, False, 0.0, ARM_L, ARM_HW, ARM_HW),
                    (hA, omA, 0, False, LOOP_D, LOOP_D + 1e-3, LOOP_R, LOOP_R), (hB, omB, 0, False, LOOP_D, LOOP_D + 1e-3, LOOP_R, LOOP_R)):
                c_, s_ = np.cos(ang), np.sin(ang)
                lx = d[:, 0] * c_ + d[:, 1] * s_
                ly = -d[:, 0] * s_ + d[:, 1] * c_
                pen, nx, ny, uc = caps_contact(lx, ly, u0, u1, h0, h1)
                better = (pen > 0) & (pen > best)
                if not better.any(): continue
                wnx = nx * c_ - ny * s_; wny = nx * s_ + ny * c_
                best = np.where(better, pen, best); bnx = np.where(better, wnx, bnx); bny = np.where(better, wny, bny)
                bom = np.where(better, om, bom)
                if isblade:
                    inner = better & (np.sign(ly) == inner_sign) & (uc > 20)
                    cut_side = np.where(better, inner.astype(np.int8), cut_side)
            # hub
            r = np.hypot(d[:, 0], d[:, 1]); pen = BR + HUB_R - r
            better = (pen > 0) & (pen > best)
            best = np.where(better, pen, best)
            bnx = np.where(better, d[:, 0] / np.maximum(r, 1e-9), bnx); bny = np.where(better, d[:, 1] / np.maximum(r, 1e-9), bny)
            bom = np.where(better, OMEGA, bom); cut_side = np.where(better, 0, cut_side)
            # clear ghosts that are free of the mechanism
            ghost[:n] &= ~((best <= 0) & (age[:n] > 0.06))
            hk = np.nonzero((best > 0) & ~ghost[:n])[0]
            cuts = []
            closing = stage == 2
            for k in hk:
                if closing and cut_side[k] and not boom_done and n + 3 * (len(cuts) + 1) <= MAXN:
                    cuts.append(k); continue
                nrm = np.array([bnx[k], bny[k]])
                P[k] += nrm * (best[k] + 0.01)
                q = P[k] - (CX, CY) - nrm * BR
                sv = np.array([-bom[k] * q[1], bom[k] * q[0]])
                rel = V[k] - sv; vn = rel @ nrm
                if vn < 0:
                    V[k] = sv + rel - 2.0 * vn * nrm
                    sp = np.hypot(*V[k])
                    if sp > 1400: V[k] *= 1400 / sp
                    if -vn > 120:
                        events.append((t, 'tink', P[k, 0], P[k, 1], float(-vn)))
            # --- cuts: 1 ball -> 4
            for k in cuts:
                p0 = pos[k].copy()
                base = theta + rng.uniform(0, np.pi / 2)
                kids = [k] + list(range(n, n + 3)); n += 3
                for m, j in enumerate(kids):
                    a = base + np.pi / 4 + m * np.pi / 2
                    dv = np.array([np.cos(a), np.sin(a)])
                    pos[j] = p0 + dv * BR * 0.8
                    rr = np.hypot(*(pos[j] - (CX, CY)))
                    if rr > WALL: pos[j] = (CX, CY) + (pos[j] - (CX, CY)) / rr * WALL
                    vel[j] = dv * VT * rng.uniform(0.95, 1.15)
                    col[j] = (col[k] + 1 + m * 2 + rng.integers(0, 2)) % 7 if m else (col[k] + rng.integers(1, 7)) % 7
                    cd[j] = 0.15; ghost[j] = True; age[j] = 0.0
                events.append((t, 'cut', p0[0], p0[1], float(n)))
            t += DT
        if not boom_done:
            sp = np.hypot(vel[:n, 0], vel[:n, 1]) + 1e-9
            f = 1 + 0.05 * (VT / sp - 1)
            vel[:n] *= f[:, None]
        if exploded_t is None and n >= CAP:
            exploded_t = t + 2.2
            events.append((t, 'crack_start', CX, CY, 0))
        if exploded_t is not None and t >= exploded_t and not boom_done:
            boom_done = True
            events.append((t, 'boom', CX, CY, 0))
            d = pos[:n] - (CX, CY); r = np.hypot(d[:, 0], d[:, 1])[:, None] + 1e-9
            vel[:n] = vel[:n] * 0.5 + d / r * rng.uniform(700, 1300, (n, 1))
        frames_pos.append(pos[:n].astype(np.float32).copy())
        frames_col.append(col[:n].copy()); frames_gh.append(ghost[:n].copy()); frames_n.append(n); thetas.append(theta); phis.append(phi)
        if exploded_t is not None and t > exploded_t + 3.4:
            break
    off = np.cumsum([0] + frames_n)
    np.savez_compressed(out, pos=np.concatenate(frames_pos), col=np.concatenate(frames_col), gh=np.concatenate(frames_gh),
                        off=off, theta=np.array(thetas), phi=np.array(phis), exploded=exploded_t or -1,
                        ev_t=np.array([e[0] for e in events]), ev_k=np.array([e[1] for e in events]),
                        ev_x=np.array([e[2] for e in events]), ev_y=np.array([e[3] for e in events]),
                        ev_s=np.array([e[4] for e in events]))
    print('frames', len(frames_n), 'final n', n, 'explode at', exploded_t)
    print(' '.join(f"{sec}:{frames_n[min(sec * FPS, len(frames_n) - 1)]}" for sec in range(0, int(len(frames_n) / FPS) + 1, 2)))

if __name__ == '__main__':
    main(int(sys.argv[1]), sys.argv[2])
