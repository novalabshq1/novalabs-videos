"""Recherche de parties (sans rendu), en parallèle.

python3 search.py FORMAT N FLAT G [S0 S1]
  FORMAT = couleurs | pays ; N = nombre de balles (4 ou 5 en couleurs, 4 en pays)
Affiche les graines valides, triées par score.
"""
import sys
import numpy as np
from multiprocessing import Pool
import sim

RAMP = {'couleurs': 0.45, 'pays': 0.22}
DUEL = {'couleurs': (8, 16), 'pays': (8, 20)}


def evaluate(args):
    fmt, n, flat, g, seed = args
    r = sim.run(seed, n, RAMP[fmt], flat=flat, g=g)
    if r is None or r.get('invalid'):
        return None
    times = [e[0] for e in r['elim']]
    dur = r['duration']
    ok = 45 <= dur <= 69
    ok &= times[0] >= 6
    pre = [0.0] + times[:n - 2]           # éliminations avant le duel final
    gaps = np.diff(pre)
    ok &= bool((gaps <= 18).all())
    duel = r['t_win'] - r['t2']
    lo, hi = DUEL[fmt]
    ok &= lo <= duel <= hi
    if fmt == 'couleurs':
        ok &= r['mult'] >= 15
    # score : changements de leader + fin serrée + retournement du futur vainqueur
    w = r['winner']
    lead_changes = 0
    prev = None
    worst_rank = 0
    min_w = 1e9
    for t, c in r['leader']:
        alive_c = c.copy()
        L = int(np.argmax(alive_c))
        if prev is not None and L != prev and c[L] > 0:
            lead_changes += 1
        prev = L
        if c[w] > 0:
            worst_rank = max(worst_rank, int((c > c[w]).sum()))
            min_w = min(min_w, c[w])
    # fin serrée : nombre de fils du gagnant à la fin (petit = serré)
    end_c = r['leader'][-1][1][w] if r['leader'] else 0
    score = lead_changes + 2.0 * worst_rank + (3.0 if min_w <= 5 else 0) + max(0, 3 - end_c / 20)
    if fmt == 'couleurs':
        score += 2.0 if 15 <= r['mult'] <= 25 else 0
    return dict(seed=seed, ok=bool(ok), dur=round(dur, 2), first=round(times[0], 2),
                elim=[round(x, 1) for x in times], duel=round(duel, 2), mult=round(r['mult'], 1),
                winner=w, final=[e[1] for e in r['elim']][-1], lead=lead_changes,
                worst_rank=worst_rank, min_w=int(min_w), score=round(score, 2))


if __name__ == '__main__':
    fmt, n, flat, g = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
    s0 = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    s1 = int(sys.argv[6]) if len(sys.argv) > 6 else 1500
    with Pool() as p:
        res = [r for r in p.map(evaluate, [(fmt, n, flat, g, s) for s in range(s0, s1)], chunksize=8) if r]
    good = sorted([r for r in res if r['ok']], key=lambda r: -r['score'])
    durs = np.array([r['dur'] for r in res]) if res else np.zeros(1)
    print(f'{fmt} n={n} FLAT={flat} G={g}: {len(res)} parties terminées < {sim.TMAX}s, '
          f'durée médiane {np.median(durs):.1f}s, valides {len(good)}')
    for r in good[:25]:
        print(r)
