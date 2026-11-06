"""Hammer Split — renderer. python3 render.py sim.npz out_lossless.mkv"""
import sys, math, subprocess, ctypes as C, numpy as np
import cr
from sim import CX, CY, R_OUT, RING_W, BR, HUB_R, HANDLE_L, HANDLE_HW, HEAD_X0, HEAD_X1, HEAD_HW, FPS
W, H = 1080, 1920
TITLE = b"HOW LONG UNTIL IT EXPLODES?"
BG = (0x07/255, 0x0A/255, 0x14/255)
PAL = ["#FF7A1A", "#2E7BFF", "#FF2E43", "#FFD21F", "#FF4FB4", "#2EDB5A", "#1FD6F0"]
PAL = [tuple(int(h[i:i+2], 16)/255 for i in (1, 3, 5)) for h in PAL]
GREY = (0xC6/255, 0xCA/255, 0xD3/255); RIVET = (0x4A/255, 0x4E/255, 0x57/255)
RING_R = R_OUT - RING_W/2
d = np.load(sys.argv[1]); out = sys.argv[2]
pos, col, off, theta = d['pos'], d['col'], d['off'], d['theta']
ev_t, ev_k = d['ev_t'], d['ev_k']
t_crack = float(ev_t[ev_k == 'crack_start'][0]); t_boom = float(ev_t[ev_k == 'boom'][0])
nfr = min(len(theta), int((t_boom + 3.2) * FPS))
rng = np.random.default_rng(7)
# stars outside the ring and away from title
stars = []
while len(stars) < 80:
    x, y = rng.uniform(8, W-8), rng.uniform(8, H-8)
    if math.hypot(x-CX, y-CY) < R_OUT + 22: continue
    if 360 < y < 470 and 70 < x < 1010: continue
    stars.append((x, y, rng.uniform(1.0, 1.5), rng.uniform(0.3, 0.8)))
# cracks / fragments
NCR = 16
crack_a = np.sort(rng.uniform(0, 2*np.pi, NCR)); crack_a += np.arange(NCR) * 0  # random
crack_order = rng.permutation(NCR)
bounds = np.append(crack_a, crack_a[0] + 2*np.pi)
frags = []
for i in range(NCR):
    a0, a1 = bounds[i], bounds[i+1]
    frags.append((a0, a1, rng.uniform(650, 1000), rng.uniform(-4, 4)))
s = cr.surface_create(0, W, H); c = cr.create(s)
stride = cr.get_stride(s); buf = cr.get_data(s)
ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}', '-r', str(FPS),
                       '-i', '-', '-c:v', 'libx264', '-qp', '0', '-preset', 'ultrafast', '-pix_fmt', 'yuv444p', out], stdin=subprocess.PIPE)
cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
te = cr.TE(); cr.text_extents(c, TITLE, C.byref(te))
tx = 540 - (te.xb + te.w/2)
def rr(x0, y0, x1, y1):
    cr.rectangle(c, x0, y0, x1-x0, y1-y0)
def rivet(x, y, r=4.5):
    cr.new_path(c); cr.arc(c, x, y, r, 0, 2*math.pi); cr.set_rgb(c, *RIVET); cr.fill(c)
def hammer(th):
    cr.save(c); cr.translate(c, CX, CY); cr.rotate(c, th)
    cr.set_line_width(c, 3); cr.set_line_join(c, 1)
    i = 1.5
    for (x0, x1, hw) in ((0, HANDLE_L, HANDLE_HW), (HEAD_X0, HEAD_X1, HEAD_HW)):
        cr.new_path(c); rr(x0+i, -hw+i, x1-i, hw-i); cr.set_rgb(c, *GREY); cr.fill_preserve(c); cr.set_rgb(c, 1, 1, 1); cr.stroke(c)
    cr.new_path(c); cr.arc(c, 0, 0, HUB_R-i, 0, 2*math.pi); cr.set_rgb(c, *GREY); cr.fill_preserve(c); cr.set_rgb(c, 1, 1, 1); cr.stroke(c)
    for x in (95, 165, 230): rivet(x, 0, 4)
    for (x, y) in ((HEAD_X0+18, -HEAD_HW+18), (HEAD_X1-18, -HEAD_HW+18), (HEAD_X0+18, HEAD_HW-18), (HEAD_X1-18, HEAD_HW-18), ((HEAD_X0+HEAD_X1)/2, 0)):
        rivet(x, y)
    rivet(0, 0, 7)
    cr.restore(c)
for fi in range(nfr):
    t = (fi + 1) / FPS  # sim state of frame fi is at time (fi+1)/FPS
    cr.set_rgb(c, *BG); cr.paint(c)
    for (x, y, r, a) in stars:
        cr.new_path(c); cr.arc(c, x, y, r, 0, 2*math.pi); cr.set_rgba(c, 1, 1, 1, a); cr.fill(c)
    cr.set_rgb(c, 1, 1, 1); cr.move_to(c, tx, 440); cr.show_text(c, TITLE)
    # ring
    cr.set_line_width(c, RING_W); cr.set_line_cap(c, 0)
    if t < t_boom:
        cr.new_path(c); cr.arc(c, CX, CY, RING_R, 0, 2*math.pi); cr.set_rgb(c, 1, 1, 1); cr.stroke(c)
        if t >= t_crack:
            k = int(NCR * min(1, (t - t_crack) / (t_boom - t_crack - 0.15))) 
            cr.set_rgb(c, *BG); cr.set_line_width(c, 3)
            for q in crack_order[:k]:
                a = crack_a[q]; ca, sa = math.cos(a), math.sin(a)
                # zig-zag crack across the ring
                pts = [(RING_R-5, 0), (RING_R-1, 3.5), (RING_R+1, -3.5), (RING_R+5, 0)]
                cr.new_path(c)
                for j, (r, dt) in enumerate(pts):
                    px = CX + r*ca - dt*sa; py = CY + r*sa + dt*ca
                    (cr.move_to if j == 0 else cr.line_to)(c, px, py)
                cr.stroke(c)
    else:
        tau = t - t_boom
        cr.set_rgb(c, 1, 1, 1); cr.set_line_width(c, RING_W)
        for (a0, a1, v, w) in frags:
            am = (a0 + a1)/2; mx, my = CX + RING_R*math.cos(am), CY + RING_R*math.sin(am)
            ox, oy = math.cos(am)*v*tau, math.sin(am)*v*tau
            cr.save(c); cr.translate(c, mx+ox, my+oy); cr.rotate(c, w*tau); cr.translate(c, -mx, -my)
            cr.new_path(c); cr.arc(c, CX, CY, RING_R, a0+0.012, a1-0.012); cr.stroke(c); cr.restore(c)
    # balls
    P = pos[off[fi]:off[fi+1]]; K = col[off[fi]:off[fi+1]]
    for ci in range(7):
        sel = P[K == ci]
        if not len(sel): continue
        cr.set_rgb(c, *PAL[ci]); cr.new_path(c)
        for (x, y) in sel:
            if -30 < x < W+30 and -30 < y < H+30:
                cr.new_sub_path(c); cr.arc(c, float(x), float(y), BR, 0, 2*math.pi)
        cr.fill(c)
    hammer(float(theta[fi]))
    cr.flush(s)
    ff.stdin.write(C.string_at(buf, stride*H))
ff.stdin.close(); ff.wait()
print('frames', nfr, 'dur', nfr/FPS, 'crack', t_crack, 'boom', t_boom)
