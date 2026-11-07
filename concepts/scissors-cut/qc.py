"""QC: python3 qc.py video.mp4 t1,t2,...  -> extracts frames, checks ring bbox, title, background."""
import sys, subprocess, numpy as np
from PIL import Image
v = sys.argv[1]; ts = [float(x) for x in sys.argv[2].split(',')]; od = sys.argv[3]
boxes = []
for t in ts:
    f = f"{od}/qc_{t:06.2f}.png"
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(t), '-i', v, '-frames:v', '1', f], check=True)
    a = np.asarray(Image.open(f).convert('RGB')).astype(int)
    white = (a.min(2) > 225)
    reg = white[540:1620]
    rows = np.nonzero(reg.sum(1) >= 2)[0]; cols = np.nonzero(white[540:1620].sum(0) >= 2)[0]
    y0, y1 = rows[0] + 540, rows[-1] + 540; x0, x1 = cols[0], cols[-1]
    cx, cy, w = (x0 + x1 + 1) / 2, (y0 + y1 + 1) / 2, x1 - x0 + 1
    ml, mr = x0, 1080 - 1 - x1
    tit = white[380:460]; tr = np.nonzero(tit.sum(1))[0]; tc = np.nonzero(tit.sum(0))[0]
    tcx = (tc[0] + tc[-1] + 1) / 2; base = 380 + tr[-1] + 1
    bg = a[1700:1900, 20:900]; bgm = np.median(bg.reshape(-1, 3), 0)
    ok = abs(cx - 540) <= 4 and abs(cy - 1075) <= 6 and abs(w - 900) <= 6 and abs(ml - mr) <= 4 and abs(tcx - 540) <= 4
    boxes.append((x0, y0, x1, y1))
    print(f"t={t:6.2f} box=({x0},{y0})-({x1},{y1}) centre=({cx},{cy}) w={w} margins L{ml}/R{mr} title_cx={tcx} title_bottom={base} bg={bgm} {'OK' if ok else 'FAIL'}")
print('box stable:', len(set(boxes)) == 1)
