# Usage: python3 search.py START END [NPROC]  -> prints candidate seeds (validated settings + RUSH rules)
import sim, sys, json, numpy as np
from multiprocessing import Pool
sim.PLOW_K = 10**9; sim.MAX_T = 60.0; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC

def abort(t, deaths, nalive):
    if deaths and deaths[0][0] < 8: return True
    if not deaths and t < 8: return False
    if len(deaths) >= 2 and deaths[1][0] - deaths[0][0] < 5: return True
    if len(deaths) == 1 and len(SPEC) > 2 and t - deaths[0][0] < 5: return False
    if nalive > 2 and t > 60 - 1.5 - 12: return True     # duel would be < 12 s
    return False
sim.ABORT = abort

def one(seed):
    r = sim.run(SPEC, seed, 200, 35)
    if r['end_t'] is None: return None
    tot = r['end_t'] + 1.5
    d = [x[0] for x in r['deaths']]
    if d[0] < 8 or (len(d) > 2 and d[1] - d[0] < 5): return None
    duel = r['end_t'] - r['t2']
    c = r['counts']; f2 = int(r['t2'] * 60)
    cd = c[f2:]
    # leader changes during the duel
    lead = []
    for row in cd:
        if row.max() == 0: continue
        if (row == row.max()).sum() == 1:
            ld = int(row.argmax())
            if not lead or lead[-1] != ld: lead.append(ld)
    # comeback: a ball at 1..5 strings that later climbs back above 15
    comeback = False
    for i in range(c.shape[1]):
        col = c[:, i]; low = np.where((col >= 1) & (col <= 5))[0]
        if len(low) and (col[low[0]:] > 15).any(): comeback = True
    mn = [int(c[:, i][c[:, i] > 0].min()) for i in range(c.shape[1])]
    return dict(seed=seed, tot=round(tot, 2), duel=round(duel, 2), deaths=[round(x, 2) for x in d],
                order=[[cc.name for cc in r['cs']].index(n) for n in []], winner=r['winner'],
                lead_changes=len(lead) - 1, comeback=comeback, min_strings=mn,
                vmax=round(float(r['speeds'].max()), 0))

if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2]); npr = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    with Pool(npr) as p:
        for res in p.imap_unordered(one, range(a, b), chunksize=2):
            if res: print(json.dumps(res), flush=True)
