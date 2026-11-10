"""Contrôle qualité physique d'un enregistrement : chevauchements, sorties du cercle, pénétration du mécanisme.
python3 diag.py rec.bin [mech]"""
import sys
import numpy as np
from sim import load_record, MECHS, CX, CY, R


def frame_overlaps(a, include_cap=False):
    if not include_cap:
        a = a[a[:, 5] == 0]
    p = a[:, 2:4].astype(np.float64); r = a[:, 4].astype(np.float64)
    d = np.sqrt(((p[:, None] - p[None]) ** 2).sum(-1))
    ov = (r[:, None] + r[None]) - d
    np.fill_diagonal(ov, -1)
    return ov


def main(path, mech='press'):
    fr = load_record(path)
    m = MECHS[mech]
    worst = []
    for k, (t, f, ph, a) in enumerate(fr):
        ov = frame_overlaps(a)
        i, j = np.unravel_index(np.argmax(ov), ov.shape) if ov.size else (0, 0)
        mo = ov.max() if ov.size else 0
        free = a[a[:, 5] == 0]
        dist = np.hypot(free[:, 2] - CX, free[:, 3] - CY) + free[:, 4] - R
        worst.append((mo, t, len(a), float(dist.max()) if len(free) else 0))
    w = np.array(worst)
    print('frames', len(w), 'max overlap %.2f at t=%.2f' % (w[:, 0].max(), w[np.argmax(w[:, 0]), 1]))
    print('p99 overlap %.2f  p50 %.2f' % (np.percentile(w[:, 0], 99), np.percentile(w[:, 0], 50)))
    print('frames with overlap > 3px:', int((w[:, 0] > 3).sum()), ' > 1px:', int((w[:, 0] > 1).sum()))
    print('max wall penetration %.2f' % w[:, 3].max())
    return w


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'press')
