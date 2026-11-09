# Usage: python3 search.py START END GAP_DEG [JIT_DEG] -> valid seeds for the evening ESCAPE format
import cfg, sys
E = cfg.setup(float(sys.argv[3]), float(sys.argv[4]) if len(sys.argv) > 4 else 8.0)
for seed in range(int(sys.argv[1]), int(sys.argv[2])):
    r = E.run(seed)
    if not r['ok']: continue
    if not (30 <= r['end_t'] <= 45): continue
    sp = [e[0] for e in r['events'] if e[1] == 'spawn']
    durs = [round(b - a, 1) for a, b in zip(sp, sp[1:] + [r['escaped_t']])]
    if r['tries'] < 9 or max(durs[:-1]) > 8: continue
    near = [round(e[2]) for e in r['events'] if e[1] == 'trymin' and e[0] < 15 and e[2] < 70]
    if len(near) < 2: continue
    print(seed, r['tries'], round(r['end_t'], 1), 'near', near, 'last_try', durs[-1], 'durs', durs, flush=True)
