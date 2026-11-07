# Usage: python3 search.py START END [GAP_DEG] [SPREAD] -> valid seeds for ESCAPE (gap at the bottom, fixed launch)
import esc_sim as E, math, sys
GAPD = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
E.RO=490.0; E.RING_T=16.0; E.RI=E.RO-E.RING_T; E.BR=26.0
E.MAX_TRIES=45; E.ROT=0; E.NSPK=88; E.SPK_HALF=math.pi/88; E.SPK_H=62; E.LEAN=1.0
E.G=400; E.V0=360; E.GAP=math.radians(GAPD); E.GAP_AT=math.radians(90); E.SPIKES=E.spike_angles()
if len(sys.argv) > 4: E.SPREAD_DEG = float(sys.argv[4])
stats = {}
for seed in range(int(sys.argv[1]), int(sys.argv[2])):
    r = E.run(seed)
    if not r['ok']: stats[r['reason']] = stats.get(r['reason'], 0) + 1; continue
    sp = [e[0] for e in r['events'] if e[1] == 'spawn']
    durs = [round(b - a, 1) for a, b in zip(sp, sp[1:] + [r['escaped_t']])]
    key = 'tries<9' if r['tries'] < 9 else ('dur' if not 30 <= r['end_t'] <= 45 else ('long' if max(durs[:-1]) > 8 else None))
    if key: stats[key] = stats.get(key, 0) + 1; continue
    near = [round(e[2]) for e in r['events'] if e[1] == 'trymin' and e[0] < 15 and e[2] < 70]
    if len(near) < 2: stats['near'] = stats.get('near', 0) + 1; continue
    print(seed, r['tries'], round(r['end_t'], 1), 'near', near, 'last_try', durs[-1], flush=True)
print(stats, file=sys.stderr)
