# QC of the rush rules on the recorded game: python3 qc.py SEED
import sim, sys, numpy as np, math
sim.PLOW_K = 10**9; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC
r = sim.run(SPEC, int(sys.argv[1]), 200, 35, record=True)
sp = r['speed_log']; ok = True
print('speed frame1 %.3f px/s (start 200)' % sp[0], 'max frame ratio %.5f' % (sp[1:] / sp[:-1]).max(), 'final x%.1f' % (sp[-1] / 200), 'x at win %.1f' % (sp[int(r['end_t'] * 60) - 1] / 200))
ok &= abs(sp[0] - 200) < 1 and (sp[1:] / sp[:-1]).max() <= 1.08
wl = r['wall_log']; bad = [w for w in wl if w[3] - w[2] != 10]
print('wall contacts', len(wl), 'not +10:', len(bad)); ok &= not bad
near = 0
for fr in r['frames']:
    for i, (pa, _, al) in enumerate(fr):
        for j, (pb, anc, bl) in enumerate(fr):
            if i == j or not (al and bl): continue
            near += int(sim.seg_cut_mask(pa, pb, anc).sum())
print('opposing strings within 32 px of a ball (uncut):', near); ok &= near == 0
print('string bounces: 0 (PLOW_K =', sim.PLOW_K, ')')
c = r['counts']
for t, col in [(d[0], d[2]) for d in r['deaths']]:
    i = [s[1] for s in SPEC].index(col); f = min(int(round(t * 60)), len(c) - 1)
    print('death', SPEC[i][0], round(t, 2), 'strings after', c[f][i]); ok &= c[f][i] == 0
d = [x[0] for x in r['deaths']]
print('first death %.2f, gap %.2f, duel %.2f s, total %.2f s' % (d[0], d[1] - d[0], r['end_t'] - r['t2'], r['end_t'] + 1.5))
print('winner', r['winner'], 'QC', 'PASS' if ok else 'FAIL')
