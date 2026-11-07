"""seed search: python3 search.py PHIMAX seed0 seed1"""
import sys, os, io, contextlib, numpy as np
os.environ["PHIMAX"] = sys.argv[1]
import sim
for seed in range(int(sys.argv[2]), int(sys.argv[3])):
    f = f"/tmp/claude-0/sc/q_{sys.argv[1]}_{seed}.npz"
    with contextlib.redirect_stdout(io.StringIO()):
        sim.main(seed, f)
    d = np.load(f); off = d['off']; ns = np.diff(off)
    ex = float(d['exploded'])
    ev_t, ev_k = d['ev_t'], d['ev_k']
    ct = np.sort(ev_t[ev_k == 'cut'])
    gaps = np.diff(np.concatenate([[0], ct[ct < ex - 3] if ex > 0 else ct]))
    print(sys.argv[1], seed, 'explode', round(ex, 1), 'first cut', round(ct[0], 2) if len(ct) else None,
          'max gap', round(gaps.max(), 1) if len(gaps) else None, 'n@10/20/30', ns[min(600, len(ns)-1)], ns[min(1200, len(ns)-1)], ns[min(1800, len(ns)-1)], flush=True)
    os.remove(f)
