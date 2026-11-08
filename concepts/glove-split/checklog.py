"""Log checks: every split = 2 balls of the NEXT colour, order kept, no ball outside the ring before the burst."""
import sys, numpy as np
from sim import RAD, CX, CY, R_IN
d = np.load(sys.argv[1]); sp = d['splits']; tb = float(d['t_boom'])
ok = True
for t, c0, c1, c2, n in sp:
    if not (c1 == c0 + 1 and c2 == c0 + 1): ok = False; print('BAD split', t, c0, c1, c2)
print('splits', len(sp), 'all next-colour x2:', ok, 'n after last split', int(sp[-1, 4]))
pos, col, off = d['pos'], d['col'], d['off']
worst = -1e9
for fi in range(len(off) - 1):
    if (fi + 1) / 60 >= tb: break
    P = pos[off[fi]:off[fi + 1]]; K = col[off[fi]:off[fi + 1]]
    r = np.hypot(P[:, 0] - CX, P[:, 1] - CY) + RAD[K]
    worst = max(worst, (r - R_IN).max())
    if fi > 0 and off[fi + 1] - off[fi] - (off[fi] - off[fi - 1]) < 0: print('ball lost at', fi)
print('max (ball edge - ring inner edge) before burst: %.2f px' % worst, 'wall_viol', int(d['wall_viol']))
st = sp[:, 0]; g = np.diff(st[st > 1]); print('max gap between splits after 1 s: %.2f s' % g.max())
counts = {}
for fi in [int(x * 60) for x in (5, 10, 15, 20, 25, 30, 35, 39) if x < tb]:
    K = col[off[fi]:off[fi + 1]]; counts[fi // 60] = (len(K), np.bincount(K, minlength=9).tolist())
for k, v in counts.items(): print(k, 's ->', v)
# penetration into the mechanism (should stay ~0 px)
import sim
th = d["theta"]; worst = 0; bad = []
for fi in range(0, len(off) - 1):
    if (fi + 1) / 60 >= tb: break
    P = pos[off[fi]:off[fi + 1]].astype(float); rb = RAD[col[off[fi]:off[fi + 1]]]; t_ = float(th[fi]); ca, sa = np.cos(t_), np.sin(t_)
    for (gx, gy), gr, _ in sim.mech_circles(t_):
        worst = max(worst, (rb + gr - np.hypot(P[:, 0] - gx, P[:, 1] - gy)).max())
    for (ax, ay, bx, by, hw) in ((CX - sim.ARM_L * ca, CY - sim.ARM_L * sa, CX + sim.ARM_L * ca, CY + sim.ARM_L * sa, sim.ARM_HW), (CX, CY, CX, CY + 1e-3, sim.HUB_R)):
        worst = max(worst, sim.seg_contact(P, rb, ax, ay, bx, by, hw)[0].max())
    if worst > 2 and (not bad or bad[-1][1] != round(worst, 1)): bad.append((fi, round(worst, 1)))
print("max penetration into mechanism: %.2f px" % worst, "frames >2px:", bad)
