# Framing QC on saved key frames (key_*.npy, BGR): ring bbox, gap centre, title position.
import numpy as np, glob, sys
fails = 0; prev = None
for f in sorted(glob.glob('key_*.npy')):
    im = np.load(f).astype(int); b, g, r = im[..., 0], im[..., 1], im[..., 2]
    mx = im.max(2); mn = im.min(2)
    ring = (mx > 150) & (mx - mn > 90)
    ring[:520] = False
    # keep only pixels whose hue matches the ring gradient (rejects balls / confetti of other colours)
    C1 = np.array([0.10, 0.90, 0.95]); CM = np.array([0.30, 0.42, 1.00]); C2 = np.array([0.98, 0.30, 0.80])
    us = np.linspace(0, 1, 200)
    grad = np.array([C1 * (1 - 2 * u) + CM * 2 * u if u < 0.5 else CM * (2 - 2 * u) + C2 * (2 * u - 1) for u in us])
    grad = grad / grad.max(1, keepdims=True)
    rgb = np.stack([r, g, b], -1) / np.maximum(mx, 1)[..., None]
    ys, xs = np.nonzero(ring)
    d = np.abs(rgb[ys, xs][:, None, :] - grad[None]).max(2).min(1)
    ring[ys[d > 0.15], xs[d > 0.15]] = False
    # only the ring stroke: pixels at the stroke radius around the expected centre (robust to balls/confetti)
    yy, xx = np.nonzero(ring)
    rr = np.hypot(xx - 540, yy - 1075)
    sel = (rr > 470 * 1.04) & (rr < 485 * 1.04)
    xx, yy = xx[sel], yy[sel]
    l, rgt, top, bot = xx.min(), xx.max(), yy.min(), yy.max()
    w = rgt - l + 1; cx = (l + rgt) / 2; cy = top + (w - 1) / 2
    ml, mr = l, 1079 - rgt
    # gap: bottom-most ring pixels on each side
    # gap: angular bins (0.25 deg) of the stroke; confetti specks are too sparse to fill a bin
    ang = np.degrees(np.arctan2(yy - 1075, xx - 540)) % 360
    cnt = np.bincount((ang * 4).astype(int), minlength=1440)
    full = cnt >= 6
    k = 360
    a0 = k; a1 = k
    while not full[a0 - 1]: a0 -= 1
    while not full[a1 + 1]: a1 += 1
    gdeg = (a1 - a0 + 1) / 4; gmid = (a0 + a1 + 1) / 8
    gm = 540 + 480 * 1.04 * np.cos(np.radians(gmid))
    # title
    wt = (im.min(2) > 200); wt[500:] = False
    ty, tx = np.nonzero(wt)
    tcx = (tx.min() + tx.max()) / 2; tbase = ty.max() + 1
    ok = abs(cx - 540) <= 4 and abs(cy - 1075) <= 6 and abs(w - 997) <= 8 and abs(ml - mr) <= 4 and abs(gm - 540) <= 4 \
        and abs(tcx - 540) <= 4 and abs(tbase - 440) <= 1 and (prev is None or prev == (l, rgt, top))
    prev = (l, rgt, top)
    fails += not ok
    print(f, 'OK' if ok else 'FAIL', f'ring cx={cx} cy={cy} w={w} margins={ml}/{mr} gap_mid_x={gm:.1f} gap_mid_deg={gmid} gap_width_deg~{gdeg} title cx={tcx} base={tbase}')
sys.exit(1 if fails else 0)
