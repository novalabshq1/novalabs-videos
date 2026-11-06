# Physics QC from sim_log.json: no ball through a spike / grey ball / wall, each death widens the gap by STEP, escape through the opening.
import json, math, esc_sim as E
L = json.load(open('sim_log.json')); E.setup(L['gap0'], L['step'])
bad = []
gaps = L['gaps']
for i in range(1, len(gaps)):
    if abs(gaps[i][1] - min(60, gaps[i - 1][1] + L['step'])) > 1e-6: bad.append(('gap step', gaps[i]))
if len(gaps) - 1 != len(L['deaths']): bad.append(('deaths vs widenings', len(gaps) - 1, len(L['deaths'])))
death_t = [d[0] for d in L['deaths']]
for t, x, y, st, gdeg, dead in L['traj']:
    if st != 'alive': continue
    if any(abs(t - td) < 0.02 for td in death_t): continue
    E.GAP = math.radians(gdeg); E.SPIKES = E.spike_angles()
    r = math.hypot(x - E.CX, y - E.CY); ang = math.atan2(y - E.CY, x - E.CX)
    if r > E.RI - E.BR + 0.5 and not E.in_gap(ang, E.GAP_AT) and r < E.RO: bad.append(('wall', t, r))
    for dx, dy in dead:
        if math.hypot(x - dx, y - dy) < 2 * E.BR - 0.5: bad.append(('through grey', t))
    if r > E.RI - E.SPK_H - E.BR - 2:
        for tri in E.spike_tris(E.GAP_AT):
            for k in range(3):
                d, _ = E.seg_dist((x, y), tri[k], tri[(k + 1) % 3])
                if d < E.BR - 0.5: bad.append(('through spike', t, d))
# every death is on a spike (distance to a spike edge ~ BR) of the ring as it was
for (td, x, y), (_, gprev) in zip(L['deaths'], gaps[:-1]):
    E.GAP = math.radians(gprev); E.SPIKES = E.spike_angles()
    dmin = min(E.seg_dist((x, y), tri[k], tri[(k + 1) % 3])[0] for tri in E.spike_tris(E.GAP_AT) for k in range(3))
    if dmin > E.BR + 0.5: bad.append(('death not on spike', td, dmin))
# escape: last alive position before leaving is inside the opening angle
esc = [f for f in L['traj'] if f[3] == 'escaped'][0]
gx = math.degrees(math.atan2(esc[2] - E.CY, esc[1] - E.CX))
if abs(gx - 90) > esc[4] / 2: bad.append(('escape outside gap', gx))
spw = L['spawns']; durs = [b - a for a, b in zip(spw, spw[1:] + [L['escaped_t']])]
print('tries', L['tries'], 'deaths', len(L['deaths']), 'gap', gaps[0][1], '->', gaps[-1][1], 'escape angle', round(gx, 1),
      'max try (non-last)', round(max(durs[:-1]), 2), 'last try', round(durs[-1], 2), 'end', round(L['end_t'], 2))
print('PROBLEMS:', bad[:10], len(bad))
