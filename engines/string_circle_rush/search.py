# Usage: python3 search.py NBALLS START END [NPROC]  -> JSON lines of candidate seeds (RUSH rules)
import sim, sys, json, math, numpy as np
from multiprocessing import Pool
sim.PLOW_K = 10**9; sim.MAX_T = 62; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
NB = int(sys.argv[1])
ANG = {4: [225, 315, 45, 135], 5: [270, 342, 54, 126, 198]}[NB]
SPEC = [(f"b{i}", (1, 1, 1), a) for i, a in enumerate(ANG)]

def one(seed):
    r = sim.run(SPEC, seed, 200, 35, early=True)
    if r['end_t'] is None: return None
    tot = r['end_t'] + sim.END_HOLD
    d = [x[0] for x in r['deaths']]
    if d[0] < 8 or d[1] - d[0] < 5: return None
    duel = r['end_t'] - r['t2']
    c = r['counts']; fps = sim.FPS
    i2 = int(r['t2'] * fps)
    alive2 = [i for i in range(NB) if c[i2 + 1, i] > 0]
    sub = c[i2 + 1:, alive2]
    leaders = []
    for row in sub:
        if row[0] != row[1]:
            ld = int(row.argmax())
            if not leaders or leaders[-1] != ld: leaders.append(ld)
    names = [s[0] for s in SPEC]
    w = names.index(r['winner'])
    # comeback: someone at 1-5 strings who then recovers to >= 30
    comeback = False
    for i in range(NB):
        col = c[:, i]
        low = np.where((col >= 1) & (col <= 5))[0]
        if len(low) and (col[low[0]:] >= 30).any(): comeback = True
    # stuck check: max gap between wall contacts per ball while alive
    gaps = []
    for i in range(NB):
        ts = [x[0] for x in r['wall'] if x[1] == i]
        death = next((x[0] for x in r['deaths'] if x[2] == SPEC[i][1] and False), None)
        if ts: gaps.append(max(np.diff([0] + ts)))
    order = [None] * NB  # elimination order by index
    elim = []
    for t0, p, col in r['deaths']:
        # find which index died: the ball whose count dropped to 0 at that frame
        f = min(int(t0 * fps), len(c) - 1)
        for i in range(NB):
            if c[f, i] == 0 and i not in elim and i != w: elim.append(i); break
    return dict(seed=seed, total=round(tot, 2), duel=round(duel, 2), deaths=[round(x, 2) for x in d],
                winner=w, elim=elim, finalists=alive2, lead_changes=len(leaders) - 1, comeback=comeback,
                maxgap=round(max(gaps), 2), vmax=round(float(r['speed'].max()), 0),
                maxstep=round(float((r['speed'][1:] / r['speed'][:-1]).max()), 4))

if __name__ == '__main__':
    a, b = int(sys.argv[2]), int(sys.argv[3])
    npr = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    with Pool(npr) as p:
        for res in p.imap_unordered(one, range(a, b), chunksize=4):
            if res: print(json.dumps(res), flush=True)
