"""physics check: non-ghost balls penetrating the scissors. PHIMAX=38 python3 pen.py sim.npz"""
import sys, numpy as np, sim
d = np.load(sys.argv[1]); pos, off, th, ph, gh = d['pos'], d['off'], d['theta'], d['phi'], d['gh']
boom = float(d['ev_t'][d['ev_k'] == 'boom'][0]); bad = []
for fi in range(len(th)):
    if (fi + 1) / 60 > boom: break
    P = pos[off[fi]:off[fi+1]].astype(float); G = gh[off[fi]:off[fi+1]]; dd = P - (sim.CX, sim.CY)
    aA, aB, hA, hB = sim.parts(th[fi], ph[fi]); best = np.zeros(len(P))
    for ang, u0, u1, h0, h1 in ((aA, 0, sim.BL, sim.HW0, sim.HWT), (aB, 0, sim.BL, sim.HW0, sim.HWT),
                                (hA, 0, sim.ARM_L, sim.ARM_HW, sim.ARM_HW), (hB, 0, sim.ARM_L, sim.ARM_HW, sim.ARM_HW),
                                (hA, sim.LOOP_D, sim.LOOP_D + 1e-3, sim.LOOP_R, sim.LOOP_R), (hB, sim.LOOP_D, sim.LOOP_D + 1e-3, sim.LOOP_R, sim.LOOP_R)):
        c, s = np.cos(ang), np.sin(ang); lx = dd[:, 0]*c + dd[:, 1]*s; ly = -dd[:, 0]*s + dd[:, 1]*c
        pen, *_ = sim.caps_contact(lx, ly, u0, u1, h0, h1); best = np.maximum(best, pen)
    m = (best > 3) & ~G
    if m.any(): bad.append((fi, int(m.sum()), round(float(best[m].max()), 1)))
print('frames with non-ghost penetration > 3 px:', len(bad), bad[:20])
