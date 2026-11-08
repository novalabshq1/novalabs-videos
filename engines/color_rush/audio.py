"""COLOR RUSH — son (aucune musique, aucun son de fil, aucun son lié à la vitesse).

python3 audio.py EVENTS.json OUT.wav
- mur / choc entre balles : crunch-pop (bruit filtré + note 820 -> 120 Hz, 0,3 s), max 1 / 60 ms
- élimination : pop grave (300 -> 60 Hz, 0,5 s) + petit bruit court
- victoire : accord brillant de 4 notes montantes
Pic normalisé à -1 dBFS.
"""
import json
import sys
import wave

import numpy as np

SR = 48000
rng = np.random.default_rng(7)


def sweep(f0, f1, dur, decay):
    t = np.arange(int(dur * SR)) / SR
    f = f0 * (f1 / f0) ** (t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = np.exp(-t / decay) * np.minimum(1, t / 0.002)
    return np.sin(ph) * env


def filt_noise(dur, lo, hi, decay):
    n = int(dur * SR)
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    fr = np.fft.rfftfreq(n, 1 / SR)
    X[(fr < lo) | (fr > hi)] = 0
    y = np.fft.irfft(X, n)
    y /= np.abs(y).max() + 1e-9
    t = np.arange(n) / SR
    return y * np.exp(-t / decay)


def crunch():
    s = 0.75 * sweep(820, 120, 0.3, 0.07)
    nz = filt_noise(0.3, 900, 5000, 0.012) * 0.45
    return s + nz


def pop():
    s = sweep(300, 60, 0.5, 0.16)
    nz = filt_noise(0.5, 200, 2500, 0.02) * 0.4
    return s + nz


def chord():
    notes = [523.25, 659.25, 783.99, 1046.5]     # do mi sol do (accord, pas une mélodie)
    total = np.zeros(int(1.6 * SR))
    for i, f in enumerate(notes):
        t = np.arange(int(1.3 * SR)) / SR
        env = np.exp(-t / 0.45) * np.minimum(1, t / 0.004)
        x = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)) * env
        o = int(i * 0.07 * SR)
        total[o:o + len(x)] += x * 0.55
    return total


def add(buf, snd, t, gain):
    i = int(round(t * SR))
    j = min(len(buf), i + len(snd))
    if i < len(buf):
        buf[i:j] += snd[:j - i] * gain


if __name__ == '__main__':
    ev = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    dur = ev['duration']
    buf = np.zeros(int(dur * SR) + SR)
    C, Pp, Ch = crunch(), pop(), chord()
    last = -1.0
    placed = []
    for e in ev['events']:
        t, kind = e[0], e[1]
        if kind in ('wall', 'ball'):
            if t - last >= 0.060:
                add(buf, C, t, 0.5)
                last = t
                placed.append((t, kind))
        elif kind == 'death':
            add(buf, Pp, t, 0.9)
            placed.append((t, kind))
        elif kind == 'win':
            add(buf, Ch, t, 0.6)
            placed.append((t, kind))
    buf = buf[:int(dur * SR)]
    peak = np.abs(buf).max()
    buf *= 10 ** (-1 / 20) / peak
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    st = np.stack([pcm, pcm], axis=1)
    with wave.open(out, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(st.tobytes())
    gaps = np.diff([p[0] for p in placed if p[1] in ('wall', 'ball')])
    print('sons placés', len(placed), 'écart min crunch', gaps.min() if len(gaps) else None,
          'pic dBFS', 20 * np.log10(np.abs(pcm).max() / 32767))
