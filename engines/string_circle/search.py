# Usage: python3 search.py START END   -> prints valid seeds (validated settings)
import sim, sys, numpy as np
sim.PLOW_K = 10**9; sim.MAX_T = 62; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC
for seed in range(int(sys.argv[1]), int(sys.argv[2])):
    r = sim.run(SPEC, seed, 200, 35)
    if r['end_t'] is None: continue
    tot = r['end_t'] + 1.5
    if not 40 <= tot <= 60: continue
    d = [x[0] for x in r['deaths']]
    if d[0] < 10 or (len(d) > 2 and d[1] - d[0] < 7) or r['end_t'] - d[-2] > 22: continue
    c = r['counts']
    mn = [int(c[:, i][c[:, i] > 0].min()) for i in range(c.shape[1])]
    print(seed, round(tot, 1), [round(x, 1) for x in d], 'winner', r['winner'], 'min_strings', mn, flush=True)
