# Usage: python3 search.py START END [GAP0_DEG] [STEP_DEG] -> valid seeds for ESCAPE - WIDER GAP
import esc_sim as E, sys
g0 = float(sys.argv[3]) if len(sys.argv) > 3 else 14.0
st = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
for seed in range(int(sys.argv[1]), int(sys.argv[2])):
    E.setup(g0, st)
    r = E.run(seed)
    if not r['ok']: continue
    if not (40 <= r['end_t'] <= 58): continue
    sp = [e[0] for e in r['events'] if e[1] == 'spawn']
    durs = [round(b - a, 1) for a, b in zip(sp, sp[1:] + [r['escaped_t']])]
    if r['tries'] < 10 or max(durs[:-1]) > 8: continue
    if r["escaped_t"] - sp[-1] < float(sys.argv[5] if len(sys.argv) > 5 else 0): continue
    near = [round(e[2]) for e in r['events'] if e[1] == 'trymin' and e[0] < 15 and e[2] < 70]
    if len(near) < 2: continue
    print(seed, r['tries'], round(r['end_t'], 1), 'gapEnd', round(E.GAP*57.2958, 1), 'near', near, 'last_try', durs[-1], flush=True)
