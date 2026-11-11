# Usage: python3 search.py START END [GAP_DEG] -> graines valides CLONES (30-45 s, faux espoirs, aucune balle > 8 s sauf la gagnante)
import clones_sim as S, sys
S.setup(float(sys.argv[3]) if len(sys.argv) > 3 else 20.0)
if len(sys.argv) > 4: S.SPAWN_GAP = float(sys.argv[4])
for seed in range(int(sys.argv[1]), int(sys.argv[2])):
    r = S.run(seed)
    if not r['ok'] or not (30 <= r['end_t'] <= 45): continue
    lv = r['lives']; win = [l for l in lv if l[3] == 'escaped'][0]
    if max((l[2] - l[1] for l in lv if l[3] == 'dead'), default=0) > 8: continue
    near = [round(e[2]) for e in r['events'] if e[1] == 'trymin' and e[0] < 15 and e[2] < 70]
    if len(near) < 2: continue
    print(seed, 'balls', r['balls'], 'deaths', len(r['dead']), 'end', round(r['end_t'], 1), 'near', near, 'winner_flight', round(win[2] - win[1], 1), flush=True)
