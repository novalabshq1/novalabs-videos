"""Audio for a morning_press run. usage: python3.13 audio.py events_SEED.json OUT.wav [MODE=sfx|melody]
SFX: boom on every hit (150 -> 60 Hz + short noise), pop per crushed ball (pentatonic, pitch rises with colour),
discreet wall ticks (>= 60 ms apart), rising 'fiou' when the cheater leaves through the slit.
MELODY mode: also plays MELODY_NOTES (MIDI numbers) one note per hit, in order (fill MELODY_NOTES before using)."""
import sys, json, numpy as np

SR = 48000
ev = json.load(open(sys.argv[1])); OUT = sys.argv[2]
MODE = sys.argv[3] if len(sys.argv) > 3 else 'sfx'
MELODY_NOTES = []
dur = ev['nframes'] / 60.0
N = int(dur * SR) + SR
out = np.zeros(N)
rng = np.random.default_rng(1)
PENTA = [261.63, 293.66, 329.63, 392.00, 440.00, 523.25, 587.33, 659.25]   # green (low) ... cyan (high)


def add(t, sig):
    i = int(round(t * SR))
    if i < 0: sig = sig[-i:]; i = 0
    j = min(N, i + len(sig)); out[i:j] += sig[:j - i]


def boom():
    n = int(0.45 * SR); tt = np.arange(n) / SR
    f = 60 + 90 * np.exp(-tt / 0.07)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-tt / 0.16) * 0.62
    s += 0.18 * np.sin(2 * ph) * np.exp(-tt / 0.06)
    nz = rng.standard_normal(n); k = np.ones(12) / 12; nz = np.convolve(nz, k, 'same')
    s += 0.35 * nz * np.exp(-tt / 0.018)
    s[:48] *= np.linspace(0, 1, 48)
    return s


def pop(level, amp):
    f0 = PENTA[level]; n = int(0.13 * SR); tt = np.arange(n) / SR
    f = f0 * (1 + 0.6 * np.exp(-tt / 0.012))
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = (np.sin(ph) + 0.25 * np.sin(2 * ph)) * np.exp(-tt / 0.045)
    s[:24] *= np.linspace(0, 1, 24)
    return amp * s


def tick():
    n = int(0.012 * SR); tt = np.arange(n) / SR
    return 0.05 * np.sin(2 * np.pi * 2600 * tt) * np.exp(-tt / 0.0025)


def fiou():
    n = int(0.42 * SR); tt = np.arange(n) / SR
    f = 480 * (1800 / 480) ** (tt / tt[-1])
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = np.sin(np.pi * tt / tt[-1]) ** 1.5
    return 0.30 * np.sin(ph) * env


def note(midi, amp=0.32):
    f0 = 440 * 2 ** ((midi - 69) / 12); n = int(0.5 * SR); tt = np.arange(n) / SR
    s = (np.sin(2 * np.pi * f0 * tt) + 0.3 * np.sin(4 * np.pi * f0 * tt) + 0.1 * np.sin(6 * np.pi * f0 * tt)) * np.exp(-tt / 0.18)
    s[:48] *= np.linspace(0, 1, 48)
    return amp * s


B = boom()
crush_by_t = {}
for (t, x, y, L, L2) in ev['crush']:
    crush_by_t.setdefault(round(t, 5), []).append(L)
for hi, h in enumerate(ev['hits']):
    if 'tc' not in h: continue
    add(h['tc'], B)
    if MODE == 'melody' and MELODY_NOTES:
        add(h['tc'], note(MELODY_NOTES[hi % len(MELODY_NOTES)]))
    lv = crush_by_t.get(round(h['tc'], 5), [])
    # at most 5 pops per hit (distinct colours first), spread over 0-24 ms -> never saturates
    uniq = sorted(set(lv)); pick = uniq[:5]
    rest = [l for l in lv if l not in pick] if False else []
    while len(pick) < min(5, len(lv)): pick.append(lv[len(pick)])
    amp = 0.30 / np.sqrt(max(1, len(pick)))
    for k, L in enumerate(pick):
        add(h['tc'] + 0.006 * k, pop(L, amp))
T = tick()
last = -1
for t in ev['wall']:
    if t - last >= 0.06: add(t, T); last = t
for e in ev['escape']:
    add(e['t'] - 0.06, fiou())
out = out[:int(dur * SR)]
peak = np.abs(out).max(); out *= 10 ** (-1.2 / 20) / peak
pcm = (out * 32767).astype(np.int16)
import wave
w = wave.open(OUT, 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
w.writeframes(np.repeat(pcm[:, None], 2, 1).tobytes()); w.close()
print('audio', OUT, 'dur', dur, 'peak dBFS', 20 * np.log10(np.abs(out).max()))
