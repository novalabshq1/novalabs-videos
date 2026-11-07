# Usage: python3 audio_esc.py DURATION SCREAM_T  -> esc_audio.wav (game sfx peak -8 dBFS, scream peak -1 dBFS)
import numpy as np, wave, sys
SR = 48000; DUR = float(sys.argv[1]); SCT = float(sys.argv[2]); SCD = 0.6
ev = np.load('esc_events.npy'); rng = np.random.default_rng(5)
N = int(DUR * SR) + SR; L = np.zeros(N); Rr = np.zeros(N)
def add(sig, t, g, pan=0.5):
    i = int(t * SR); j = min(N, i + len(sig)); s = sig[:j - i] * g
    L[i:j] += s * np.sqrt(1 - pan); Rr[i:j] += s * np.sqrt(pan)
def env(n, tau, att=0.0006):
    t = np.arange(n) / SR; return np.exp(-t / tau) * (1 - np.exp(-t / att)), t
def wood(f):            # wood / marimba "toc"
    e, t = env(int(0.16 * SR), 0.045)
    return (np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * 3.93 * f * t) * np.exp(-t / 0.012)) * e \
        + 0.12 * rng.standard_normal(len(t)) * np.exp(-t / 0.002)
def die():              # spike hit: crunch-pop, ~820 -> 120 Hz, 0.3 s
    n = int(0.3 * SR); t = np.arange(n) / SR
    fr = 120 + 700 * np.exp(-t / 0.02)
    s = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t / 0.07)
    nz = np.convolve(rng.standard_normal(n), np.ones(5) / 5, 'same') * np.exp(-t / 0.012)
    return 0.8 * s + 0.6 * nz
def spawn():
    e, t = env(int(0.12 * SR), 0.04)
    fr = 500 + 600 * (1 - np.exp(-t / 0.03))
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * e
def escape():
    n = int(1.6 * SR); t = np.arange(n) / SR; out = np.zeros(n)
    sw = rng.standard_normal(n) * np.exp(-((t - 0.25) / 0.18) ** 2)
    sw = np.convolve(sw, np.ones(8) / 8, 'same'); out += 0.35 * sw
    for k, f in enumerate([523.25, 659.25, 783.99, 1046.5]):
        i = int((0.05 + 0.07 * k) * SR); m = n - i; tt = np.arange(m) / SR
        out[i:] += (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt / 0.45) * (1 - np.exp(-tt / 0.003)) * 0.5
    return out
penta = [261.63, 293.66, 329.63, 392.0, 440.0, 523.25]
caps = [t for t, k, x in ev if int(k) == 5]
for t, k, x in ev:
    k = int(k)
    if k == 0 and not any(abs(t - c) < 1e-6 for c in caps):
        add(wood(penta[rng.integers(len(penta))] * 2), t, 0.15 + 0.3 * x, rng.uniform(0.3, 0.7))
    elif k == 1: add(wood(penta[rng.integers(len(penta))]), t, 0.25 + 0.45 * x, rng.uniform(0.3, 0.7))
    elif k == 5: add(wood(penta[rng.integers(len(penta))] * 4), t, 0.45, rng.uniform(0.35, 0.65))   # gap edge: higher tok
    elif k == 2: add(die(), t, 0.6)
    elif k == 3: add(spawn(), t, 0.12)
    elif k == 4: add(escape(), t, 0.5)
mix = np.stack([L, Rr], 1)[:int(DUR * SR)]
mix = np.tanh(mix * 1.3) / np.tanh(1.3)
mix = mix / np.abs(mix).max() * 10 ** (-8 / 20)                     # game peak -8 dBFS
mix *= np.minimum(1, (len(mix) - np.arange(len(mix))) / (0.3 * SR))[:, None]
# ---- screamer: detuned saws rising +35 %, 38 Hz vibrato, noise, 55 Hz hit, tanh drive; 4 ms attack, peak -1 dBFS
m = int(SCD * SR); t = np.arange(m) / SR
rise = 1 + 0.35 * (t / SCD) ** 0.7
vib = 1 + 0.03 * np.sin(2 * np.pi * 38 * t)
def saw(f):
    ph = np.cumsum(f * rise * vib) / SR
    return 2 * (ph % 1.0) - 1
sc = sum(saw(f) for f in (620, 655, 940, 1310)) / 4
sc += 0.35 * np.convolve(rng.standard_normal(m), np.ones(2) / 2, 'same')
sc += 1.2 * np.sin(2 * np.pi * 55 * t) * np.exp(-t / 0.12)
sc = np.tanh(3.0 * sc)
sc *= np.minimum(1, t / 0.004) * np.minimum(1, (SCD - t) / 0.006)
sc = sc / np.abs(sc).max() * 10 ** (-1 / 20)
i = int(round(SCT * SR)); j = min(len(mix), i + m)
mix[i:j] *= 0.05                                                     # everything else drops to 5 %
mix[i:j] += sc[:j - i, None] * np.array([1.0, 1.0])
mix = np.clip(mix, -0.99, 0.99)
w = wave.open('esc_audio.wav', 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
w.writeframes((mix * 32767).astype(np.int16).tobytes()); w.close(); print('audio ok, scream at', SCT)
