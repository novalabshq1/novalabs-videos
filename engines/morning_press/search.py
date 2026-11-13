"""Recherche de parties (sans rendu, en parallèle).

python3 search.py MECH TWIST SEED0 SEED1 [out.jsonl]
  MECH  : clé de sim.MECHS (press, press_side, ...)
  TWIST : survivor | tricheuse | lastcolor | rescapee | any
  --extra '{"lone_max": 4}' : réglages ajoutés (ex. LA DERNIÈRE COULEUR version « une seule balle chaude »)
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
    if twist == 'rescapee':
        return dict(rescue=3.0, rescue_v=250.0, rescue_nmax=6)
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
        # une seule balle de couleur <= lone_max (par défaut tout sauf cyan ; lone_max=4 : une seule balle rose ou plus
        # chaude au milieu des violettes / bleues / cyan), seule de sa couleur depuis au moins 6 s
        cc = r['col_count']
        lm = int(over.get('lone_max', 6))
        tw = r['t_full'] > 0 and sum(cc[:lm + 1]) == 1 and r['t_full'] - r['t_multi'] >= 6.0
    elif TWIST == 'rescapee':
        # une seule balle chassée des mâchoires (et elle s'en sort), bien visible : entre 8 s et 5 s avant la fin
        tw = r['rescue_kicks'] == 1 and r['rescues'] == 1 and r['rescue_fail'] == 0 and 8 < r['rescue_t'] < r['t_full'] - 5
    else:
        tw = True
    r.pop('params')
    r['twist_ok'] = bool(tw)
    r['ok'] = bool(ok and tw)
    r['over'] = over
    return r


if __name__ == '__main__':
    MECH, TWIST = sys.argv[1], sys.argv[2]
    if '--extra' in sys.argv:
        EXTRA = json.loads(sys.argv[sys.argv.index('--extra') + 1])
    s0, s1 = int(sys.argv[3]), int(sys.argv[4])
    out = sys.argv[5] if len(sys.argv) > 5 else 'search_%s_%s.jsonl' % (MECH, TWIST)
    with Pool(os.cpu_count()) as p, open(out, 'w') as fo:
        n = 0
        for r in p.imap_unordered(job, range(s0, s1), chunksize=4):
            fo.write(json.dumps(r) + '\n')
            if r['ok']:
                n += 1
                print('OK seed %d full %.2f hits %d green_cap %s cols %s lone %d' % (r['seed'], r['t_full'], r['hits'], r['green_cap'], r['col_count'], r['lone_col']), flush=True)
    print('valid:', n)
