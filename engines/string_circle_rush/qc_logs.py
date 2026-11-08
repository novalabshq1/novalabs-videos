# Usage: python3 qc_logs.py SEED  -> physics log checks for the RUSH rules
import sim, sys, numpy as np
sim.PLOW_K = 10**9; sim.POSF = 0.8; sim.SPREAD = 18; sim.JIT = 0.15
from render_spec import SPEC
r = sim.run(SPEC, int(sys.argv[1]), 200, 35, check=True)
st = r['stats']; sp = r['speeds']
walls = st['wall']
ok_wall = all(b - a == 10 for (_, a, b) in walls)
dead_ok = all(len(c.anchors) == 0 for c in r['cs'] if not c.alive)
ratio = (sp[1:] / sp[:-1]).max()
print('frames', r['nframes'], 'duration', r['nframes'] / 60)
print('string bounces (PLOW_K)', sim.PLOW_K, '-> none')
print('min clearance ball vs enemy string after cuts', round(st['minclear'], 2), 'OK' if st['minclear'] >= sim.BR else 'FAIL')
print('max movement per substep px', round(st['maxstep'], 3), 'OK' if st['maxstep'] <= 3.0 else 'FAIL')
print('wall contacts', len(walls), 'all +10:', ok_wall)
print('dead balls had 0 strings:', dead_ok, [len(c.anchors) for c in r['cs']])
print('v start', round(r['v0'], 2), 'first frame', round(sp[0], 3), 'final', round(sp[-1], 1), 'x', round(sp[-1] / 200, 2))
print('max frame-to-frame increase %', round((ratio - 1) * 100, 3), 'OK' if ratio <= 1.08 else 'FAIL')
print('deaths', [round(d[0], 2) for d in r['deaths']], 't2', round(r['t2'], 2), 'duel', round(r['end_t'] - r['t2'], 2), 'winner', r['winner'])
