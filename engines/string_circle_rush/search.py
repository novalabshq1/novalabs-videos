# Usage: python3 search.py START END [NPROC]  -> valid seeds for the RUSH rules (headless)
import sim, sys, numpy as np, multiprocessing as mp
sim.PLOW_K = 10**9; sim.MAX_T = 62; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC

def one(seed):
    r = sim.run(SPEC, seed, 200, 35)
    if r['end_t'] is None or r['t2'] is None: return None
    tot = r['end_t'] + 1.5
    d = [x[0] for x in r['deaths']]
    duel = r['end_t'] - r['t2']
    c = r['counts']; i2 = int(r['t2'] * 60)
    fin = [i for i in range(c.shape[1]) if c[i2:, i].max() > 0 and c[-1, i] >= 0 and any(c[i2:, i] > 0)]
    lead = []
    for row in c[i2:]:
        a = [row[i] for i in fin]
        if len(a) == 2 and a[0] != a[1]:
            l = fin[int(np.argmax(a))]
            if not lead or lead[-1] != l: lead.append(l)
    mn = {i: int(c[i2:, i][c[i2:, i] > 0].min()) for i in fin}
    w = [x.name for x in r['cs']].index(r['winner'])
    comeback = mn[w] <= 5
    return dict(seed=seed, tot=round(tot, 1), deaths=[round(x, 1) for x in d], duel=round(duel, 1),
                lead_changes=len(lead) - 1, comeback=comeback, min_w=mn[w], vmax=round(r['speeds'].max() / 200, 1),
                winner=r['winner'], finalists=[r['cs'][i].name for i in fin])

if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2]); n = int(sys.argv[3]) if len(sys.argv) > 3 else mp.cpu_count()
    with mp.Pool(n) as p:
        for r in p.imap_unordered(one, range(a, b), chunksize=4):
            if r: print(r, flush=True)
