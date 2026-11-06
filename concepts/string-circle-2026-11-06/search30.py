import sys; sys.path.insert(0, '.')
import sim, numpy as np
sim.PLOW_K = 10**9; sim.MAX_T = 50; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC
N0 = int(sys.argv[3])
for seed in range(int(sys.argv[1]), int(sys.argv[2])):
    r = sim.run(SPEC, seed, 200, N0)
    if r['end_t'] is None: continue
    tot = r['end_t'] + 1.5
    if not 30 <= tot <= 45: continue
    d = [x[0] for x in r['deaths']]
    if d[0] < 8 or (len(d) > 1 and d[1] - d[0] < 5) or r['end_t'] - d[-2] > 15: continue
    c = r['counts']
    leaders = []
    for row in c:
        if (row == row.max()).sum() == 1:
            ld = int(row.argmax())
            if not leaders or leaders[-1] != ld: leaders.append(ld)
    if len(leaders) - 1 < 2: continue
    names = [s[0] for s in SPEC]; w = names.index(r['winner'])
    row = c[int((r['end_t'] - 8) * 60)]
    others = [row[i] for i in range(len(row)) if i != w and row[i] > 0]
    if not others or row[w] > 1.3 * max(others): continue
    mn = [int(c[:, i][c[:, i] > 0].min()) for i in range(c.shape[1])]
    alive8 = int((c[8*60] > 0).sum())
    print(seed, round(tot, 1), [round(x, 1) for x in d], 'winner', r['winner'], 'min', mn, 'lead_changes', len(leaders)-1, 'alive8', alive8, 'wmin', mn[w], flush=True)
