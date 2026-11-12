"""Rendu 1080x1920 60 fps d'une partie morning_press + export final (qualité TikTok) avec l'audio.

python3 render.py SEED MECH audio.wav out.mp4 [extra_json] [--frames 0,60,600 --png-dir DIR]
  extra_json : réglages supplémentaires passés à la simulation (ex. la fente de LA TRICHEUSE)
"""
import ctypes as C
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cr  # noqa: E402
from sim import simulate, load_record, COLORS, CX, CY, R, MECHS  # noqa: E402

WIDTH, HEIGHT, FPS = 1080, 1920, 60
BLOCK = '#C9CCD4'   # gris clair plat
ROD = '#B8BCC6'
PLATE = '#D6D9E0'
RIVET = '#5E636E'
OUTLINE = (1, 1, 1)

FFMPEG_VIDEO = ['-c:v', 'libx264', '-profile:v', 'high', '-level', '4.2', '-pix_fmt', 'yuv420p', '-preset', 'slow',
                '-crf', '14', '-maxrate', '25M', '-bufsize', '50M', '-g', '120', '-colorspace', 'bt709',
                '-color_primaries', 'bt709', '-color_trc', 'bt709']
FFMPEG_AUDIO = ['-c:a', 'aac', '-b:a', '320k', '-ar', '48000']


def hexrgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


RGB = [hexrgb(c) for c in COLORS]


def rect_ab(ctx, axis, a0, a1, b0, b1):
    """rectangle dans le repère du mécanisme (a = axe de fermeture, b = travers)."""
    if axis == 0:
        cr.rectangle(ctx, CX + b0, CY + a0, b1 - b0, a1 - a0)
    else:
        cr.rectangle(ctx, CX + a0, CY + b0, a1 - a0, b1 - b0)


def pt_ab(axis, a, b):
    return (CX + b, CY + a) if axis == 0 else (CX + a, CY + b)


def fill_stroke(ctx, rgb, lw=3.0):
    cr.set_rgb(ctx, *rgb)
    cr.fill_preserve(ctx)
    cr.set_rgb(ctx, *OUTLINE)
    cr.set_line_width(ctx, lw)
    cr.stroke(ctx)


def draw_press(ctx, m, f):
    axis, W, H, rw = m['axis'], m['W'], m['H'], m['rod_w']
    hw = W / 2
    cr.save(ctx)
    cr.new_path(ctx)
    cr.arc(ctx, CX, CY, R - 2.5, 0, 2 * math.pi)
    cr.clip(ctx)
    cr.new_path(ctx)
    for s in (-1, 1):
        # tige (piston) jusqu'au bord du cercle
        a_in, a_out = f + H, R + 20
        rect_ab(ctx, axis, *(sorted((s * a_in, s * a_out))), -rw / 2, rw / 2)
        fill_stroke(ctx, hexrgb(ROD))
        # bloc
        a0, a1 = sorted((s * f, s * (f + H)))
        rect_ab(ctx, axis, a0, a1, -hw, hw)
        fill_stroke(ctx, hexrgb(BLOCK))
        # plaque de frappe le long de la face
        pa0, pa1 = sorted((s * f, s * (f + 16)))
        rect_ab(ctx, axis, pa0, pa1, -hw, hw)
        fill_stroke(ctx, hexrgb(PLATE), 3.0)
        # rivets
        cr.set_rgb(ctx, *hexrgb(RIVET))
        for bb in (-hw + 22, -hw / 3, hw / 3, hw - 22):
            x, y = pt_ab(axis, s * (f + H - 20), bb)
            cr.new_path(ctx)
            cr.arc(ctx, x, y, 5.0, 0, 2 * math.pi)
            cr.fill(ctx)
        for k in range(1, 4):
            x, y = pt_ab(axis, s * (f + H + 40 * k), 0)
            if math.hypot(x - CX, y - CY) < R - 12:
                cr.new_path(ctx)
                cr.arc(ctx, x, y, 4.0, 0, 2 * math.pi)
                cr.fill(ctx)
    cr.restore(ctx)


def draw_jaws(ctx, m, f):
    """MÂCHOIRES : 2 demi-disques (faces plates face à face), une tige chacun jusqu'au bord du cercle."""
    axis, W, rw = m['axis'], m['W'], m['rod_w']
    Rj = W / 2
    cr.save(ctx)
    cr.new_path(ctx)
    cr.arc(ctx, CX, CY, R - 2.5, 0, 2 * math.pi)
    cr.clip(ctx)
    cr.new_path(ctx)
    for s in (-1, 1):
        # tige
        a_in, a_out = f + Rj - 6, R + 20
        rect_ab(ctx, axis, *(sorted((s * a_in, s * a_out))), -rw / 2, rw / 2)
        fill_stroke(ctx, hexrgb(ROD))
        # demi-disque : centre sur la face (a = s*f), bombé vers l'extérieur
        cx, cy = pt_ab(axis, s * f, 0)
        if axis == 0:
            a0 = math.pi if s < 0 else 0.0   # s = -1 : moitié haute (y < cy)
        else:
            a0 = math.pi / 2 if s < 0 else -math.pi / 2
        cr.new_path(ctx)
        cr.arc(ctx, cx, cy, Rj, a0, a0 + math.pi)
        cr.close_path(ctx)
        fill_stroke(ctx, hexrgb(BLOCK))
        # bande de frappe le long de la face plate (dans le demi-disque)
        cr.save(ctx)
        cr.new_path(ctx)
        cr.arc(ctx, cx, cy, Rj - 1.5, a0, a0 + math.pi)
        cr.close_path(ctx)
        cr.clip(ctx)
        cr.new_path(ctx)
        pa0, pa1 = sorted((s * f, s * (f + 18)))
        rect_ab(ctx, axis, pa0, pa1, -Rj, Rj)
        fill_stroke(ctx, hexrgb(PLATE), 3.0)
        cr.restore(ctx)
        # contour net par-dessus
        cr.new_path(ctx)
        cr.arc(ctx, cx, cy, Rj, a0, a0 + math.pi)
        cr.close_path(ctx)
        cr.set_rgb(ctx, *OUTLINE)
        cr.set_line_width(ctx, 3.0)
        cr.stroke(ctx)
        # rivets : un arc de rivets dans le dôme + le moyeu
        cr.set_rgb(ctx, *hexrgb(RIVET))
        for k in range(5):
            th = math.radians(30 + 30 * k)          # 30..150° dans le dôme
            u, v = (Rj - 26) * math.sin(th), (Rj - 26) * math.cos(th)
            x, y = pt_ab(axis, s * (f + u), v)
            cr.new_path(ctx)
            cr.arc(ctx, x, y, 5.0, 0, 2 * math.pi)
            cr.fill(ctx)
        x, y = pt_ab(axis, s * (f + 62), 0)
        cr.new_path(ctx)
        cr.arc(ctx, x, y, 9.0, 0, 2 * math.pi)
        cr.fill(ctx)
    cr.restore(ctx)


def draw_frame(ctx, frame, m, slit=None):
    t, f, ph, arr = frame
    cr.set_rgb(ctx, 0, 0, 0)
    cr.paint(ctx)
    # balles
    order = np.argsort(arr[:, 1], kind='stable')
    for k in order:
        _, col, x, y, r, _ = arr[k]
        cr.set_rgb(ctx, *RGB[int(col)])
        cr.new_path(ctx)
        cr.arc(ctx, float(x), float(y), float(r), 0, 2 * math.pi)
        cr.fill(ctx)
    (draw_jaws if m.get('mech') == 1 else draw_press)(ctx, m, f)
    # cercle : contour blanc 5 px, rayon 450 (diamètre 900)
    cr.set_rgb(ctx, *OUTLINE)
    cr.set_line_width(ctx, 5.0)
    cr.new_path(ctx)
    if slit:
        ang, w = slit
        half = (w / 2) / R
        cr.arc(ctx, CX, CY, R, ang + half, ang - half + 2 * math.pi)
    else:
        cr.arc(ctx, CX, CY, R, 0, 2 * math.pi)
    cr.stroke(ctx)


def main():
    seed, mech, wav, out = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
    extra = json.loads(sys.argv[5]) if len(sys.argv) > 5 and not sys.argv[5].startswith('--') else {}
    png_frames, png_dir = None, None
    if '--frames' in sys.argv:
        png_frames = [int(x) for x in sys.argv[sys.argv.index('--frames') + 1].split(',')]
        png_dir = sys.argv[sys.argv.index('--png-dir') + 1]
        os.makedirs(png_dir, exist_ok=True)
    rec = out + '.rec.bin'
    res = simulate(seed, mech, rec=rec, **extra)
    frames = load_record(rec)
    os.remove(rec)
    m = MECHS[mech]
    slit = (extra['slit_ang'], extra['slit_w']) if extra.get('slit_w', 0) > 0 else None
    surf = cr.surface_create(0, WIDTH, HEIGHT)  # ARGB32
    ctx = cr.create(surf)
    stride = cr.get_stride(surf)
    assert stride == WIDTH * 4
    if png_frames is not None:
        for k in png_frames:
            draw_frame(ctx, frames[min(k, len(frames) - 1)], m, slit)
            cr.flush(surf)
            buf = C.string_at(cr.get_data(surf), stride * HEIGHT)
            img = np.frombuffer(buf, np.uint8).reshape(HEIGHT, WIDTH, 4)[:, :, [2, 1, 0]]
            path = os.path.join(png_dir, 'f%05d.ppm' % k)
            with open(path, 'wb') as fo:
                fo.write(b'P6 %d %d 255\n' % (WIDTH, HEIGHT))
                fo.write(img.tobytes())
        return
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', '%dx%d' % (WIDTH, HEIGHT),
           '-r', str(FPS), '-i', '-', '-i', wav, '-map', '0:v', '-map', '1:a',
           '-vf', 'scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int'] + \
        FFMPEG_VIDEO + FFMPEG_AUDIO + ['-shortest', '-movflags', '+faststart', out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for k, fr in enumerate(frames):
        draw_frame(ctx, fr, m, slit)
        cr.flush(surf)
        p.stdin.write(C.string_at(cr.get_data(surf), stride * HEIGHT))
        if k % 600 == 0:
            print('frame', k, '/', len(frames), flush=True)
    p.stdin.close()
    p.wait()
    print('done', out, 'frames', len(frames), 't_full', res['t_full'])


if __name__ == '__main__':
    main()
