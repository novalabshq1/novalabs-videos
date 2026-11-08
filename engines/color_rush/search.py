"""Recherche de parties (sans rendu), en parallèle.

/usr/bin/python3 search.py FORMAT N SURSIS G [S0 S1]
  FORMAT = couleurs | pays ; N = nombre de balles (4 ou 5 en couleurs, 4 en pays)
  SURSIS = distance du sursis en px (bouton principal de durée) ; G = croissance de base (0,02, ou 0,01 si trop court)
Critères : durée 50-60 s (pause comprise), 1re élimination >= 5 s, duel final 10-15 s,
COULEURS : multiplicateur final >= 15. Score : sauvetages, fin serrée, changements de leader.
"""
import sys
import numpy as np
from multiprocessing import Pool
import sim

RAMP = {'couleurs': 0.30, 'pays': 0.22}


def evaluate(args):
    fmt, n, sursis, g, seed = args
    r = sim.run(seed, n, RAMP[fmt], sursis=sursis, g=g)
    if r is None or r.get('invalid'):
        return None
    times = [e[0] for e in r['elim']]
    dur = r['duration']
    duel = r['t_win'] - r['t2']
    ok = 50 <= dur <= 60 and times[0] >= 5 and 10 <= duel <= 15
    if fmt == 'couleurs':
        ok &= r['mult'] >= 15
    w = r['winner']
    lead_changes, prev, min_w = 0, None, 1e9
    for t, c in r['leader']:
        L = int(np.argmax(c))
        if prev is not None and L != prev and c[L] > 0:
            lead_changes += 1
        prev = L
        if c[w] > 0:
            min_w = min(min_w, c[w])
    end_c = r['leader'][-1][1][w] if r['leader'] else 0
    nsave = len(r['saves'])
    score = lead_changes + 4.0 * min(nsave, 2) + (3.0 if min_w <= 5 else 0) + max(0, 3 - end_c / 20)
    return dict(seed=seed, ok=bool(ok), dur=round(dur, 2), first=round(times[0], 2),
                elim=[round(x, 1) for x in times], order=[e[1] for e in r['elim']], duel=round(duel, 2),
                mult=round(r['mult'], 1), winner=w, saves=nsave, lead=lead_changes,
                min_w=int(min_w), end_c=int(end_c), score=round(score, 2))


if __name__ == '__main__':
    fmt, n, sursis, g = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
    s0 = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    s1 = int(sys.argv[6]) if len(sys.argv) > 6 else 1500
    with Pool() as p:
        res = [r for r in p.map(evaluate, [(fmt, n, sursis, g, s) for s in range(s0, s1)], chunksize=8) if r]
    good = sorted([r for r in res if r['ok']], key=lambda r: -r['score'])
    durs = np.array([r['dur'] for r in res]) if res else np.zeros(1)
    print(f'{fmt} n={n} SURSIS={sursis} G={g}: {len(res)} parties terminées < {sim.TMAX}s, '
          f'durée médiane {np.median(durs):.1f}s, valides {len(good)}')
    for r in good[:15]:
        print(r)
