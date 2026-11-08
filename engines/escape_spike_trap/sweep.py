# python3 sweep.py GAP TS_H TS_HALF_DEG START END -> summary of valid seeds (SPIKE TRAP)
import esc_sim as E, math, sys
from multiprocessing import Pool
GAPD, TSH, TSA, A, B = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
def setup():
    E.RO=490.0; E.RING_T=16.0; E.RI=E.RO-E.RING_T; E.BR=26.0; E.MAX_TRIES=22; E.ROT=0; E.NSPK=88
    E.SPK_HALF=math.pi/88; E.SPK_H=62; E.LEAN=1.0; E.G=400; E.V0=360; E.GAP=math.radians(GAPD)
    E.GAP_AT=math.radians(90); E.SPIKES=E.spike_angles(); E.TS_H=TSH; E.TS_HALF=math.radians(TSA)
def one(seed):
    setup(); r = E.run(seed)
    if not r['ok']: return (seed, r['reason'])
    sp = [e[0] for e in r['events'] if e[1] == 'spawn']
    durs = [b - a for a, b in zip(sp, sp[1:] + [r['escaped_t']])]
    if r['tries'] < 9: return (seed, 'tries<9')
    if not 30 <= r['end_t'] <= 45: return (seed, 'dur')
    if max(durs[:-1]) > 8: return (seed, 'long')
    if min(durs[:-1]) < 0.6: return (seed, 'instadeath')
    near = [round(e[2]) for e in r['events'] if e[1] == 'trymin' and e[0] < 15 and e[2] < 70]
    if len(near) < 2: return (seed, 'near')
    tk = sum(1 for e in r['events'] if e[1] == 'trapkill')
    return (seed, 'OK', r['tries'], round(r['end_t'], 1), near, round(durs[-1], 1), tk)
if __name__ == '__main__':
    with Pool(4) as p: res = p.map(one, range(A, B), chunksize=4)
    st = {}
    for x in res:
        st[x[1]] = st.get(x[1], 0) + 1
        if x[1] == 'OK': print(*x, flush=True)
    print(GAPD, TSH, TSA, st, flush=True)
