# Usage: python3 qc.py SEED   -> physics/log checks for the chosen game (RUSH rules)
import sim, sys, numpy as np, math
sim.PLOW_K = 10**9; sim.MAX_T = 62; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC
seed = int(sys.argv[1])
r = sim.run(SPEC, seed, 200, 35, record=True)
fr = r['frames']; sp = r['speeds']; cols = [s[1] for s in SPEC]; names = [s[0] for s in SPEC]
ok = True
def bad(msg):
    global ok; ok = False; print('FAIL', msg)
# 1) strings never bounce (PLOW_K huge) + no ball within BR of an enemy string that is not cut
viol = 0
for k, f in enumerate(fr):
    for i, (pa, _, al) in enumerate(f):
        if not al: continue
        for j, (pb, anc, bl) in enumerate(f):
            if i == j or not bl: continue
            if sim.seg_cut_mask(pa, pb, anc).any(): viol += 1
print('enemy-string proximity violations (<32 px, uncut):', viol)
if viol: bad('proximity')
# 2) wall contact = +10 strings : per ball, strings added between frames (count change + strings cut) is a multiple of 10
snapcnt = {}
for (t0, p, an, col) in r['snaps']:
    fi = min(len(fr) - 1, int(math.floor(t0 * sim.FPS + 1e-7)))
    snapcnt[(fi, cols.index(col))] = snapcnt.get((fi, cols.index(col)), 0) + 1
walls = 0
for k in range(1, len(fr)):
    for i in range(len(SPEC)):
        a0 = len(fr[k - 1][i][1]); a1 = len(fr[k][i][1])
        added = a1 - a0 + snapcnt.get((k, i), 0)
        if added % 10 != 0 or added < 0: bad(f'frame {k} ball {i} added {added}')
        walls += added // 10
nplu = sum(1 for e in r['events'] if e[1] == 'pluck')
print('wall contacts:', nplu, 'strings added /10 :', walls)
if walls != nplu: bad('wall +10 mismatch')
# 3) every dead ball had 0 strings, no second chance
for i in range(len(SPEC)):
    al = [f[i][2] for f in fr]
    if False in al:
        k = al.index(False)
        if len(fr[k][i][1]) != 0: bad(f'ball {i} died with strings')
        if any(al[k:]): bad(f'ball {i} came back')
print('deaths at', [round(d[0], 2) for d in r['deaths']], 'all with 0 strings')
# 4) speed
v0 = sp[0]; ratio = (sp[1:] / sp[:-1]).max()
print('speed frame1 %.2f px/s (start 200), max frame-to-frame x%.5f (+%.3f %%), final %.0f px/s = x%.1f' % (v0, ratio, (ratio - 1) * 100, sp[-1], sp[-1] / 200))
if abs(v0 - 200) > 1 or ratio > 1.08: bad('speed')
# 5) balls stay inside the circle
for f in fr:
    for (p, _, al) in f:
        if al and math.hypot(p[0] - sim.CX, p[1] - sim.CY) > sim.R - sim.BR + 0.5: bad('outside')
print('steps', r['steps'], 'duel %.2f s (t2 %.2f -> end %.2f)' % (r['end_t'] - r['t2'], r['t2'], r['end_t']), 'total %.2f s' % (r['end_t'] + 1.5))
print('winner', r['winner'])
print('ALL OK' if ok else 'QC FAILED')
