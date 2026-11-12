# Usage: python3 audio_esc.py DUR SCREAM_T [OUT]  (reads esc_events.npy)
import numpy as np, wave, sys
SR = 48000; DUR = float(sys.argv[1]); ST = float(sys.argv[2]); OUT = sys.argv[3] if len(sys.argv) > 3 else 'esc_audio.wav'
SDUR = 0.6
ev = np.load('esc_events.npy'); rng = np.random.default_rng(5)
N = int(DUR * SR) + SR; L = np.zeros(N); Rr = np.zeros(N)
def add(sig, t, g, pan=0.5):
    i = int(t * SR); j = min(N, i + len(sig)); s = sig[:j - i] * g
    L[i:j] += s * np.sqrt(1 - pan); Rr[i:j] += s * np.sqrt(pan)
def env(n, tau, att=0.0006):
    t = np.arange(n) / SR; return np.exp(-t / tau) * (1 - np.exp(-t / att)), t
def wood(f, dec=0.035):   # wooden / marimba "toc"
    e, t = env(int(0.16 * SR), dec)
    return (np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * 3.93 * f * t) * np.exp(-t / 0.008)) * e \
        + 0.12 * rng.standard_normal(len(t)) * np.exp(-t / 0.0015)
def die():                # crunch-pop: very short noise + 820 -> 120 Hz drop, ~0.3 s
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
for t, k, x in ev:
    k = int(k)
    if k == 1: add(wood(penta[rng.integers(len(penta))]), t, 0.25 + 0.5 * x, rng.uniform(0.3, 0.7))
    elif k == 5: add(wood(2 * penta[rng.integers(3, 6)], 0.03), t, 0.45, rng.uniform(0.35, 0.65))
    elif k == 2: add(die(), t, 0.6)
    elif k == 3: add(spawn(), t, 0.12)
    elif k == 4: add(escape(), t, 0.5)
game = np.stack([L, Rr], 1)[:int(DUR * SR)]
game = np.tanh(game * 1.3) / np.tanh(1.3)
game = game / np.abs(game).max() * 10 ** (-8 / 20)            # game peak -8 dBFS
# duck to 5 % during the scream (5 ms ramps)
i0, i1 = int(ST * SR), int((ST + SDUR) * SR)
duck = np.ones(len(game)); duck[i0:i1] = 0.05
duck = np.convolve(duck, np.ones(240) / 240, 'same'); duck[i0:i1] = 0.05
game *= duck[:, None]
# scream: 4 detuned saws rising +35 %, 38 Hz vibrato, noise, 55 Hz thump, tanh distortion
n = i1 - i0; t = np.arange(n) / SR
rise = 1 + 0.35 * (t / SDUR) ** 0.8
vib = 1 + 0.025 * np.sin(2 * np.pi * 38 * t)
sc = np.zeros(n)
for f, a in ((620, 1.0), (655, 0.9), (940, 0.8), (1310, 0.6)):
    ph = np.cumsum(f * rise * vib) / SR
    sc += a * (2 * (ph % 1) - 1)
sc += 0.9 * rng.standard_normal(n)
sc += 3.0 * np.sin(2 * np.pi * 55 * t) * np.exp(-t / 0.08)
sc = np.tanh(sc * 1.6)
envs = np.minimum(1, t / 0.004) * np.minimum(1, (SDUR - t) / 0.02)
sc *= envs
sc = sc / np.abs(sc).max() * 10 ** (-1 / 20)                  # scream peak -1 dBFS
mix = game.copy(); mix[i0:i1, 0] += sc; mix[i0:i1, 1] += np.roll(sc, 18)
pk = np.abs(mix).max()
if pk > 10 ** (-1 / 20): mix *= 10 ** (-1 / 20) / pk
mix *= np.minimum(1, (len(mix) - np.arange(len(mix))) / (0.3 * SR))[:, None]
w = wave.open(OUT, 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes()); w.close(); print('ok', OUT)
