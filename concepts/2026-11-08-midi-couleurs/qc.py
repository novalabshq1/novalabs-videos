import json, subprocess, numpy as np, sys
from PIL import Image
ev = json.load(open('out_noaudio.events.json'))
q = ev['qc']
el = [e[0] for e in ev['elim']]
key = [0.5, 5, 15, 30] + [t+0.05 for t in el] + [ev['t2']+0.2, ev['t2']+4, ev['t_win']-1.0, ev['t_win']-0.3, ev['t_win']+0.4, ev['duration']-0.05]
key = sorted(set(round(k,2) for k in key))
ok = True
for i,t in enumerate(key):
    subprocess.run(['ffmpeg','-y','-loglevel','error','-ss',str(t),'-i','final.mp4','-frames:v','1',f'k_{i:02d}.png'],check=True)
    a = np.asarray(Image.open(f'k_{i:02d}.png').convert('RGB')).astype(int)
    white = (a.min(axis=2) > 190)
    ys, xs = np.nonzero(white)
    x0,x1,y0,y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy = (x0+x1)/2, (y0+y1)/2; dw, dh = x1-x0+1, y1-y0+1
    ml, mr = x0, 1079-x1
    top = a[:560].max()
    good = abs(cx-540)<=4 and abs(cy-1075)<=4 and abs(dw-900)<=6 and abs(dh-900)<=6 and abs(ml-mr)<=4 and top < 8
    ok &= good
    print(f't={t:6.2f} centre=({cx:.1f},{cy:.1f}) diam={dw}x{dh} marges {ml}/{mr} haut_max={top} {"OK" if good else "ECHEC"}')
vf = np.array(q['v_frames'])
inc = (vf[1:]/np.maximum(vf[:-1],1e-9)).max()
print('steps', q['steps'], 'min gap fil adverse', round(q['min_gap'],2), 'violations', q['violations'],
      'max sortie', round(q['max_out'],3), 'ajouts mur min/max', min(q['wall_adds']), max(q['wall_adds']), len(q['wall_adds']),
      'fils à la mort', q['dead_counts'], 'v0', vf[0], 'v max', round(vf.max(),1), 'mult', round(ev['mult'],2), 'hausse max/img', round(inc,4))
print('ALL OK' if ok and q['violations']==0 and q['max_out']<=1e-6 and 10<=min(q['wall_adds']) and max(q['wall_adds'])<=15 and all(c==0 for c in q['dead_counts']) and 140<=vf[0]<=150 and inc<=1.08 else 'QC FAIL')
