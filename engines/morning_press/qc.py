"""QC for a morning_press video. usage: python3.13 qc.py SEED final.mp4"""
import sys, json, subprocess, numpy as np
SEED = int(sys.argv[1]); VID = sys.argv[2]
import os
P = 'runs/' if os.path.exists(f'runs/events_{SEED}.json') else ''
ev = json.load(open(f'{P}events_{SEED}.json')); qf = json.load(open(f'{P}qc_frames_{SEED}.json'))
ok = True
def chk(name, cond, info=''):
    global ok; ok &= bool(cond); print(('OK  ' if cond else 'FAIL'), name, info)

hits = ev['hits']
chk('every hit crushes >=1 ball (no empty hit)', all(h.get('crushed', 0) >= 1 for h in hits if 'tc' in h),
    f"{len(hits)} hits, min crushed {min(h.get('crushed', 0) for h in hits)}")
gaps = [b['t0'] - a['t0'] for a, b in zip(hits, hits[1:])]
print('     hit interval: median %.2f s, max %.2f s' % (np.median(gaps), max(gaps)))
# splits: compare level counts just before / after every crush
by_t = {}
for (t, x, y, L, L2) in ev['crush']: by_t.setdefault(round(t, 5), []).append((L, L2))
ts = np.array([q['t'] for q in qf]); bad = 0
for t, lst in by_t.items():
    i1 = int(np.searchsorted(ts, t - 1e-4)); i0 = i1 - 1
    if i0 < 0 or i1 >= len(qf): continue
    exp = np.array(qf[i0]['lv']); 
    for (L, L2) in lst: exp[L] -= 1; exp[L2] += 2
    if any(L2 != min(L + 1, 7) for L, L2 in lst): bad += 1
    # escapes between the two frames would change counts too
    esc = [e for e in ev['escape'] if qf[i0]['t'] <= e['t'] <= qf[i1]['t'] + 0.02]
    if not esc and list(exp) != qf[i1]['lv']: bad += 1
chk('each crushed ball -> 2 balls of the next colour', bad == 0, f'{len(ev["crush"])} crushes, {bad} mismatches')
chk('no ball through the circle (except via the slit)', max(q['wall_pen'] for q in qf) < 1.0, 'max %.2f px' % max(q['wall_pen'] for q in qf))
chk('no ball overlap (free balls)', max(q['overlap'] for q in qf) < 3.0, 'max %.2f px, frames>1px: %d' % (max(q['overlap'] for q in qf), sum(q['overlap'] > 1 for q in qf)))
chk('no ball inside the mechanism', max(q['plate_pen'] for q in qf) < 2.0, 'max %.2f px' % max(q['plate_pen'] for q in qf))
chk('cheater: exactly one ball leaves through the slit', len(ev['escape']) == 1 if ev['slit_h'] > 0 else True, str(ev['escape']))
chk('full between 42 and 57 s', 42 <= ev['full_t'] <= 57, '%.2f s, %d balls, fill %.3f' % (ev['full_t'], ev['n'], qf[-1]['fill']))
dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', VID]))
chk('duration 45-60 s', 45 <= dur <= 60, '%.2f s' % dur)
# framing: detect the white ring in a few frames
import struct
W, H = 1080, 1920
def frame_at(t):
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', VID, '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'])
    return np.frombuffer(raw, np.uint8).reshape(H, W)
cs = []
for t in (0.5, dur * 0.3, dur * 0.6, dur - 0.5):
    g = frame_at(t).astype(float)
    pts = []
    for k in range(72):
        th = k * 2 * np.pi / 72; rr = np.arange(380, 530, 0.5)
        px = np.round(540 + rr * np.cos(th)).astype(int); py = np.round(1075 + rr * np.sin(th)).astype(int)
        v = g[py, px]; idx = np.nonzero(v > 200)[0]
        if len(idx): pts.append((px[idx[-1]], py[idx[-1]]))
    P_ = np.array(pts, float); A_ = np.c_[2 * P_, np.ones(len(P_))]; bb = (P_ ** 2).sum(1)
    for _ in range(3):   # least squares circle, drop outliers (slit, balls)
        sol = np.linalg.lstsq(A_, bb, rcond=None)[0]; c0 = sol[:2]; rad = np.sqrt(sol[2] + c0 @ c0)
        res_ = np.abs(np.hypot(*(P_ - c0).T) - rad); keep = res_ < 3
        A_, bb, P_ = A_[keep], bb[keep], P_[keep]
    cs.append((c0[0], c0[1], 2 * rad, 2 * rad))
cs = np.array(cs); print('     ring (cx, cy, wx, wy) per sample:', cs.round(1).tolist())
cx, cy = cs[:, 0].mean(), cs[:, 1].mean(); dia = cs[:, 2].mean() - 4   # outermost bright pixel -> stroke centre (5 px stroke)
chk('ring centred (540+-4, 1075+-4)', abs(cx - 540) <= 4 and abs(cy - 1075) <= 4, f'{cx:.1f}, {cy:.1f}')
chk('ring diameter 900+-6', abs(dia - 900) <= 6, f'{dia:.1f}')
chk('ring static', np.ptp(cs[:, 0]) < 1.5 and np.ptp(cs[:, 1]) < 1.5 and np.ptp(cs[:, 2]) < 1.5)
pr = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_name,profile,width,height,r_frame_rate,pix_fmt,sample_rate', '-of', 'json', VID])
print(pr.decode())
print('QC', 'PASSED' if ok else 'FAILED')
