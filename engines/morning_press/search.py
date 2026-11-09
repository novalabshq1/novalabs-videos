"""Search seeds without rendering, in parallel.
usage: python3.13 search.py START END [HW D SLIT_W]  -> prints valid seeds as JSON lines and writes search_results.json"""
import sys, json, os
from multiprocessing import Pool
import sim

A = sys.argv
S0, S1 = int(A[1]), int(A[2])
HW = float(A[3]) if len(A) > 3 else 90.0
D = float(A[4]) if len(A) > 4 else 265.0
SW = float(A[5]) if len(A) > 5 else 30.03
ELEMENT = os.environ.get('ELEMENT', 'cheater')


def cfg():
    c = sim.default_cfg(); c['mech_kw'] = dict(HW=HW, D=D); c['slit_w'] = SW; c['slit'] = ELEMENT == 'cheater'
    return c


def one(seed):
    early = dict(max_escape=int(os.environ.get('MAXESC', '1'))) if ELEMENT == 'cheater' else None
    r = sim.run(seed, cfg(), early=early)
    e = r['events']
    row = dict(seed=seed, ok=r['ok'], why=r.get('why'), full_t=r.get('full_t'), n=r.get('n'),
               hits=len(e['hits']), empty_hits=sum(1 for h in e['hits'] if h.get('crushed', 1) == 0),
               escapes=[round(x['t'], 2) for x in e['escape']], esc_lv=[x['lv'] for x in e['escape']],
               maxov=round(e['max_overlap'], 2), levels=r.get('levels'))
    if r['ok']:
        # first hits: should start slowly (few balls) and grow
        row['n_at'] = {k: next((h['n_after'] for h in e['hits'] if h['t0'] >= k), None) for k in (5, 10, 20, 30, 40)}
        # LAST COLOUR: the lowest colour still present is held by ONE ball only, alive for a long time
        lvls = r['levels']; low = next(L for L in range(8) if lvls[L] > 0)
        row['last'] = None
        if low <= 3 and lvls[low] == 1:
            b = next(b for b in r['balls'] if b[1] == low)
            # since when is it the only ball of its colour and below?
            since = None
            for h in e['hits']:
                if 'lv' in h and sum(h['lv'][:low + 1]) == 1: since = h['tc'] if since is None else since
                elif 'lv' in h: since = None
            row['last'] = dict(id=b[0], lv=low, born=round(b[2], 2), alone_since=since and round(since, 2),
                               cool_share=round(sum(lvls[5:]) / sum(lvls), 3))
        row['hit_gaps_max'] = round(max(b['t0'] - a['t0'] for a, b in zip(e['hits'], e['hits'][1:])), 2)
    return row


def valid(row):
    if not row['ok'] or row['empty_hits']: return False
    if not (42.0 <= row['full_t'] <= 57.0): return False
    if ELEMENT == 'cheater':
        return len(row['escapes']) == 1 and 12.0 <= row['escapes'][0] <= row['full_t'] - 2.0
    if ELEMENT == 'last':
        L = row.get('last')
        return bool(L) and L['alone_since'] is not None and row['full_t'] - L['alone_since'] >= 12 and row['full_t'] - L['born'] >= 25
    return True


if __name__ == '__main__':
    with Pool(os.cpu_count()) as p:
        rows = []
        for r in p.imap_unordered(one, range(S0, S1), chunksize=1):
            rows.append(r)
            if valid(r): print(json.dumps(r), flush=True)
    good = [r for r in rows if valid(r)]
    from collections import Counter
    print('summary: valid', len(good), '/', len(rows), Counter((r['why'] or 'ok') for r in rows),
          'escapes hist', Counter(len(r['escapes']) for r in rows))
    json.dump(rows, open(os.environ.get('OUTJ', 'search_results.json'), 'w'))
