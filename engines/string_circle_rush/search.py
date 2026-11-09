# Usage: python3 search.py START END [NPROC] -> prints candidate seeds (rush rules, headless)
import sim, sys, numpy as np, multiprocessing as mp
sim.PLOW_K = 10**9; sim.MAX_T = 62; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC

def one(seed):
    r = sim.run(SPEC, seed, 200, 35)
    if r['end_t'] is None: return None
    tot = r['end_t'] + 1.5
    d = [x[0] for x in r['deaths']]
    duel = r['end_t'] - r['t2']
    c = r['counts']
    # leader changes and comeback during the duel
    f2 = int(r['t2'] * sim.FPS)
    alive2 = [i for i in range(c.shape[1]) if c[f2 + 1:, i].max() > 0] if f2 + 1 < len(c) else []
    lead = []
    for row in c[f2:]:
        if len(alive2) == 2 and row[alive2[0]] != row[alive2[1]]:
            ld = alive2[0] if row[alive2[0]] > row[alive2[1]] else alive2[1]
            if not lead or lead[-1] != ld: lead.append(ld)
    names = [s[0] for s in SPEC]
    wi = names.index(r['winner'])
    wmin = int(c[f2:, wi].min())
    # stuck: longest gap between two wall contacts of a living ball
    gaps = []
    for i in range(c.shape[1]):
        ts = [w[0] for w in r['wall_log'] if w[1] == i]
        dt_ = [x[0] for x in r['deaths'] if x[2] == SPEC[i][1]]
        end = dt_[0] if dt_ else r['end_t']
        ts = [0.0] + ts + [end]
        gaps.append(max(np.diff(ts)))
    return (seed, round(tot, 2), [round(x, 2) for x in d], round(duel, 2), len(lead) - 1, wmin,
            round(max(gaps), 2), round(r['speed_log'].max() / 200, 1), r['winner'])

if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2])
    npr = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    with mp.Pool(npr) as p:
        for res in p.imap_unordered(one, range(a, b)):
            if res: print(*res, flush=True)
