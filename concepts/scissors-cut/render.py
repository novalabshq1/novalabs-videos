"""Scissors Cut — renderer. PHIMAX=38 python3 render.py sim.npz out_lossless.mkv [frame_list_for_png]"""
import sys, math, subprocess, ctypes as C, numpy as np
import cr
from sim import (CX, CY, R_OUT, RING_W, BR, BL, HW0, HWT, ARM_L, ARM_HW, LOOP_D, LOOP_R, LOOP_HOLE,
                 HANDLE_OFF, HUB_R, FPS, parts)
W, H = 1080, 1920
TITLE = b"EVERY CUT MAKES 4 BALLS"
BG = (0x05/255, 0x07/255, 0x0D/255)
PAL = ["#FF7A1A", "#2E7BFF", "#FF2E43", "#FFD21F", "#FF4FB4", "#2EDB5A", "#1FD6F0"]
PAL = [tuple(int(h[i:i+2], 16)/255 for i in (1, 3, 5)) for h in PAL]
GREY = (0xC8/255, 0xCC/255, 0xD5/255); RIVET = (0x4A/255, 0x4E/255, 0x57/255)
RING_R = R_OUT - RING_W/2
d = np.load(sys.argv[1]); out = sys.argv[2]
only = set(int(x) for x in sys.argv[3].split(',')) if len(sys.argv) > 3 else None
pos, col, off, theta, phi = d['pos'], d['col'], d['off'], d['theta'], d['phi']
ev_t, ev_k = d['ev_t'], d['ev_k']
t_crack = float(ev_t[ev_k == 'crack_start'][0]); t_boom = float(ev_t[ev_k == 'boom'][0])
nfr = min(len(theta), int(round((t_boom + 1.8) * FPS)))
rng = np.random.default_rng(7)
stars = []
while len(stars) < 70:
    x, y = rng.uniform(10, W-150), rng.uniform(10, H-260)
    if math.hypot(x-CX, y-CY) < R_OUT + 24: continue
    if 370 < y < 465 and 70 < x < 1010: continue
    stars.append((x, y, rng.uniform(1.0, 1.5), rng.uniform(0.3, 0.8)))
NCR = 16
crack_a = np.sort(rng.uniform(0, 2*np.pi, NCR)); crack_order = rng.permutation(NCR)
bounds = np.append(crack_a, crack_a[0] + 2*np.pi)
frags = [(bounds[i], bounds[i+1], rng.uniform(650, 1000), rng.uniform(-4, 4)) for i in range(NCR)]
s = cr.surface_create(0, W, H); c = cr.create(s)
stride = cr.get_stride(s); buf = cr.get_data(s)
ff = None
if only is None:
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}', '-r', str(FPS),
                           '-i', '-', '-c:v', 'libx264', '-qp', '0', '-preset', 'ultrafast', '-pix_fmt', 'yuv444p', out], stdin=subprocess.PIPE)
cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
te = cr.TE(); cr.text_extents(c, TITLE, C.byref(te))
tx = 540 - (te.xb + te.w/2)
print('title width', te.w)
I = 1.5  # inset so the 3 px white outline is centred 1.5 px inside the collision shape edge... outline outer edge = shape edge
def rivet(x, y, r=4.5):
    cr.new_path(c); cr.arc(c, x, y, r, 0, 2*math.pi); cr.set_rgb(c, *RIVET); cr.fill(c)
def fill_stroke():
    cr.set_rgb(c, *GREY); cr.fill_preserve(c); cr.set_rgb(c, 1, 1, 1); cr.stroke(c)
def tapered(u0, u1, h0, h1):
    """capsule tapering from half-width h0 at u0 to h1 at u1, in current local frame"""
    L = u1 - u0; a = math.asin((h0 - h1) / L)
    cr.new_path(c)
    cr.arc(c, u1, 0, h1 - I, -math.pi/2 + a, math.pi/2 - a)
    cr.arc(c, u0, 0, h0 - I, math.pi/2 - a, 3*math.pi/2 + a)
    cr.close_path(c)
def half(ang, hang, flip):
    # handle: arm + loop with a hole
    cr.save(c); cr.translate(c, CX, CY); cr.rotate(c, hang)
    cr.new_path(c); cr.rectangle(c, 0, -ARM_HW + I, LOOP_D - LOOP_R + 6, 2*(ARM_HW - I)); fill_stroke()
    cr.set_fill_rule(c, 1)
    cr.new_path(c); cr.arc(c, LOOP_D, 0, LOOP_R - I, 0, 2*math.pi)
    cr.new_sub_path(c); cr.arc_negative(c, LOOP_D, 0, LOOP_HOLE + I, 2*math.pi, 0)
    fill_stroke(); cr.set_fill_rule(c, 0)
    cr.new_path(c); cr.arc(c, LOOP_D, 0, LOOP_HOLE, 0, 2*math.pi); cr.set_rgb(c, *BG); cr.fill(c)
    cr.new_path(c); cr.arc(c, LOOP_D, 0, LOOP_HOLE + I, 0, 2*math.pi); cr.set_line_width(c, 3); cr.set_rgb(c, 1, 1, 1); cr.stroke(c)
    rivet(ARM_L * 0.6, 0, 3.5)
    cr.restore(c)
    # blade
    cr.save(c); cr.translate(c, CX, CY); cr.rotate(c, ang)
    tapered(0, BL, HW0, HWT); fill_stroke()
    for u in (110, 200, 280): rivet(u, 0, 3.5)
    cr.restore(c)
cr.set_line_width(c, 3); cr.set_line_join(c, 1)
for fi in range(nfr):
    if only is not None and fi not in only: continue
    t = (fi + 1) / FPS
    cr.set_rgb(c, *BG); cr.paint(c)
    for (x, y, r, a) in stars:
        cr.new_path(c); cr.arc(c, x, y, r, 0, 2*math.pi); cr.set_rgba(c, 1, 1, 1, a); cr.fill(c)
    cr.set_rgb(c, 1, 1, 1); cr.move_to(c, tx, 440); cr.show_text(c, TITLE)
    cr.set_line_width(c, RING_W); cr.set_line_cap(c, 0)
    if t < t_boom:
        cr.new_path(c); cr.arc(c, CX, CY, RING_R, 0, 2*math.pi); cr.set_rgb(c, 1, 1, 1); cr.stroke(c)
        if t >= t_crack:
            k = int(NCR * min(1, (t - t_crack) / (t_boom - t_crack - 0.15)))
            cr.set_rgb(c, *BG); cr.set_line_width(c, 3)
            for q in crack_order[:k]:
                a = crack_a[q]; ca, sa = math.cos(a), math.sin(a)
                pts = [(RING_R-5, 0), (RING_R-1, 3.5), (RING_R+1, -3.5), (RING_R+5, 0)]
                cr.new_path(c)
                for j, (r, dt) in enumerate(pts):
                    (cr.move_to if j == 0 else cr.line_to)(c, CX + r*ca - dt*sa, CY + r*sa + dt*ca)
                cr.stroke(c)
    else:
        tau = t - t_boom
        cr.set_rgb(c, 1, 1, 1); cr.set_line_width(c, RING_W)
        for (a0, a1, v, w) in frags:
            am = (a0 + a1)/2; mx, my = CX + RING_R*math.cos(am), CY + RING_R*math.sin(am)
            ox, oy = math.cos(am)*v*tau, math.sin(am)*v*tau
            cr.save(c); cr.translate(c, mx+ox, my+oy); cr.rotate(c, w*tau); cr.translate(c, -mx, -my)
            cr.new_path(c); cr.arc(c, CX, CY, RING_R, a0+0.012, a1-0.012); cr.stroke(c); cr.restore(c)
    P = pos[off[fi]:off[fi+1]]; K = col[off[fi]:off[fi+1]]
    for ci in range(7):
        sel = P[K == ci]
        if not len(sel): continue
        cr.set_rgb(c, *PAL[ci]); cr.new_path(c)
        for (x, y) in sel:
            if -30 < x < W+30 and -30 < y < H+30:
                cr.new_sub_path(c); cr.arc(c, float(x), float(y), BR, 0, 2*math.pi)
        cr.fill(c)
    aA, aB, hA, hB = parts(float(theta[fi]), float(phi[fi]))
    cr.set_line_width(c, 3)
    half(aB, hB, -1); half(aA, hA, 1)
    cr.new_path(c); cr.arc(c, CX, CY, HUB_R - I, 0, 2*math.pi); fill_stroke(); rivet(CX, CY, 8)
    cr.flush(s)
    if only is not None:
        import PIL.Image
        im = PIL.Image.frombuffer('RGBA', (W, H), C.string_at(buf, stride*H), 'raw', 'BGRA', 0, 1)
        im.convert('RGB').save(f"{out}_{fi:05d}.png")
    else:
        ff.stdin.write(C.string_at(buf, stride*H))
if ff: ff.stdin.close(); ff.wait()
print('frames', nfr, 'dur', nfr/FPS, 'crack', t_crack, 'boom', t_boom)
