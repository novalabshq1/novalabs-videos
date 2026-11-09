"""Render a morning_press run. usage: python3.13 render.py SEED OUT_LOSSLESS.mkv [HW D SLIT_W ELEMENT]
Writes events_SEED.json (all logs for QC + audio) next to the video. Frames are drawn directly at 1080x1920, 60 fps."""
import sys, json, math, ctypes, subprocess, numpy as np
import sim, cr, mechanisms as M

SEED = int(sys.argv[1]); OUT = sys.argv[2]
HW = float(sys.argv[3]) if len(sys.argv) > 3 else 140.0
D = float(sys.argv[4]) if len(sys.argv) > 4 else 190.0
SW = float(sys.argv[5]) if len(sys.argv) > 5 else 30.03
ELEMENT = sys.argv[6] if len(sys.argv) > 6 else 'cheater'
W, H = 1080, 1920
CX, CY, R = M.CX, M.CY, M.R

cfg = sim.default_cfg(); cfg['mech_kw'] = dict(HW=HW, D=D); cfg['slit_w'] = SW; cfg['slit'] = ELEMENT == 'cheater'
res = sim.run(SEED, cfg, record=True)
assert res['ok'], res.get('why')
frames = res['frames']; ev = res['events']
mech = M.MECHS[cfg['mech']](**cfg['mech_kw'])
json.dump(dict(seed=SEED, cfg=cfg, full_t=res['full_t'], end_t=res['end_t'], n=res['n'], levels=res['levels'],
               slit_a=res['slit_a'], slit_h=res['slit_h'], hits=ev['hits'], crush=ev['crush'], wall=ev['wall'],
               escape=ev['escape'], spawn_overlap=ev['spawn_overlap'], nframes=len(frames)),
          open(f'events_{SEED}.json', 'w'))
print('seed', SEED, 'full', res['full_t'], 'frames', len(frames), 'hits', len(ev['hits']), 'esc', [e['t'] for e in ev['escape']], flush=True)

COL = [tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)) for h in sim.COLORS]
def hexc(h): return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
STEEL = hexc('#CDD1D9'); STEEL_D = hexc('#B8BCC6'); STEEL_L = hexc('#D6D9E0'); RIVET = hexc('#5B606C')

surf = cr.surface_create(0, W, H); c = cr.create(surf); stride = cr.get_stride(surf)
cr.set_line_join(c, 1); cr.set_line_cap(c, 0)


def rect(x0, y0, x1, y1):
    cr.new_path(c); cr.rectangle(c, x0, y0, x1 - x0, y1 - y0)


def draw_press(u):
    f = mech.face(u); hw = mech.HW
    cr.save(c)
    cr.new_path(c); cr.arc(c, CX, CY, R - 2.5, 0, 2 * math.pi); cr.clip(c)
    for s in (-1, 1):   # s=-1 top block, +1 bottom block
        yf = CY + s * f; yb = CY + s * (R + 40)
        y0, y1 = min(yf, yb), max(yf, yb)
        rect(CX - hw, y0, CX + hw, y1); cr.set_rgb(c, *STEEL); cr.fill(c)
        # striking face plate (slightly darker band) and a lighter back band
        lip = 30
        ya, yb2 = (yf - lip, yf) if s < 0 else (yf, yf + lip)
        rect(CX - hw, ya, CX + hw, yb2); cr.set_rgb(c, *STEEL_D); cr.fill(c)
        yc = yf + s * 120
        rect(CX - hw + 26, min(yc, yc + s * 46), CX + hw - 26, max(yc, yc + s * 46)); cr.set_rgb(c, *STEEL_L); cr.fill(c)
        # outlines
        cr.set_line_width(c, 3); cr.set_rgb(c, 1, 1, 1)
        rect(CX - hw + 1.5, y0 + (1.5 if s > 0 else 0), CX + hw - 1.5, y1 - (1.5 if s < 0 else 0)); cr.stroke(c)
        cr.new_path(c); cr.move_to(c, CX - hw + 1.5, yf + s * lip); cr.line_to(c, CX + hw - 1.5, yf + s * lip); cr.stroke(c)
        # rivets
        for rx in (CX - hw + 16, CX + hw - 16, CX - hw / 3, CX + hw / 3):
            ry_ = yf + s * (lip / 2)
            cr.new_path(c); cr.arc(c, rx, ry_, 5, 0, 2 * math.pi); cr.set_rgb(c, *RIVET); cr.fill(c)
        for rx in (CX - hw + 14, CX + hw - 14):
            ry_ = yf + s * (lip + 22)
            cr.new_path(c); cr.arc(c, rx, ry_, 4.5, 0, 2 * math.pi); cr.set_rgb(c, *RIVET); cr.fill(c)
    cr.restore(c)


def draw_ring():
    cr.set_line_width(c, 5); cr.set_rgb(c, 1, 1, 1); cr.new_path(c)
    if res['slit_h'] > 0:
        ha = res['slit_h'] / R
        cr.arc(c, CX, CY, R, res['slit_a'] + ha, res['slit_a'] - ha + 2 * math.pi)
    else:
        cr.arc(c, CX, CY, R, 0, 2 * math.pi)
    cr.stroke(c)


ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}',
                       '-r', '60', '-i', '-', '-c:v', 'libx264rgb', '-preset', 'ultrafast', '-qp', '0', OUT], stdin=subprocess.PIPE)
QC = []


def rect_sdf(px, py, x0, y0, x1, y1):
    cx_, cy_ = (x0 + x1) / 2, (y0 + y1) / 2; hx, hy = (x1 - x0) / 2, (y1 - y0) / 2
    dx = np.abs(px - cx_) - hx; dy = np.abs(py - cy_) - hy
    return np.hypot(np.maximum(dx, 0), np.maximum(dy, 0)) + np.minimum(np.maximum(dx, dy), 0)


for fi, fr in enumerate(frames):
    cr.set_rgb(c, 0, 0, 0); cr.paint(c)
    x, y, r, ry, lv, cg = fr['x'], fr['y'], fr['r'], fr['ry'], fr['lv'], fr['caught']
    # free balls, grouped by colour
    for L in range(sim.NLV):
        idx = np.nonzero((lv == L) & ~cg)[0]
        if not len(idx): continue
        cr.new_path(c)
        for i in idx:
            cr.new_sub_path(c); cr.arc(c, float(x[i]), float(y[i]), float(r[i]), 0, 2 * math.pi)
        cr.set_rgb(c, *COL[L]); cr.fill(c)
    # caught balls being squashed (flattened ellipses)
    for i in np.nonzero(cg)[0]:
        rr, yy = float(r[i]), float(ry[i])
        if yy < 0.6: continue
        rx = min(rr * math.sqrt(rr / yy), rr * 1.7)
        cr.save(c); cr.translate(c, float(x[i]), float(y[i])); cr.scale(c, rx, yy)
        cr.new_path(c); cr.arc(c, 0, 0, 1, 0, 2 * math.pi); cr.restore(c)
        cr.set_rgb(c, *COL[int(lv[i])]); cr.fill(c)
    # ---- per-frame QC (free balls only; caught balls are being crushed)
    fx, fy, fr_ = x[~cg].astype(float), y[~cg].astype(float), r[~cg].astype(float)
    dc = np.hypot(fx - CX, fy - CY)
    inside = dc < R + 1
    if res['slit_h'] > 0:   # balls in the slit mouth / gone through it are excluded from the wall check
        a = np.angle(np.exp(1j * (np.arctan2(fy - CY, fx - CX) - res['slit_a'])))
        inside &= ~((np.abs(a) * R < res['slit_h'] + 2) & (dc > R - 40))
    wall_pen = float(np.max(dc[inside] + fr_[inside] - R)) if inside.any() else -99
    ov = 0.0
    if len(fx) > 1:
        dd = np.hypot(fx[:, None] - fx[None], fy[:, None] - fy[None]) - fr_[:, None] - fr_[None]
        np.fill_diagonal(dd, 99); ov = float(max(0, -dd.min()))
    f_ = mech.face(fr['u'])
    pp = max(float(np.max(fr_ - rect_sdf(fx, fy, CX - HW, CY - R - 60, CX + HW, CY - f_))),
             float(np.max(fr_ - rect_sdf(fx, fy, CX - HW, CY + f_, CX + HW, CY + R + 60)))) if len(fx) else -99
    QC.append(dict(t=fr['t'], n=int(len(x)), lv=np.bincount(lv, minlength=sim.NLV).tolist(), wall_pen=wall_pen, overlap=ov,
                   plate_pen=pp, caught=int(cg.sum()), u=fr['u'],
                   fill=float(np.sum(np.pi * r.astype(float) ** 2) / (math.pi * R * R))))
    draw_press(fr['u'])
    draw_ring()
    cr.flush(surf)
    ff.stdin.write(ctypes.string_at(cr.get_data(surf), stride * H))
    if fi % 600 == 0: print('frame', fi, '/', len(frames), flush=True)
ff.stdin.close(); ff.wait(); json.dump(QC, open(f'qc_frames_{SEED}.json', 'w')); print('done', OUT)
