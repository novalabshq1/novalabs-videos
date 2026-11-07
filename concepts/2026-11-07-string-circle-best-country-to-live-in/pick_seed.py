# headless seed filter for the daily prompt rules (uses the validated sim, same settings as search.py)
import sys, os; sys.path.insert(0, os.getcwd())
import sim, numpy as np
from multiprocessing import Pool
sim.PLOW_K = 10**9; sim.MAX_T = 62; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC
N0 = int(sys.argv[3]) if len(sys.argv) > 3 else 35
def ev(seed):
    r = sim.run(SPEC, seed, 200, N0)
    if r['end_t'] is None: return None
    tot = r['end_t'] + 1.5
    if not 30 <= tot <= 45: return None
    d = [x[0] for x in r['deaths']]
    if d[0] < 8 or (len(d) > 1 and d[1] - d[0] < 5) or r['end_t'] - d[-2] > 15: return None
    c = r['counts']; FPS = 60
    leaders = []
    for row in c:
        if (row == row.max()).sum() == 1:
            ld = int(row.argmax())
            if not leaders or leaders[-1] != ld: leaders.append(ld)
    if len(leaders) - 1 < 2: return None
    names = [s[0] for s in SPEC]; w = names.index(r['winner'])
    f8 = int((r['end_t'] - 8) * FPS); row = c[f8]
    others = [row[i] for i in range(len(row)) if i != w and row[i] > 0]
    if not others or row[w] > 1.3 * max(others): return None
    mn = [int(c[:, i][c[:, i] > 0].min()) for i in range(c.shape[1])]
    alive8 = int((c[8 * FPS] > 0).sum())
    return (seed, round(tot, 1), [round(x, 1) for x in d], r['winner'], mn[w], mn, len(leaders) - 1, alive8)
if __name__ == '__main__':
    with Pool(os.cpu_count()) as p:
        for x in p.imap(ev, range(int(sys.argv[1]), int(sys.argv[2]))):
            if x: print(*x, flush=True)
