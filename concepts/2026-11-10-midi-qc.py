import glob, json, numpy as np, subprocess, math
yy, xx = np.mgrid[0:1920, 0:1080]
for f in sorted(glob.glob('kf/k*.png')):
    raw = subprocess.run(['ffmpeg','-loglevel','error','-i',f,'-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(1920,1080,3).astype(int)
    white = (a.min(2) > 200)
    ys, xs = np.nonzero(white)
    l, r_, t, b = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy = (l + r_) / 2, (t + b) / 2; dia = r_ - l + 1
    ok = abs(cx-540)<=4 and abs(cy-1075)<=4 and abs(dia-900)<=6 and abs(l-(1079-r_))<=4
    outside = ((xx-540)**2+(yy-1075)**2 > 460**2) & (a.max(2) > 40)
    print(f, 'c', cx, cy, 'dia', dia, 'marg', l, 1079-r_, 'OK' if ok else 'FAIL', 'outside px', int(outside.sum()))
q = json.load(open('/home/user/novalabs-videos/engines/string_circle_rush/qc_log.json'))
sp = np.array(q['speeds'])
print('v start', sp[0], 'max ratio', (sp[1:]/sp[:-1]).max(), 'vmax', sp.max(), 'mult', sp.max()/200)
print('walls all +10:', all(a-b==10 for (_,_,b,a) in q['walls']), len(q['walls']))
print('deaths', q['deaths'], 'max step px', q['max_step_px'])
print('t2', q['t2'], 'end', q['end_t'], 'duel', q['end_t']-q['t2'])
