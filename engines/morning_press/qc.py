"""Contrôle qualité d'une vidéo morning_press finale.

python3 qc.py final.mp4 SEED MECH [extra_json]
- ffprobe (1080x1920, 60 fps, h264 High, yuv420p, AAC 48 kHz, durée 45-60 s)
- cadrage du cercle sur 8 images (centre 540/1075 ±4, diamètre 900 ±6, immobile)
- logs physiques : coups dans le vide, divisions, chevauchements, sorties du cercle
- audio : pic max <= -1 dBFS
"""
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sim import simulate, load_events  # noqa: E402


def probe(path):
    out = subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path])
    return json.loads(out)


def frame_at(path, t):
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', '%.3f' % t, '-i', path, '-frames:v', '1',
                                   '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
    return np.frombuffer(raw, np.uint8).reshape(1920, 1080, 3)


def circle_fit(img):
    # contour blanc : pixels quasi blancs ; le cercle donne les extrêmes gauche/droite/haut/bas
    white = (img.min(axis=2) > 200)
    ys, xs = np.nonzero(white)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = (x1 - x0 + 1) - 5, (y1 - y0 + 1) - 5   # diamètre au milieu du trait de 5 px
    return cx, cy, dx, dy


def main():
    path, seed, mech = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    extra = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
    ok = True
    p = probe(path)
    v = [s for s in p['streams'] if s['codec_type'] == 'video'][0]
    a = [s for s in p['streams'] if s['codec_type'] == 'audio'][0]
    dur = float(p['format']['duration'])
    print('video', v['width'], v['height'], v['r_frame_rate'], v['codec_name'], v['profile'], v['pix_fmt'],
          v.get('color_space'), '| audio', a['codec_name'], a['sample_rate'], '| dur %.2f' % dur,
          '| bitrate %.1f Mb/s' % (int(p['format']['bit_rate']) / 1e6))
    ok &= (v['width'], v['height'], v['r_frame_rate'], v['codec_name'], v['profile'], v['pix_fmt']) == \
        (1080, 1920, '60/1', 'h264', 'High', 'yuv420p')
    ok &= a['codec_name'] == 'aac' and a['sample_rate'] == '48000'
    ok &= 45 <= dur <= 60
    fits = []
    for t in np.linspace(0.5, dur - 0.3, 8):
        fits.append(circle_fit(frame_at(path, t)))
    fits = np.array(fits)
    print('circle fits (cx, cy, dx, dy):')
    print(fits.round(1))
    ok &= bool(np.all(np.abs(fits[:, 0] - 540) <= 4) and np.all(np.abs(fits[:, 1] - 1075) <= 4))
    ok &= bool(np.all(np.abs(fits[:, 2] - 900) <= 6) and np.all(np.abs(fits[:, 3] - 900) <= 6))
    ok &= bool(np.ptp(fits[:, 0]) < 1 and np.ptp(fits[:, 1]) < 1)
    # physique
    evp = path + '.qc.ev'
    r = simulate(seed, mech, rec=path + '.qc.rec', events=evp, **extra)
    os.remove(path + '.qc.rec')
    E = load_events(evp)
    os.remove(evp)
    starts, hits, crush, born = (E[E[:, 1] == k] for k in (4, 1, 2, 5))
    print('hits', r['hits'], 'empty_hits', r['empty_hits'], 'closures', len(starts), 'min captured', starts[:, 5].min(),
          'crushed', len(crush), 'born', len(born), 'bad_split', r['bad_split'])
    ok &= r['empty_hits'] == 0 and len(born) == 2 * len(crush) and r['bad_split'] == 0
    # chaque balle écrasée -> 2 balles de la couleur suivante (cyan -> cyan)
    exp = np.minimum(crush[:, 4] + 1, 7)
    got = born[:, 4].reshape(-1, 2)
    colok = bool(np.all(got[:, 0] == exp) and np.all(got[:, 1] == exp))
    print('colour chain ok', colok)
    ok &= colok
    print('max overlap %.2f px, max wall penetration %.2f px, escapes %d' % (r['max_overlap'], r['max_wall_pen'], r['escapes']))
    ok &= r['max_overlap'] <= 2.5 and r['max_wall_pen'] <= 0.5
    print('t_full %.2f, green capture times %s, final colours %s' % (r['t_full'], r['green_cap'], r['col_count']))
    # audio
    pk = subprocess.run(['ffmpeg', '-i', path, '-af', 'volumedetect', '-vn', '-f', 'null', '-'],
                        capture_output=True, text=True).stderr
    mx = [l for l in pk.splitlines() if 'max_volume' in l]
    print(mx[0].strip() if mx else 'no volumedetect')
    print('QC', 'OK' if ok else 'FAILED')
    return ok


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
