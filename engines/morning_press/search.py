"""Recherche de parties (sans rendu, en parallèle).

python3 search.py MECH TWIST SEED0 SEED1 [out.jsonl]
  MECH  : clé de sim.MECHS (press, press_side, ...)
  TWIST : survivor | tricheuse | lastcolor | any
Critères communs : cercle plein entre 42 et 57 s, aucun coup dans le vide, aucune division ratée,
premier coup avant 3 s, montée progressive.
"""
import json
import math
import os
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import simulate  # noqa: E402

MECH, TWIST = 'press', 'survivor'
EXTRA = {}


def twist_params(twist, seed):
    if twist == 'tricheuse':
        # fente à un endroit au hasard (hors bas de l'écran), à peine plus large qu'une balle de 15 px
        import random
        rng = random.Random(seed * 7919)
        axis = 1 if MECH == 'press_side' else 0
        while True:
            a = rng.uniform(-math.pi, math.pi)
            # pas dans la bande droite de 140 px (x > 940) et loin des tiges du mécanisme (>= 20°)
            if 540 + 450 * math.cos(a) > 900:
                continue
            rod = [0.0, math.pi] if axis == 1 else [math.pi / 2, -math.pi / 2]
            if min(abs(math.remainder(a - r, 2 * math.pi)) for r in rod) < math.radians(20):
                continue
            return dict(slit_ang=a, slit_w=34.0)
    return {}


def job(seed):
    over = dict(EXTRA)
    over.update(twist_params(TWIST, seed))
    if TWIST == 'survivor':
        over['stop_no_green'] = 1
    r = simulate(seed, MECH, **over)
    ok = 42.0 <= r['t_full'] <= 57.0 and r['max_overlap'] <= 2.5 and r['max_wall_pen'] <= 0.5 and r['empty_hits'] == 0 and r['bad_split'] == 0 and 0 < r['first_hit'] < 3.0
    tw = False
    if TWIST == 'survivor':
        tw = r['t_full'] > 0 and min(r['green_cap']) < 0
    elif TWIST == 'tricheuse':
        tw = r['escapes'] == 1 and 15 < r['escape_t'] < r['t_full'] - 3
    elif TWIST == 'lastcolor':
        cc = r['col_count']
        tw = r['t_full'] > 0 and sum(cc[:7]) == 1
    else:
        tw = True
    r.pop('params')
    r['twist_ok'] = bool(tw)
    r['ok'] = bool(ok and tw)
    r['over'] = over
    return r


if __name__ == '__main__':
    MECH, TWIST = sys.argv[1], sys.argv[2]
    s0, s1 = int(sys.argv[3]), int(sys.argv[4])
    out = sys.argv[5] if len(sys.argv) > 5 else 'search_%s_%s.jsonl' % (MECH, TWIST)
    with Pool(os.cpu_count()) as p, open(out, 'w') as fo:
        n = 0
        for r in p.imap_unordered(job, range(s0, s1), chunksize=4):
            fo.write(json.dumps(r) + '\n')
            if r['ok']:
                n += 1
                print('OK seed %d full %.2f hits %d green_cap %s' % (r['seed'], r['t_full'], r['hits'], r['green_cap']), flush=True)
    print('valid:', n)
