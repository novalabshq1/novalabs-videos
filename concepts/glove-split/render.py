"""Glove Split — renderer (cairo via ctypes), 1080x1920 @ 60 fps, no scaling.
python3 render.py sim.npz out.mkv            (lossless intermediate)
python3 render.py sim.npz prefix 0,120,600   (PNG stills of chosen frames)
"""
import sys, math, subprocess, ctypes as C
import numpy as np
import cr
from sim import (CX, CY, R_OUT, RING_W, RAD, ARM_L, ARM_HW, HUB_R, FIST_U, FIST_R, THUMB_U, THUMB_V, THUMB_R,
                 CUFF_U0, CUFF_U1, CUFF_HW, FPS)

W, H = 1080, 1920
TITLE = b"EVERY PUNCH = 2 NEW BALLS"
def hx(h): return tuple(int(h[i:i+2], 16) / 255 for i in (1, 3, 5))
PAL = [hx(h) for h in ("#FFFFFF", "#3DDC5A", "#FFD60A", "#FF8A00", "#FF3B30", "#FF4FA3", "#A44BFF", "#2F7BFF", "#19E3FF")]
BG = hx("#05070D"); GREY = hx("#C9CDD5"); RIVET = hx("#5B606C")
RING_R = R_OUT - RING_W / 2
I = 1.5   # 3 px outline drawn fully inside the collision edge

d = np.load(sys.argv[1]); out = sys.argv[2]
only = set(int(x) for x in sys.argv[3].split(',')) if len(sys.argv) > 3 else None
pos, col, off, theta = d['pos'], d['col'], d['off'], d['theta']
ev = d['ev']; t_crack = float(d['t_crack']); t_boom = float(d['t_boom']); omega = float(d['omega'])
nsim = len(theta)
nfr = nsim + int(round(1.5 * FPS))
pops = ev[ev[:, 1] == 0]

rng = np.random.default_rng(11)
stars = []
while len(stars) < 80:
    x, y = rng.uniform(8, W - 8), rng.uniform(8, H - 8)
    if math.hypot(x - CX, y - CY) < R_OUT + 30: continue
    if 330 < y < 470 and 60 < x < 1020: continue      # keep the title area clean
    stars.append((x, y, rng.uniform(1.0, 1.5), rng.uniform(0.3, 0.8)))
NCR = 16
crack_a = np.linspace(0, 2 * np.pi, NCR, endpoint=False) + rng.uniform(-0.06, 0.06, NCR) + 0.1; crack_order = rng.permutation(NCR)
bounds = np.append(crack_a, crack_a[0] + 2 * np.pi)
frags = [(bounds[i], bounds[i + 1], rng.uniform(1300, 1600), rng.choice([-1, 1]) * rng.uniform(0.8, 1.6)) for i in range(NCR)]

s = cr.surface_create(0, W, H); c = cr.create(s)
stride = cr.get_stride(s); buf = cr.get_data(s)
ff = None
if only is None:
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}', '-r', str(FPS),
                           '-i', '-', '-c:v', 'libx264rgb', '-qp', '0', '-preset', 'ultrafast', out], stdin=subprocess.PIPE)
cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
te = cr.TE(); cr.text_extents(c, TITLE, C.byref(te))
tx = 540 - (te.xb + te.w / 2)
print('title width', round(te.w, 1))

def rivet(x, y, r=4.5):
    cr.new_path(c); cr.arc(c, x, y, r, 0, 2 * math.pi); cr.set_rgb(c, *RIVET); cr.fill(c)
def fill_stroke():
    cr.set_rgb(c, *GREY); cr.fill_preserve(c); cr.set_rgb(c, 1, 1, 1); cr.set_line_width(c, 3); cr.stroke(c)
def capsule(u0, u1, hw):
    cr.new_path(c); cr.arc(c, u1, 0, hw - I, -math.pi / 2, math.pi / 2); cr.arc(c, u0, 0, hw - I, math.pi / 2, 3 * math.pi / 2); cr.close_path(c)
def disc(x, y, r):
    cr.new_path(c); cr.arc(c, x, y, r - I, 0, 2 * math.pi)
def mechanism(th):
    cr.save(c); cr.translate(c, CX, CY); cr.rotate(c, th)
    capsule(-ARM_L, ARM_L, ARM_HW); fill_stroke()
    for u in (-200, -110, 110, 200): rivet(u, 0, 4)
    for sgn in (1, -1):
        cr.save(c)
        if sgn < 0: cr.rotate(c, math.pi)
        # cuff (rounded rectangle)
        u0, u1, hw, rr = CUFF_U0 + I, CUFF_U1 + 8, CUFF_HW - I, 8
        cr.new_path(c)
        cr.arc(c, u1 - rr, -hw + rr, rr, -math.pi / 2, 0); cr.arc(c, u1 - rr, hw - rr, rr, 0, math.pi / 2)
        cr.arc(c, u0 + rr, hw - rr, rr, math.pi / 2, math.pi); cr.arc(c, u0 + rr, -hw + rr, rr, math.pi, 3 * math.pi / 2)
        cr.close_path(c); fill_stroke()
        rivet(CUFF_U0 + 19, -18, 4); rivet(CUFF_U0 + 19, 18, 4)
        disc(FIST_U, 0, FIST_R); fill_stroke()
        # knuckle seam (dark grey, 3 px) facing the punch direction
        cr.new_path(c); cr.arc(c, FIST_U - 14, 0, FIST_R * 0.62, -1.1, 1.1); cr.set_rgb(c, *RIVET); cr.set_line_width(c, 3); cr.stroke(c)
        disc(THUMB_U, THUMB_V, THUMB_R); fill_stroke()
        cr.restore(c)
    disc(0, 0, HUB_R); fill_stroke(); rivet(0, 0, 8)
    cr.restore(c)

for fi in range(nfr):
    if only is not None and fi not in only: continue
    t = (fi + 1) / FPS
    k = min(fi, nsim - 1)
    th = float(theta[k]) + omega * max(0, fi - (nsim - 1)) / FPS
    cr.set_rgb(c, *BG); cr.paint(c)
    for (x, y, r, a) in stars:
        cr.new_path(c); cr.arc(c, x, y, r, 0, 2 * math.pi); cr.set_rgba(c, 1, 1, 1, a); cr.fill(c)
    cr.set_rgb(c, 1, 1, 1); cr.move_to(c, tx, 440); cr.show_text(c, TITLE)
    # ring
    cr.set_line_cap(c, 0)
    if t < t_boom:
        cr.new_path(c); cr.arc(c, CX, CY, RING_R, 0, 2 * math.pi); cr.set_rgb(c, 1, 1, 1); cr.set_line_width(c, RING_W); cr.stroke(c)
        if t >= t_crack:
            nk = int(math.ceil(NCR * min(1, (t - t_crack) / (t_boom - t_crack - 0.1))))
            cr.set_rgb(c, *BG); cr.set_line_width(c, 3)
            for q in crack_order[:nk]:
                a = crack_a[q]; ca, sa = math.cos(a), math.sin(a)
                pts = [(RING_R - 4, 0), (RING_R - 1, 3.5), (RING_R + 1, -3.5), (RING_R + 4, 0)]
                cr.new_path(c)
                for j, (r, dt) in enumerate(pts):
                    (cr.move_to if j == 0 else cr.line_to)(c, CX + r * ca - dt * sa, CY + r * sa + dt * ca)
                cr.stroke(c)
    else:
        tau = t - t_boom
        cr.set_rgb(c, 1, 1, 1); cr.set_line_width(c, RING_W)
        for (a0, a1, v, w) in frags:
            am = (a0 + a1) / 2; mx, my = CX + RING_R * math.cos(am), CY + RING_R * math.sin(am)
            ox, oy = math.cos(am) * v * tau, math.sin(am) * v * tau
            cr.save(c); cr.translate(c, mx + ox, my + oy); cr.rotate(c, w * tau); cr.translate(c, -mx, -my)
            cr.new_path(c); cr.arc(c, CX, CY, RING_R, a0 + 0.015, a1 - 0.015); cr.stroke(c); cr.restore(c)
    # pop rings (0.18 s) at every split, in the parent colour
    if t < t_boom + 0.2:
        rec = pops[(pops[:, 0] <= t) & (pops[:, 0] > t - 0.18)]
        cr.set_line_width(c, 3)
        for (te_, _, x, y, _, pc) in rec:
            a = (t - te_) / 0.18; r0 = RAD[int(pc)]
            cr.new_path(c); cr.arc(c, x, y, r0 * (1.0 + 0.9 * a), 0, 2 * math.pi)
            cr.set_rgba(c, *PAL[int(pc)], 1 - a); cr.stroke(c)
    # balls
    if fi < nsim:
        P = pos[off[fi]:off[fi + 1]]; K = col[off[fi]:off[fi + 1]]
        for ci in range(9):
            sel = P[K == ci]
            if not len(sel): continue
            cr.set_rgb(c, *PAL[ci]); cr.new_path(c); rr = float(RAD[ci])
            for (x, y) in sel:
                if -40 < x < W + 40 and -40 < y < H + 40:
                    cr.new_sub_path(c); cr.arc(c, float(x), float(y), rr, 0, 2 * math.pi)
            cr.fill(c)
    mechanism(th)
    cr.flush(s)
    if only is not None:
        import PIL.Image
        im = PIL.Image.frombuffer('RGBA', (W, H), C.string_at(buf, stride * H), 'raw', 'BGRA', 0, 1)
        im.convert('RGB').save(f"{out}_{fi:05d}.png")
    else:
        ff.stdin.write(C.string_at(buf, stride * H))
if ff: ff.stdin.close(); ff.wait()
print('frames', nfr, 'dur', nfr / FPS, 'crack', t_crack, 'boom', t_boom)
