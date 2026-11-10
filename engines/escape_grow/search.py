# Usage: python3 search.py START END GAP_DEG [R0] [SHRINK] -> valid seeds for ESCAPE — SHRINK
import cfg, sys
E = cfg.setup(float(sys.argv[3]), 8.0); E.T_ABORT = 45 - 1.6
if len(sys.argv) > 4: E.R0 = float(sys.argv[4])
if len(sys.argv) > 5: E.GROWF = float(sys.argv[5])
stats = {}
for seed in range(int(sys.argv[1]), int(sys.argv[2])):
    r = E.run(seed)
    if not r['ok']: stats[r['reason']] = stats.get(r['reason'], 0) + 1; continue
    sp = [e[0] for e in r['events'] if e[1] == 'spawn']
    durs = [round(b - a, 1) for a, b in zip(sp, sp[1:] + [r['escaped_t']])]
    key = 'ok_dur' if not (30 <= r['end_t'] <= 45) else ('ok_tries' if r['tries'] < 9 or max(durs[:-1]) > 8 else None)
    near = [round(e[2]) for e in r['events'] if e[1] == 'trymin' and e[0] < 15 and e[2] < 70]
    if key is None and len(near) < 2: key = 'ok_near'
    if key: stats[key] = stats.get(key, 0) + 1; continue
    g = [e[2] for e in r['events'] if e[1] == 'grow' and e[0] < r['escaped_t']]
    if len(r['bursts']) < 1: stats['no_burst'] = stats.get('no_burst', 0) + 1; continue
    print(seed, 'bursts', len(r['bursts']), 'maxr', round(max(g), 1), 'esc_r', round(g[-1] if g else 26, 1), r['tries'], round(r['end_t'], 1), 'near', near, 'last_try', durs[-1], 'durs', durs, flush=True)
print(stats)
