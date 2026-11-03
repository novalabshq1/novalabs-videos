# Screamer validé par Yanis (version 1) : visage qui surgit 0,9 s. Usage : python3 screamer.py  -> scream_v.mp4
import cr, math, ctypes, subprocess, numpy as np
W, H, FPS, DUR = 1080, 1920, 60, 0.9
s = cr.surface_create(0, W, H); c = cr.create(s); st = cr.get_stride(s)
rng = np.random.default_rng(21)
ff = subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgra','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
    '-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p','scream_v.mp4'], stdin=subprocess.PIPE)
def radial(x, y, r0, r1, stops):
    g = cr.pattern_radial(x, y, r0, x, y, r1)
    for o, rgba in stops: cr.add_stop(g, o, *rgba)
    return g
def blob(x, y, rx, ry, stops, jag=0.0, seed=0):
    r = np.random.default_rng(seed)
    cr.save(c); cr.translate(c, x, y); cr.scale(c, rx, ry)
    cr.new_path(c)
    for k in range(40):
        a = 2 * math.pi * k / 40; rr = 1 + jag * r.uniform(-1, 1)
        (cr.move_to if k == 0 else cr.line_to)(c, rr * math.cos(a), rr * math.sin(a))
    cr.close_path(c)
    g = radial(0, 0, 0, 1.15, stops); cr.set_source(c, g); cr.fill(c); cr.pattern_destroy(g)
    cr.restore(c)
mouth_teeth = [(k, rng.uniform(0.6, 1.4)) for k in range(-3, 4)]
n = int(DUR * FPS)
for i in range(n):
    t = i / FPS
    z = 1.0 + 0.38 * (1 - math.exp(-t / 0.12))
    dx, dy = rng.normal(0, 18), rng.normal(0, 18)
    cr.identity_matrix(c); cr.set_rgb(c, 0, 0, 0); cr.paint(c)
    cr.translate(c, W/2 + dx, H/2 + dy); cr.scale(c, z, z); cr.translate(c, -W/2, -H/2)
    cx, cy = W/2, H/2
    # head emerging from darkness
    blob(cx, cy, 470, 680, [(0, (0.80, 0.80, 0.74, 1)), (0.55, (0.55, 0.55, 0.50, 1)), (0.85, (0.12, 0.11, 0.10, 1)), (1, (0, 0, 0, 0))], 0.04, 1)
    # deep eye sockets
    for sx in (-1, 1):
        blob(cx + sx*175, cy-170, 190, 175, [(0, (0, 0, 0, 1)), (0.6, (0.02, 0, 0, 1)), (1, (0.2, 0.18, 0.16, 0))], 0.12, 2 + sx)
        pr = 9 + 4 * math.sin(t * 40)
        blob(cx + sx*175 + rng.uniform(-4, 4), cy-160, pr, pr, [(0, (1, 1, 0.95, 1)), (1, (1, 0.2, 0.1, 0))], 0, 5)
    # gaping irregular mouth
    mo = 0.55 + 0.45 * min(1, t / 0.18)
    blob(cx, cy+300, 210, 300*mo, [(0, (0, 0, 0, 1)), (0.75, (0.05, 0, 0, 1)), (1, (0.25, 0.15, 0.12, 0))], 0.10, 7)
    for k, L in mouth_teeth:
        x = cx + k*48; y0 = cy + 300 - 255*mo
        cr.new_path(c); cr.move_to(c, x-18, y0); cr.line_to(c, x+18, y0); cr.line_to(c, x + rng.uniform(-4, 4), y0 + 90*L*mo); cr.close_path(c)
        cr.set_rgba(c, 0.85, 0.82, 0.68, 0.95); cr.fill(c)
    cr.flush(s)
    img = np.frombuffer(ctypes.string_at(cr.get_data(s), st*H), np.uint8).reshape(H, st//4, 4)[:, :W].astype(np.int16).copy()
    # post: grain, red tint, RGB split, flicker
    img[..., :3] += rng.normal(0, 22, (H, W, 1)).astype(np.int16)
    img[..., 2] = np.roll(img[..., 2], 9, axis=1) + 25        # red channel (BGRA) shifted + tinted
    img[..., 0] = img[..., 0] * 0.7                             # less blue
    if rng.random() < 0.25: img[..., :3] = img[..., :3] * 0.35   # flicker frames
    img = np.clip(img, 0, 255).astype(np.uint8)
    ff.stdin.write(img.tobytes())
ff.stdin.close(); ff.wait(); print('frames', n)
