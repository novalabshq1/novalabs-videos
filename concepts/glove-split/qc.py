"""Framing QC on key frames before the burst. python3 qc.py video.mp4 t1,t2,... outdir"""
import sys, subprocess, os, numpy as np
from PIL import Image
v, ts, od = sys.argv[1], [float(x) for x in sys.argv[2].split(',')], sys.argv[3]
os.makedirs(od, exist_ok=True); ok = True; prev = None
for t in ts:
    f = f"{od}/k_{t:06.2f}.png"
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-ss', str(t), '-i', v, '-frames:v', '1', f], check=True)
    a = np.asarray(Image.open(f).convert('RGB')).astype(int)
    wm = (a.min(2) > 235)
    ys, xs = np.nonzero(wm[560:1600]); ys = ys + 560
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy, dw, dh = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0 + 1, y1 - y0 + 1
    ml, mr = x0, 1079 - x1
    ty, tx = np.nonzero(wm[330:470]); ty = ty + 330
    tcx = (tx.min() + tx.max()) / 2; tbase = ty.max() + 1
    bg = a[1700:1900:7, 20:900:7]; bgv = np.median(bg.reshape(-1, 3), 0)
    fail = []
    if abs(cx - 540) > 4 or abs(cy - 1075) > 4: fail.append('centre')
    if abs(dw - 900) > 6 or abs(dh - 900) > 6: fail.append('diametre')
    if abs(ml - mr) > 4: fail.append('marges')
    if prev and (abs(prev[0] - cx) > 0.5 or abs(prev[1] - cy) > 0.5): fail.append('bouge')
    if abs(tcx - 540) > 4 or abs(tbase - 440) > 1: fail.append('titre')
    prev = (cx, cy)
    ok &= not fail
    print(f"t={t:6.2f} cercle centre=({cx:.1f},{cy:.1f}) diam={dw}x{dh} marges {ml}/{mr} | titre centre x={tcx:.1f} base={tbase} | fond={bgv} {'OK' if not fail else 'ECHEC ' + ','.join(fail)}")
print('QC', 'OK' if ok else 'ECHEC')
