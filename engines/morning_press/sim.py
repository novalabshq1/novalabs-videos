"""morning_press : simulation sans rendu (wrapper ctypes du coeur C sim.c).

Usage :
    from sim import simulate, load_record
    res = simulate(seed, mech='press')                  # résumé seulement (rapide)
    res = simulate(seed, rec='rec.bin', events='ev.bin') # + enregistrement 60 fps pour render/audio
"""
import ctypes as C
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'sim.c')
LIB = os.path.join(HERE, 'libsim.so')

COLORS = ['#3DDC5A', '#FFD60A', '#FF8A00', '#FF3B30', '#FF4FA3', '#A44BFF', '#2F7BFF', '#19E3FF']
CX, CY, R = 540.0, 1075.0, 450.0


class Params(C.Structure):
    _fields_ = [(n, C.c_double) for n in 'R cx cy speed dt'.split()] + \
        [('mech', C.c_int), ('axis', C.c_int)] + \
        [(n, C.c_double) for n in 'W H g_open rod_w t_close t_hold t_open t_pause fill_target tmax t_end_hold r0 rmin shrink'.split()] + \
        [('stop_no_green', C.c_int), ('jitter', C.c_double), ('npos_iter', C.c_int),
         ('slit_ang', C.c_double), ('slit_w', C.c_double), ('rescue', C.c_double), ('rescue_v', C.c_double), ('rescue_nmax', C.c_int), ('lone_max', C.c_double)]


class Result(C.Structure):
    _fields_ = [('t_full', C.c_double), ('t_end', C.c_double), ('hits', C.c_int), ('empty_hits', C.c_int),
                ('nballs', C.c_int), ('crushed_total', C.c_int), ('green_cap', C.c_double * 2),
                ('col_count', C.c_int * 8), ('first_hit', C.c_double), ('max_overlap', C.c_double),
                ('max_wall_pen', C.c_double), ('bad_split', C.c_int), ('escapes', C.c_int),
                ('escape_t', C.c_double), ('escape_col', C.c_int), ('fill_at_end', C.c_double),
                ('t_multi', C.c_double), ('lone_col', C.c_int), ('lone_id', C.c_int),
                ('rescues', C.c_int), ('rescue_t', C.c_double), ('rescue_f', C.c_double),
                ('rescue_col', C.c_int), ('rescue_id', C.c_int), ('rescue_hit_crushed', C.c_int),
                ('rescue_kicks', C.c_int), ('rescue_fail', C.c_int)]


# Mécanismes disponibles. Chaque entrée = réglages du coeur C.
# Ajoute ici les nouveaux mécanismes (et leur géométrie dans sim.c + leur dessin dans render.py).
MECHS = {
    # PRESSE : 2 blocs (haut / bas) qui se referment au centre (validé par Yanis)
    'press': dict(mech=0, axis=0, W=320.0, H=100.0, g_open=210.0, rod_w=34.0),
    # PRESSE LATÉRALE : 2 blocs (gauche / droite)
    'press_side': dict(mech=0, axis=1, W=320.0, H=100.0, g_open=210.0, rod_w=34.0),
    # MÂCHOIRES : 2 demi-disques (rayon W/2, faces plates face à face) qui claquent haut / bas comme une bouche.
    # H = W/2 = profondeur d'un demi-disque (sert aussi de zone interdite pour placer les balles nées).
    'jaws': dict(mech=1, axis=0, W=320.0, H=160.0, g_open=210.0, rod_w=34.0),
    # IRIS : 4 lames pointées (haut, bas, gauche, droite), pointes à 90°, qui glissent vers le centre et se referment
    # en croix (elles se touchent exactement). W = largeur d'une lame, H = longueur de la partie droite, g_open = ouverture.
    'iris': dict(mech=2, axis=0, W=180.0, H=80.0, g_open=120.0, rod_w=34.0),
}

BASE = dict(R=R, cx=CX, cy=CY, speed=320.0, dt=1 / 240.0,
            t_close=0.16, t_hold=0.06, t_open=0.30, t_pause=0.30,
            fill_target=0.50, tmax=62.0, t_end_hold=2.5,
            r0=26.0, rmin=15.0, shrink=0.88, stop_no_green=0, jitter=40.0, npos_iter=4,
            slit_ang=0.0, slit_w=0.0, rescue=0.0, rescue_v=400.0, rescue_nmax=0, lone_max=6.0)

_lib = None


def lib():
    global _lib
    if _lib is None:
        if not os.path.exists(LIB) or os.path.getmtime(LIB) < os.path.getmtime(SRC):
            subprocess.check_call(['gcc', '-O2', '-shared', '-fPIC', SRC, '-o', LIB, '-lm'])
        _lib = C.CDLL(LIB)
        _lib.run.argtypes = [C.POINTER(Params), C.c_ulonglong, C.POINTER(Result), C.c_char_p, C.c_char_p]
    return _lib


def make_params(mech='press', **over):
    d = dict(BASE)
    d.update(MECHS[mech])
    d.update(over)
    p = Params()
    for k, v in d.items():
        setattr(p, k, v)
    return p, d


def simulate(seed, mech='press', rec=None, events=None, **over):
    p, d = make_params(mech, **over)
    r = Result()
    lib().run(C.byref(p), seed, C.byref(r), rec.encode() if rec else None, events.encode() if events else None)
    out = {k: getattr(r, k) for k, _ in Result._fields_}
    out['green_cap'] = list(r.green_cap)
    out['col_count'] = list(r.col_count)
    out['seed'] = seed
    out['params'] = d
    return out


def load_record(path):
    """Renvoie une liste de frames : (t, f, phase, array[n,6] id,col,x,y,r,cap)."""
    import numpy as np
    raw = np.fromfile(path, dtype=np.float32)
    frames, i = [], 0
    while i < len(raw):
        t, f, ph, n = raw[i:i + 4]
        n = int(n)
        arr = raw[i + 4:i + 4 + 6 * n].reshape(n, 6)
        frames.append((float(t), float(f), int(ph), arr))
        i += 4 + 6 * n
    return frames


def load_events(path):
    """Événements : colonnes t, type, x, y, col, val.
    type 1 = coup (val = balles écrasées), 2 = balle écrasée (val = rayon), 3 = rebond sur le cercle,
    4 = début de fermeture (val = balles prises), 5 = balle née, 6 = balle sortie par la fente."""
    import numpy as np
    return np.fromfile(path, dtype=np.float32).reshape(-1, 6)


if __name__ == '__main__':
    import sys
    import time
    t0 = time.time()
    r = simulate(int(sys.argv[1]) if len(sys.argv) > 1 else 1, sys.argv[2] if len(sys.argv) > 2 else 'press')
    r.pop('params')
    print(r, '%.2fs' % (time.time() - t0))
