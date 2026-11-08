"""Seed / speed search without rendering. python3 search.py > search.txt"""
import os, sys, itertools, subprocess, json
from concurrent.futures import ProcessPoolExecutor
def run(args):
    om, im, seed = args
    env = dict(os.environ, OMEGA=str(om), IMMUNE=str(im))
    code = f"""
import sim, json, numpy as np
r = sim.main({seed}, None, store=False)
pt = sim.palier_times(r['splits'])
st = r['splits'][:, 0].tolist()
print(json.dumps(dict(pt={{int(k): float(v) for k, v in pt.items()}}, boom=r['t_boom'], end=r['t_end'], viol=r['wall_viol'], st=st)))
"""
    o = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True).stdout
    d = json.loads(o); d.update(om=om, im=im, seed=seed); return d
def score(d):
    pt = {int(k): v for k, v in d['pt'].items()}; d['pt'] = pt; b = d['boom']
    if b is None or d['viol'] or 3 not in pt: return 1e9 + (b or 99)
    st = d['st']; gaps = [st[i+1]-st[i] for i in range(len(st)-1) if st[i] > 1]
    ks = sorted(pt); tt = [pt[k] for k in ks] + [b]
    diffs = [tt[i+1]-tt[i] for i in range(len(tt)-1)]
    import statistics as S
    s = S.pstdev(diffs[1:]) * 2 + max(gaps) * 2
    s += 10 * max(0, st[0] - 1.5) + 5 * max(0, pt[3] - 8) + 5 * max(0, 30 - b) + 5 * max(0, d['end'] - 43.5)
    return s
if __name__ == '__main__':
    oms = [float(x) for x in os.environ.get('OMS', '1.2,1.5,1.8,2.1').split(',')]
    ims = [float(x) for x in os.environ.get('IMS', '1.8,2.2,2.6,3.0').split(',')]
    seeds = range(1, int(os.environ.get('NS', '6')) + 1)
    with ProcessPoolExecutor(4) as ex:
        res = list(ex.map(run, itertools.product(oms, ims, seeds)))
    res.sort(key=score)
    for d in res[:25]:
        print(round(score(d), 2), d['om'], d['im'], d['seed'], 'first', round(d['st'][0], 2) if d['st'] else None,
              {k: round(v, 1) for k, v in d['pt'].items()}, 'boom', d['boom'] and round(d['boom'], 1), 'end', round(d['end'], 1), 'viol', d['viol'])
