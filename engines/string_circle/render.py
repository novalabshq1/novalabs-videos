import sim, cr, math, ctypes, subprocess, sys, numpy as np
from sim import W, H, CX, CY, R, BR, FPS

sim.PLOW_K = 10**9
sim.POSF = float(sys.argv[4]); sim.SPREAD = float(sys.argv[5]); sim.JIT = float(sys.argv[6])
from render_spec import SPEC
SEED, SPEED, N0 = int(sys.argv[1]), int(sys.argv[3]), 35
OUT = sys.argv[2]
TITLE = b"WHO RULES SOUTH AMERICA?"

res = sim.run(SPEC, SEED, SPEED, N0, record=True)
frames = res['frames']; snaps = res['snaps']; deaths = res['deaths']
print('end', res['end_t'], 'winner', res['winner'], 'frames', len(frames), flush=True)
np.save('events.npy', np.array([(t, {'pluck':0,'tok':1,'snap':2,'pop':3,'win':4}[k], x) for t, k, x in res['events']]))

surf = cr.surface_create(0, W, H)  # ARGB32
c = cr.create(surf)
stride = cr.get_stride(surf)
cr.set_line_cap(c, 1); cr.set_line_join(c, 1)

def hexrgb(h): return tuple(int(h[i:i+2], 16) / 255 for i in (1, 3, 5))

def star(x, y, ro, ri, rot, fillrgb):
    for i in range(10):
        a = rot + i * math.pi / 5
        rr = ro if i % 2 == 0 else ri
        (cr.move_to if i == 0 else cr.line_to)(c, x + rr * math.cos(a), y + rr * math.sin(a))
    cr.close_path(c); cr.set_rgb(c, *fillrgb); cr.fill(c)

def flag(name, x, y, r):
    cr.save(c)
    cr.new_path(c); cr.arc(c, x, y, r, 0, 2 * math.pi); cr.clip(c)
    if name == "Algeria":
        cr.rectangle(c, x - r, y - r, r, 2 * r); cr.set_rgb(c, *hexrgb('#006233')); cr.fill(c)
        cr.rectangle(c, x, y - r, r, 2 * r); cr.set_rgb(c, 1, 1, 1); cr.fill(c)
        red = hexrgb('#D21034')
        cr.set_fill_rule(c, 1)
        cr.new_path(c)
        cr.arc(c, x + 0.02 * r, y, 0.5 * r, 0, 2 * math.pi)
        cr.new_sub_path(c)
        cr.arc(c, x + 0.145 * r, y, 0.375 * r, 0, 2 * math.pi)
        cr.set_rgb(c, *red); cr.fill(c)
        cr.set_fill_rule(c, 0)
        star(x + 0.2 * r, y, 0.2 * r, 0.08 * r, math.pi, red)
    elif name == "Morocco":
        cr.rectangle(c, x - r, y - r, 2 * r, 2 * r); cr.set_rgb(c, *hexrgb('#C1272D')); cr.fill(c)
        pts = [(x + 0.52 * r * math.cos(-math.pi / 2 + k * 2 * math.pi / 5),
                y + 0.52 * r * math.sin(-math.pi / 2 + k * 2 * math.pi / 5)) for k in range(5)]
        order = [0, 2, 4, 1, 3]
        cr.new_path(c)
        for i, k in enumerate(order):
            (cr.move_to if i == 0 else cr.line_to)(c, *pts[k])
        cr.close_path(c)
        cr.set_line_width(c, 0.09 * r); cr.set_rgb(c, *hexrgb('#006233')); cr.stroke(c)
    elif name == "Germany":
        for i, col in enumerate(['#000000', '#DD0000', '#FFCE00']):
            cr.rectangle(c, x - r, y - r + i * 2 * r / 3, 2 * r, 2 * r / 3 + 0.5)
            cr.set_rgb(c, *hexrgb(col)); cr.fill(c)
    elif name == "France":
        for i, col in enumerate(['#002395', '#FFFFFF', '#ED2939']):
            cr.rectangle(c, x - r + i * 2 * r / 3, y - r, 2 * r / 3 + 0.5, 2 * r)
            cr.set_rgb(c, *hexrgb(col)); cr.fill(c)
    elif name == "Colombia":
        for (y0, hh, col) in [(-1, 1.0, '#FCD116'), (0, 0.5, '#003893'), (0.5, 0.5, '#CE1126')]:
            cr.rectangle(c, x - r, y + y0 * r, 2 * r, hh * r + 0.5); cr.set_rgb(c, *hexrgb(col)); cr.fill(c)
    elif name == "Peru":
        for i, col in enumerate(['#D91023', '#FFFFFF', '#D91023']):
            cr.rectangle(c, x - r + i * 2 * r / 3, y - r, 2 * r / 3 + 0.5, 2 * r)
            cr.set_rgb(c, *hexrgb(col)); cr.fill(c)
    elif name == "Chile":
        cr.rectangle(c, x - r, y - r, 2 * r, r + 0.5); cr.set_rgb(c, 1, 1, 1); cr.fill(c)
        cr.rectangle(c, x - r, y, 2 * r, r); cr.set_rgb(c, *hexrgb('#D52B1E')); cr.fill(c)
        cr.rectangle(c, x - r, y - r, r, r); cr.set_rgb(c, *hexrgb('#0039A6')); cr.fill(c)
        star(x - 0.5 * r, y - 0.5 * r, 0.25 * r, 0.25 * r * 0.382, -math.pi / 2, (1, 1, 1))
    elif name == "Bolivia":
        for i, col in enumerate(['#DA291C', '#F4E400', '#007A33']):
            cr.rectangle(c, x - r, y - r + i * 2 * r / 3, 2 * r, 2 * r / 3 + 0.5)
            cr.set_rgb(c, *hexrgb(col)); cr.fill(c)
    cr.restore(c)

def ball(name, col, x, y):
    g = cr.pattern_radial(x, y, BR, x, y, BR + 11)
    cr.add_stop(g, 0, *col, 0.45); cr.add_stop(g, 1, *col, 0.0)
    cr.set_source(c, g); cr.new_path(c); cr.arc(c, x, y, BR + 11, 0, 2 * math.pi); cr.fill(c)
    cr.pattern_destroy(g)
    flag(name, x, y, BR)
    cr.new_path(c); cr.arc(c, x, y, BR - 1.2, 0, 2 * math.pi)
    cr.set_line_width(c, 2.6); cr.set_rgb(c, *col); cr.stroke(c)

# title metrics
cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
te = cr.TE(); cr.text_extents(c, TITLE, ctypes.byref(te))
TX = (W - te.w) / 2 - te.xb; TY = 440

rng = np.random.default_rng(7)
parts = []
for (t0, p, col) in deaths:
    for _ in range(46):
        a = rng.uniform(0, 2 * math.pi); s = rng.uniform(120, 620)
        parts.append((t0, p[0], p[1], s * math.cos(a), s * math.sin(a), rng.uniform(3, 7), col))

ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra',
                       '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast',
                       '-crf', '17', '-pix_fmt', 'yuv420p', OUT], stdin=subprocess.PIPE)
cols = [s[1] for s in SPEC]; names = [s[0] for s in SPEC]
for fi, fr in enumerate(frames):
    t = (fi + 1) / FPS
    cr.set_rgb(c, 0, 0, 0); cr.paint(c)
    # strings
    cr.set_line_width(c, 1.3)
    for (p, anc, alive), col in zip(fr, cols):
        if not alive or len(anc) == 0: continue
        cr.new_path(c)
        for a in anc:
            cr.move_to(c, p[0], p[1]); cr.line_to(c, a[0], a[1])
        cr.set_rgba(c, *col, 0.85); cr.stroke(c)
    # snapping strings: stay straight, retract to anchor and fade
    for (t0, p0, an, col) in snaps:
        s = (t - t0) / 0.15
        if s < 0 or s > 1: continue
        e = 1 - (1 - s) ** 2
        fx, fy = p0[0] + (an[0] - p0[0]) * e, p0[1] + (an[1] - p0[1]) * e
        cr.new_path(c); cr.move_to(c, an[0], an[1]); cr.line_to(c, fx, fy)
        cr.set_line_width(c, 1.3); cr.set_rgba(c, *col, 0.85 * (1 - s)); cr.stroke(c)
    # death particles
    for (t0, x0, y0, vx, vy, r0, col) in parts:
        dt = t - t0
        if dt < 0 or dt > 0.75: continue
        k = (1 - math.exp(-3 * dt)) / 3
        x, y = x0 + vx * k, y0 + vy * k
        rr = r0 * (1 - dt / 0.75)
        cr.new_path(c); cr.arc(c, x, y, rr, 0, 2 * math.pi); cr.set_rgba(c, *col, 1 - dt / 0.75); cr.fill(c)
    # arena
    cr.new_path(c); cr.arc(c, CX, CY, R, 0, 2 * math.pi)
    cr.set_line_width(c, 3); cr.set_rgb(c, 1, 1, 1); cr.stroke(c)
    # balls
    for (p, anc, alive), nm, col in zip(fr, names, cols):
        if alive: ball(nm, col, p[0], p[1])
    # title
    cr.select_font(c, b"Poppins", 0, 1); cr.set_font_size(c, 56)
    cr.move_to(c, TX, TY); cr.set_rgb(c, 1, 1, 1); cr.show_text(c, TITLE)
    cr.flush(surf)
    buf = ctypes.string_at(cr.get_data(surf), stride * H)
    ff.stdin.write(buf)
    if fi % 600 == 0: print('frame', fi, flush=True)
ff.stdin.close(); ff.wait()
print('done')
