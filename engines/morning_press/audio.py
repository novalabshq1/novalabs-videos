"""Son morning_press (48 kHz, stéréo) à partir des événements de la simulation.

python3 audio.py SEED MECH out.wav [extra_json] [--melody NOTES]
  Mode BRUITAGES (défaut) : boom à chaque coup, pop par balle écrasée (hauteur = couleur, pentatonique),
  tic discret aux rebonds sur le cercle (max 1 / 60 ms), « fiou » montant pour une balle qui sort par la fente.
  Mode MÉLODIE : --melody "E5:1,D5:1,..." -> chaque coup joue la note suivante (synthé), en plus des bruitages.
"""
import json
import math
import os
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sim import simulate, load_events  # noqa: E402

SR = 48000
# pop : vert grave -> cyan aigu, gamme pentatonique majeure (sol)
POP_HZ = [196.00, 220.00, 246.94, 293.66, 329.63, 392.00, 440.00, 493.88]


def note_hz(name):
    names = {'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3, 'E': 4, 'F': 5, 'F#': 6, 'GB': 6, 'G': 7,
             'G#': 8, 'AB': 8, 'A': 9, 'A#': 10, 'BB': 10, 'B': 11}
    n = name.upper()
    octave = int(n[-1])
    semi = names[n[:-1]]
    midi = 12 * (octave + 1) + semi
    return 440.0 * 2 ** ((midi - 69) / 12)


def boom(rng):
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    freq = 58 + 95 * np.exp(-t / 0.045)
    ph = 2 * np.pi * np.cumsum(freq) / SR
    body = np.sin(ph) * np.exp(-t / 0.13) * np.minimum(1, t / 0.002)
    body += 0.25 * np.sin(2 * ph) * np.exp(-t / 0.05)
    noise = rng.standard_normal(n)
    # passe-bas simple pour un choc sourd
    lp = np.zeros(n)
    a = 0.12
    acc = 0.0
    for i in range(int(0.06 * SR)):
        acc += a * (noise[i] - acc)
        lp[i] = acc
    lp *= np.exp(-t / 0.018) * 2.2
    return 0.85 * body + 0.35 * lp


def pop(hz):
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    freq = hz * 2 * (1 + 0.6 * np.exp(-t / 0.012))
    ph = 2 * np.pi * np.cumsum(freq) / SR
    env = np.exp(-t / 0.045) * np.minimum(1, t / 0.0015)
    return (np.sin(ph) + 0.3 * np.sin(2 * ph)) * env


def tic(rng):
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * 2600 * t) * np.exp(-t / 0.006)
    s += 0.4 * rng.standard_normal(n) * np.exp(-t / 0.002)
    return s


def fiou():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    freq = 500 * 2 ** (t / 0.45 * 1.6)
    ph = 2 * np.pi * np.cumsum(freq) / SR
    env = np.sin(np.pi * t / t[-1]) ** 1.5
    return np.sin(ph) * env


def synth_note(hz, dur=0.42):
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.minimum(1, t / 0.004) * np.exp(-t / 0.22)
    s = np.sin(2 * np.pi * hz * t) + 0.35 * np.sin(4 * np.pi * hz * t) * np.exp(-t / 0.08) \
        + 0.12 * np.sin(6 * np.pi * hz * t) * np.exp(-t / 0.05)
    return s * env


def add(buf, sig, t, gain):
    i = int(round(t * SR))
    if i < 0 or i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += gain * sig[:j - i]


def main():
    seed, mech, out = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    extra = json.loads(sys.argv[4]) if len(sys.argv) > 4 and not sys.argv[4].startswith('--') else {}
    melody = None
    if '--melody' in sys.argv:
        melody = [x.split(':')[0] for x in sys.argv[sys.argv.index('--melody') + 1].split(',')]
    evp = out + '.ev.bin'
    res = simulate(seed, mech, events=evp, **extra)
    E = load_events(evp)
    os.remove(evp)
    # durée = nombre d'images rendues / 60
    nframes = int(math.floor(res['t_end'] * 60 + 1e-6)) + 1
    dur = nframes / 60.0
    buf = np.zeros(int(dur * SR) + SR)
    rng = np.random.default_rng(seed)
    b = boom(rng)
    pops = [pop(h) for h in POP_HZ]
    hits = E[E[:, 1] == 1]
    starts = E[E[:, 1] == 4]
    crushes = E[E[:, 1] == 2]
    for k, h in enumerate(hits):
        add(buf, b, h[0], 0.9)
        if melody:
            add(buf, synth_note(note_hz(melody[k % len(melody)])), h[0], 0.45)
    # pops : au plus 5 par coup (sous-ensemble régulier), au moment exact de l'écrasement
    for k, s in enumerate(starts):
        t0 = s[0]
        t1 = hits[k][0] if k < len(hits) else t0 + 0.3
        c = crushes[(crushes[:, 0] >= t0 - 1e-4) & (crushes[:, 0] <= t1 + 0.07)]
        if len(c) == 0:
            continue
        idx = np.unique(np.linspace(0, len(c) - 1, min(5, len(c))).round().astype(int))
        g = 0.32 if len(idx) == 1 else 0.32 / math.sqrt(len(idx)) * 1.3
        for jj, i in enumerate(idx):
            add(buf, pops[int(c[i, 4])], c[i, 0] + 0.004 * jj, g)
    # tics de rebond sur le cercle : max 1 toutes les 60 ms
    last = -1
    tc = tic(rng)
    for e in E[E[:, 1] == 3]:
        if e[0] - last >= 0.060:
            add(buf, tc, e[0], 0.07)
            last = e[0]
    for e in E[E[:, 1] == 6]:
        add(buf, fiou(), e[0] - 0.12, 0.35)
    buf = buf[:int(dur * SR)]
    peak = np.abs(buf).max()
    target = 10 ** (-1.2 / 20)
    buf *= target / peak
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    st = np.stack([pcm, pcm], 1)
    with wave.open(out, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(st.tobytes())
    print('audio', out, '%.3fs' % dur, 'hits', len(hits), 'crushes', len(crushes), 'peak dBFS %.2f' % (20 * math.log10(np.abs(pcm).max() / 32767)))


if __name__ == '__main__':
    main()
