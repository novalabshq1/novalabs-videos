# Usage: python3 search.py START END [NPROC]  -> JSON lines with metrics for every finished seed (validated settings)
import sim, sys, json, numpy as np
from multiprocessing import Pool
sim.PLOW_K = 10**9; sim.MAX_T = 62; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC

def analyse(seed):
    r = sim.run(SPEC, seed, 200, 35)
    if r['end_t'] is None or r['t2'] is None: return None
    tot = r['end_t'] + sim.END_HOLD
    d = [round(x[0], 2) for x in r['deaths']]
    c = r['counts']
    duel = r['end_t'] - r['t2']
    f2 = int(r['t2'] * sim.FPS)
    names = [s[0] for s in SPEC]
    wi = names.index(r['winner'])
    li = [i for i in range(len(SPEC)) if i != wi and c[f2, i] > 0]
    li = li[0] if li else None
    # leader changes during the duel
    leaders = []
    for row in c[f2:]:
        if row.max() > 0 and (row == row.max()).sum() == 1:
            ld = int(row.argmax())
            if not leaders or leaders[-1] != ld: leaders.append(ld)
    # comeback: a duellist at 1-5 strings that later gets back above 25
    comeback = False
    for i in [wi, li]:
        if i is None: continue
        col = c[f2:, i]
        low = np.where((col >= 1) & (col <= 5))[0]
        if len(low) and (col[low[0]:] > 25).any(): comeback = True
    # stuck / circling: longest time a living ball goes without touching the wall
    wt = {}
    for (t, ci, b, a) in r['walls']: wt.setdefault(ci, []).append(t)
    gaps = []
    for ci in range(len(SPEC)):
        tl = [0.0] + wt.get(ci, [])
        dt_ = [x[0] for x in r['deaths'] if x[2] == SPEC[ci][1]]
        tl.append(dt_[0] if dt_ else r['end_t'])
        gaps.append(max(np.diff(tl)))
    return dict(seed=seed, tot=round(tot, 2), deaths=d, duel=round(duel, 2), winner=r['winner'],
                lead_changes=len(leaders) - 1, comeback=comeback, max_gap=round(float(max(gaps)), 2),
                vmax=round(float(r['speeds'].max()), 0))

if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2])
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    with Pool(n) as p:
        for res in p.imap_unordered(analyse, range(a, b)):
            if res: print(json.dumps(res), flush=True)
