# Usage: python3 search.py START END [NPROC]  -> valid seeds (validated settings + RUSH rules)
import sim, sys, numpy as np, multiprocessing as mp
sim.PLOW_K = 10**9; sim.MAX_T = 66; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC
FPS = sim.FPS

def evaluate(seed):
    r = sim.run(SPEC, seed, 200, 35)
    if r['end_t'] is None: return None
    tot = r['nframes'] / FPS
    d = [x[0] for x in r['deaths']]
    duel = r['end_t'] - d[-2]
    c = r['counts']
    leaders = []
    for row in c:
        mx = row.max()
        if mx > 0 and (row == mx).sum() == 1:
            ld = int(row.argmax())
            if not leaders or leaders[-1] != ld: leaders.append(ld)
    # stuck / circling: longest gap between wall contacts of a living ball
    names = [x.name for x in r['cs']]
    comeback = []
    for i in range(c.shape[1]):
        col = c[:, i]; alive = np.nonzero(col > 0)[0]
        seg = col[alive]
        lo = np.nonzero((seg >= 1) & (seg <= 5))[0]
        if len(lo) and seg[lo[0]:].max() >= 20: comeback.append(names[i])
    # stuck balls: longest run of ball-ball contacts (events < 0.2 s apart)
    tk = [t for (t, k, x) in r['events'] if k == 'tok']
    stuck = 0.0; st0 = None; prev = None
    for t in tk:
        if prev is None or t - prev > 0.2: st0 = t
        stuck = max(stuck, t - st0); prev = t
    return dict(seed=seed, stuck=round(stuck, 2), tot=round(tot, 2), deaths=[round(x, 1) for x in d], duel=round(duel, 1),
                changes=len(leaders) - 1, winner=r['winner'], vmult=round(r['speeds'][-1] / 200, 1),
                order=[names[[k for k in range(len(names)) if r['cs'][k].color == col][0]] for (_, _, col) in r['deaths']],
                comeback=comeback)

def valid(e, lo=50):
    if e is None: return False
    d = e['deaths']
    return (lo <= e['tot'] <= 60 and d[0] >= 10 and (len(d) < 2 or d[1] - d[0] >= 6)
            and 10 <= e['duel'] <= 20 and e['changes'] >= 3 and e['stuck'] <= 0.4)

if __name__ == '__main__':
    a, b = int(sys.argv[1]), int(sys.argv[2]); n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    with mp.Pool(n) as p:
        for e in p.imap_unordered(evaluate, range(a, b), chunksize=4):
            if e is None: continue
            tag = 'VALID' if valid(e) else ('NEAR' if valid(e, 45) else '-')
            print(tag, e, flush=True)
