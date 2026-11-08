"""COLOR RUSH — rendu 1080x1920, 60 fps, aucun texte.

python3 render.py SPEC.json OUT_noaudio.mkv
SPEC.json : {"seed":..,"n":..,"ramp":..,"flat":..,"g":..,
             "teams":[{"rgb":[r,g,b], "flag":null|"nom"}, ...]}   (index = balle de la simulation)
Écrit aussi OUT.events.json (événements pour audio.py et le contrôle qualité).
Les drapeaux (format PAYS) se dessinent dans flags.py : flags.draw(ctx, nom, x, y, r).
"""
import ctypes as C
import json
import math
import os
import pickle
import random
import subprocess
import sys
from multiprocessing import Process

import numpy as np

import cr
import sim

W, H = 1080, 1920
CX, CY = 540.0, 1075.0
NPROC = os.cpu_count() or 4


def new_ctx():
    surf = cr.surface_create(0, W, H)
    ctx = cr.create(surf)
    return surf, ctx


def make_particles(seed, deaths):
    parts = {}
    for (t, b, x, y) in deaths:
        rr = random.Random(seed * 1000 + b)
        ps = []
        for i in range(26):
            a = rr.uniform(0, 2 * math.pi)
            sp = rr.uniform(120, 520)
            ps.append((a, sp, rr.uniform(2.5, 6.0)))
        parts[b] = (t, x, y, ps)
    return parts


def particle_positions(x, y, ps, age):
    """Particules freinées (décroissance exp) et confinées dans le cercle (réflexion)."""
    out = []
    k = 4.0
    for a, sp, sz in ps:
        dist = sp / k * (1 - math.exp(-k * age))
        px, py = x + math.cos(a) * dist, y + math.sin(a) * dist
        r = math.hypot(px, py)
        lim = sim.R - 6
        if r > lim:   # réflexion sur le bord
            over = r - lim
            px, py = px / r * (lim - over), py / r * (lim - over)
            if math.hypot(px, py) > lim:
                px, py = px / math.hypot(px, py) * lim, py / math.hypot(px, py) * lim
        out.append((px, py, sz))
    return out


def draw_frame(ctx, fi, D, spec, flags_mod):
    fr = D['frames'][fi]
    t = fr['t']
    teams = spec['teams']
    cols = [np.array(tm['rgb']) / 255.0 for tm in teams]
    n = len(teams)
    cr.set_operator(ctx, cr.OP_OVER)
    cr.set_rgb(ctx, 0, 0, 0)
    cr.paint(ctx)
    pos = fr['pos']
    # ---- fils (additif)
    cr.set_operator(ctx, cr.OP_ADD)
    cr.set_line_width(ctx, 1.0)
    ax = CX + sim.R * np.cos(fr['ang'])
    ay = CY + sim.R * np.sin(fr['ang'])
    for b in range(n):
        m = np.nonzero(fr['own'] == b)[0]
        if not len(m):
            continue
        c = cols[b]
        cr.set_rgba(ctx, c[0], c[1], c[2], 0.8)
        bx, by = CX + pos[b, 0], CY + pos[b, 1]
        for q in m:
            cr.move_to(ctx, bx, by)
            cr.line_to(ctx, ax[q], ay[q])
        cr.stroke(ctx)
    # ---- fils qui cassent : rétraction droite vers l'ancrage en 0,15 s
    for (tb, o, ang, ox, oy) in D['breaks_by_frame'].get(fi, []):
        k = (t - tb) / 0.15
        if k < 0 or k >= 1:
            continue
        c = cols[o]
        Ax, Ay = sim.R * math.cos(ang), sim.R * math.sin(ang)
        px, py = ox + (Ax - ox) * k, oy + (Ay - oy) * k
        cr.set_rgba(ctx, c[0], c[1], c[2], 0.8 * (1 - k))
        cr.move_to(ctx, CX + px, CY + py)
        cr.line_to(ctx, CX + Ax, CY + Ay)
        cr.stroke(ctx)
    cr.set_operator(ctx, cr.OP_OVER)
    # ---- traînées (vrai chemin des sous-pas sur les ~4 dernières images)
    v = fr['v']
    ta = sim.smooth((v - 320) / 700.0)
    if ta > 0:
        cr.set_line_cap(ctx, 1)
        for b in range(n):
            if not fr['alive'][b]:
                continue
            pts = [D['frames'][j]['sub'][b] for j in range(max(0, fi - 3), fi + 1)]
            pts = [p for p in pts if len(p)]
            if not pts:
                continue
            P = np.concatenate(pts)
            P = np.vstack([P, pos[b][None, :]])
            L = len(P)
            if L < 2:
                continue
            step = max(1, L // 60)
            idx = list(range(0, L, step))
            if idx[-1] != L - 1:
                idx.append(L - 1)
            c = cols[b]
            for s in range(len(idx) - 1):
                u = (s + 1) / (len(idx) - 1)        # 0 = arrière, 1 = tête
                cr.set_line_width(ctx, 2 + 50 * u ** 1.5)
                a = ta * 0.75 * u ** 2
                cr.set_rgba(ctx, c[0] * (0.35 + 0.65 * u), c[1] * (0.35 + 0.65 * u),
                                   c[2] * (0.35 + 0.65 * u), a)
                p0, p1 = P[idx[s]], P[idx[s + 1]]
                cr.move_to(ctx, CX + p0[0], CY + p0[1])
                cr.line_to(ctx, CX + p1[0], CY + p1[1])
                cr.stroke(ctx)
    # ---- particules de mort (0,7 s)
    for b, (td, x, y, ps) in D['parts'].items():
        age = t - td
        if 0 <= age < 0.7:
            c = cols[b]
            al = (1 - age / 0.7) ** 1.3
            for (px, py, sz) in particle_positions(x, y, ps, age):
                cr.set_rgba(ctx, c[0], c[1], c[2], al)
                cr.new_path(ctx)
                cr.arc(ctx, CX + px, CY + py, sz * (1 - 0.5 * age / 0.7), 0, 2 * math.pi)
                cr.fill(ctx)
    # ---- balles : glow doux, disque (couleur ou drapeau), contour blanc 2 px
    for b in range(n):
        if not fr['alive'][b]:
            continue
        x, y = CX + pos[b, 0], CY + pos[b, 1]
        c = cols[b]
        pat = cr.pattern_radial(x, y, sim.BR - 4, x, y, sim.BR + 14)
        cr.add_stop(pat, 0.0, c[0], c[1], c[2], 0.45)
        cr.add_stop(pat, 0.45, c[0], c[1], c[2], 0.18)
        cr.add_stop(pat, 1.0, c[0], c[1], c[2], 0.0)
        cr.set_source(ctx, pat)
        cr.new_path(ctx)
        cr.arc(ctx, x, y, sim.BR + 14, 0, 2 * math.pi)
        cr.fill(ctx)
        cr.pattern_destroy(pat)
        flag = teams[b].get('flag')
        if flag and flags_mod is not None:
            flags_mod.draw(ctx, flag, x, y, sim.BR)
        else:
            cr.set_rgb(ctx, c[0], c[1], c[2])
            cr.new_path(ctx)
            cr.arc(ctx, x, y, sim.BR, 0, 2 * math.pi)
            cr.fill(ctx)
        cr.set_rgb(ctx, 1, 1, 1)
        cr.set_line_width(ctx, 2.0)
        cr.new_path(ctx)
        cr.arc(ctx, x, y, sim.BR - 1, 0, 2 * math.pi)
        cr.stroke(ctx)
    # ---- cercle blanc 3 px, centre (540,1075), diamètre 900
    cr.set_rgb(ctx, 1, 1, 1)
    cr.set_line_width(ctx, 3.0)
    cr.new_path(ctx)
    cr.arc(ctx, CX, CY, sim.R, 0, 2 * math.pi)
    cr.stroke(ctx)


def worker(k, f0, f1, dpath, spec, out):
    with open(dpath, 'rb') as fh:
        D = pickle.load(fh)
    flags_mod = None
    if any(tm.get('flag') for tm in spec['teams']):
        import flags as flags_mod
    surf, ctx = new_ctx()
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra',
                           '-s', f'{W}x{H}', '-r', '60', '-i', '-', '-c:v', 'ffv1', '-level', '3',
                           '-pix_fmt', 'yuv444p', out], stdin=subprocess.PIPE)
    stride = cr.get_stride(surf)
    for fi in range(f0, f1):
        draw_frame(ctx, fi, D, spec, flags_mod)
        cr.flush(surf)
        ff.stdin.write(C.string_at(cr.get_data(surf), stride * H))
    ff.stdin.close()
    ff.wait()


def prepare(spec):
    r = sim.run(spec['seed'], spec['n'], spec['ramp'], flat=spec['flat'], g=spec['g'],
                record=True, qc=True)
    frames = r['frames']
    nfr = len(frames)
    bbf = {}
    for br in r['breaks']:
        f0 = int(math.ceil(br[0] * 60 - 1e-6))
        for fi in range(f0, min(nfr, f0 + 10)):
            bbf.setdefault(fi, []).append(br)
    deaths = [(e[0], e[4], e[2], e[3]) for e in r['events'] if e[1] == 'death']
    D = dict(frames=frames, breaks_by_frame=bbf, parts=make_particles(spec['seed'], deaths))
    return r, D


if __name__ == '__main__':
    spec = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    r, D = prepare(spec)
    base = os.path.splitext(out)[0]
    dpath = base + '.frames.pkl'
    with open(dpath, 'wb') as fh:
        pickle.dump(D, fh)
    nfr = len(D['frames'])
    ev = dict(duration=nfr / 60.0, nframes=nfr, events=[list(e[:2]) + [float(e[2]), float(e[3]), e[4]]
                                                         for e in r['events']],
              elim=r['elim'], t2=r['t2'], t_win=r['t_win'], winner=r['winner'], mult=r['mult'],
              qc=r['qc'], frame_times=[f['t'] for f in D['frames']])
    json.dump(ev, open(base + '.events.json', 'w'), default=float)
    print('frames', nfr, 'duration', nfr / 60, 'winner', r['winner'], 'mult', r['mult'])
    bounds = np.linspace(0, nfr, NPROC + 1).astype(int)
    parts = [f'{base}.part{k}.mkv' for k in range(NPROC)]
    ps = [Process(target=worker, args=(k, bounds[k], bounds[k + 1], dpath, spec, parts[k]))
          for k in range(NPROC)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
    with open(base + '.concat.txt', 'w') as fh:
        for p in parts:
            fh.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i',
                    base + '.concat.txt', '-c', 'copy', out], check=True)
    for p in parts:
        os.remove(p)
    os.remove(base + '.concat.txt')
    print('ok', out)
