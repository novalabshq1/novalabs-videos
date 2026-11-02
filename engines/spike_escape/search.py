# Usage: python3 search.py START END -> valid seeds (validated settings, with early near-misses)
import esc_sim as E, math, sys
E.RO=490.0; E.RING_T=16.0; E.RI=E.RO-E.RING_T; E.BR=26.0
E.MAX_TRIES=45; E.ROT=0; E.NSPK=88; E.SPK_HALF=math.pi/88; E.SPK_H=62; E.LEAN=1.0
E.G=400; E.V0=360; E.GAP=math.radians(20); E.GAP_AT=math.radians(150); E.SPIKES=E.spike_angles()
for seed in range(int(sys.argv[1]), int(sys.argv[2])):
    r = E.run(seed)
    if not (r['ok'] and 42 <= r['end_t'] <= 58): continue
    sp = [e[0] for e in r['events'] if e[1] == 'spawn']
    durs = [round(b - a, 1) for a, b in zip(sp, sp[1:] + [r['escaped_t']])]
    if r['tries'] < 13 or max(durs[:-1]) > 8: continue
    near = [round(e[2]) for e in r['events'] if e[1] == 'trymin' and e[0] < 15 and e[2] < 70]
    if len(near) < 2: continue
    print(seed, r['tries'], round(r['end_t'], 1), 'near', near, 'last_try', durs[-1], flush=True)
