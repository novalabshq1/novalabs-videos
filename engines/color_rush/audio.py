"""COLOR RUSH — son (aucune musique, aucun son lié à la vitesse).

python3 audio.py EVENTS.json OUT.wav C|B
- fil qui casse (son principal) : UN SEUL son pour toute la vidéo, C (aigu, sec, 7 vidéos sur 10) ou B (THWACK, 3 sur 10),
  repris de engines/string_circle/audio.py ; claquement à l'instant exact de la cassure, rafale décalée de 11 ms
  quand plusieurs fils cassent dans la même image (ignoré si > 0,15 s de retard), hauteur ×0,85..1,2, panoramique varié
- balle sauvée pendant son sursis : petit pop montant discret
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


def snap_C(f):
    # C : aigu et sec, petit "tic" de fil fin qui casse (string_circle, validé)
    n = int(0.09 * SR); t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    crack = np.diff(np.diff(nz, prepend=0), prepend=0) * np.exp(-t / 0.0015)
    fi = 700 * f + 1300 * f * np.exp(-t / 0.008)
    ph = 2 * np.pi * np.cumsum(fi) / SR
    body = np.sin(ph) * np.exp(-t / 0.02) * (1 - np.exp(-t / 0.0003))
    return 0.25 * crack + 0.6 * body


def snap_B(f):
    # B : grave et épais, gros élastique qui claque "THWACK" (string_circle, validé)
    n = int(0.22 * SR); t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    crack = np.diff(nz, prepend=0) * np.exp(-t / 0.003)
    fi = 120 * f + 380 * f * np.exp(-t / 0.018)
    ph = 2 * np.pi * np.cumsum(fi) / SR
    body = (np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph)) * np.exp(-t / 0.06) * (1 - np.exp(-t / 0.0006))
    thwap = np.convolve(nz, np.ones(14) / 14, 'same') * np.exp(-t / 0.012)
    return 0.18 * crack + 0.7 * body + 0.5 * thwap


def saved_pop():
    s = sweep(500, 1100, 0.12, 0.04)
    return s * 0.6


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


def add(buf, snd, t, gain, pan=0.5):
    i = int(round(t * SR))
    j = min(len(buf), i + len(snd))
    if i < len(buf):
        s = snd[:j - i] * gain
        buf[i:j, 0] += s * np.sqrt(2 * (1 - pan))
        buf[i:j, 1] += s * np.sqrt(2 * pan)


if __name__ == '__main__':
    ev = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    SNAP = sys.argv[3].upper()
    assert SNAP in ('C', 'B')
    snap = snap_C if SNAP == 'C' else snap_B
    dur = ev['duration']
    buf = np.zeros((int(dur * SR) + SR, 2))
    # fils qui cassent : rafales par image, 11 ms d'écart, ignorés si > 0,15 s de retard
    prng = np.random.default_rng(11)
    byframe = {}
    for (tb, o, ang) in ev['breaks']:
        byframe.setdefault(int(np.ceil(tb * 60 - 1e-6)), []).append(tb)
    nsnap = skipped = 0
    last_end = -1.0
    for fi in sorted(byframe):
        for k, tb in enumerate(sorted(byframe[fi])):
            ts = max(tb + k * 0.011, last_end + 0.011 if k else tb)
            if ts - tb > 0.15:
                skipped += 1
                continue
            add(buf, snap(prng.uniform(0.85, 1.2)), ts, 0.55 if SNAP == 'C' else 0.5,
                pan=prng.uniform(0.25, 0.75))
            last_end = ts
            nsnap += 1
    print('son de fil', SNAP, 'claquements', nsnap, 'ignorés', skipped)
    SP = saved_pop()
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
        elif kind == 'saved':
            add(buf, SP, t, 0.35)
            placed.append((t, kind))
        elif kind == 'win':
            add(buf, Ch, t, 0.6)
            placed.append((t, kind))
    buf = buf[:int(dur * SR)]
    peak = np.abs(buf).max()
    buf *= 10 ** (-1 / 20) / peak
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    st = pcm
    with wave.open(out, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(st.tobytes())
    gaps = np.diff([p[0] for p in placed if p[1] in ('wall', 'ball')])
    print('sons placés', len(placed), 'écart min crunch', gaps.min() if len(gaps) else None,
          'pic dBFS', 20 * np.log10(np.abs(pcm).max() / 32767))
