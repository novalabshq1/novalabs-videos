# Usage: python3 qc_frame.py kf/*.png  -> framing checks (white circle centre, diameter, margins)
import numpy as np, subprocess, sys
for f in sorted(sys.argv[1:], key=lambda x: float(x.split('_')[-1][:-4])):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', f, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(1920, 1080, 3).astype(int)
    white = a.min(2) > 200
    xs = np.nonzero(white[1075])[0]; ys = np.nonzero(white[:, 540])[0]
    L, Rr, T, B = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy, d = (L + Rr) / 2, (T + B) / 2, Rr - L + 1
    outside = a[:600].max()   # nothing above the arena (no title / text)
    ok = abs(cx - 540) <= 4 and abs(cy - 1075) <= 4 and abs(d - 900) <= 6 and abs(L - (1079 - Rr)) <= 4
    print(f, 'centre', (cx, cy), 'diam', d, 'vdiam', B - T + 1, 'margins', L, 1079 - Rr, 'max above y600', outside, 'OK' if ok else 'FAIL')
