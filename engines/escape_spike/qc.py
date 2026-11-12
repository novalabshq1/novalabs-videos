import cv2, numpy as np, glob, json, sys, math
S0, S1 = int(sys.argv[1]), int(sys.argv[2])   # screamer frame range
ok = True; widths = []
for f in sorted(glob.glob('keys/*.png')):
    fi = int(f[-9:-4]); im = cv2.imread(f).astype(int)
    if S0 <= fi < S1:
        print(fi, 'SCREAMER  mean lum', im.mean().round(1), 'dark-frac', (im.max(2) < 20).mean().round(3)); continue
    m = im.max(2) > 40
    reg = m.copy(); reg[:520] = False; reg[1590:] = False
    ys, xs = np.nonzero(reg)
    l, r, t, b = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy = (l + r) / 2, (t + b) / 2; wdt = r - l + 1; widths.append(wdt)
    sat = (im.max(2) - im.min(2)) > 60
    row = sat[1555, :]; xs2 = np.nonzero(row)[0]
    gaps = [(xs2[i], xs2[i+1]) for i in range(len(xs2) - 1) if xs2[i+1] - xs2[i] > 60]
    gm = [(a + b) / 2 for a, b in gaps]
    tm = m[:520]; ty, tx = np.nonzero(tm)
    tcx = (tx.min() + tx.max()) / 2; tb = ty.max()
    good = abs(cx - 540) <= 4 and abs(cy - 1075) <= 6 and abs((l) - (1079 - r)) <= 4 and any(abs(g - 540) <= 4 for g in gm) and abs(tcx - 540) <= 4 and abs(tb - 440) <= 1
    ok &= good
    print(fi, 'ring c=(%.1f,%.1f) w=%d margins L%d R%d gapmid=%s title cx=%.1f base=%d %s' % (cx, cy, wdt, l, 1079 - r, gm, tcx, tb, 'OK' if good else 'FAIL'))
print('width spread', max(widths) - min(widths)); ok &= max(widths) - min(widths) <= 4
# logs
lg = json.load(open('esc_log.json'))
lok = True
for t, x, y, a in lg['launches']:
    if not (x == 540 and y == 1015 and -88 <= a <= -72): lok = False; print('BAD launch', t, x, y, a)
print('launches OK' if lok else 'launch FAIL', len(lg['launches']), [round(l[3],1) for l in lg['launches']]); ok &= lok
for x, y, t in lg['deaths']:
    r = math.hypot(x - 540, y - 1075)
    print('death t=%.2f r=%.1f (spike zone %.0f..%.0f)' % (t, r, 474 - 62 - 26, 474 - 26))
print('ALL OK' if ok else 'FAILED')
