import numpy as np, wave, sys
SR = 48000; DUR = float(sys.argv[1]); TS = float(sys.argv[2]); SDUR = 0.6
ev = np.load('esc_events.npy'); rng = np.random.default_rng(5)
N = int(DUR * SR) + SR; L = np.zeros(N); Rr = np.zeros(N)
def add(sig, t, g, pan=0.5):
    i = int(t * SR); j = min(N, i + len(sig)); s = sig[:j - i] * g
    L[i:j] += s * np.sqrt(1 - pan); Rr[i:j] += s * np.sqrt(pan)
def env(n, tau, att=0.0006):
    t = np.arange(n) / SR; return np.exp(-t / tau) * (1 - np.exp(-t / att)), t
def bounce(f):          # clean marimba-like tok on the ring
    e, t = env(int(0.18 * SR), 0.05)
    return (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 3.9 * f * t) * np.exp(-t / 0.01)) * e
def wood(f):            # duller knock on grey balls
    e, t = env(int(0.12 * SR), 0.03)
    return (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * 2.7 * f * t)) * e + 0.15 * rng.standard_normal(len(t)) * np.exp(-t / 0.002)
def die():              # spike hit: crunchy pop then dull "stone" settle
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
scale = [523.25, 587.33, 659.25, 783.99, 880.0, 1046.5]   # pentatonic: every bounce sounds good
caps = set(round(t, 4) for t, k, x in ev if int(k) == 5)
low = [261.63, 293.66, 329.63, 392.0, 440.0]
for t, k, x in ev:
    k = int(k)
    if k == 0:
        f = scale[rng.integers(len(scale))] * (2 if round(t, 4) in caps else 1)   # gap edge: same tok, higher
        add(bounce(f), t, 0.14 + 0.3 * x, rng.uniform(0.3, 0.7))
    elif k == 1: add(wood(low[rng.integers(len(low))]), t, 0.18 + 0.3 * x, rng.uniform(0.3, 0.7))
    elif k == 2: add(die(), t, 0.6)
    elif k == 3: add(spawn(), t, 0.12)
    elif k == 4: add(escape(), t, 0.5)
mix = np.stack([L, Rr], 1)[:int(DUR * SR)]
mix = np.tanh(mix * 1.3) / np.tanh(1.3); mix = mix / np.abs(mix).max() * 10 ** (-8 / 20)   # game peak -8 dBFS
mix *= np.minimum(1, (len(mix) - np.arange(len(mix))) / (0.3 * SR))[:, None]
# SCREAM: 4 detuned saws rising +35 %, 38 Hz vibrato, noise, 55 Hz thump, tanh distortion
m = int(SDUR * SR); t = np.arange(m) / SR
rise = 1 + 0.35 * (t / SDUR) ** 0.8
vib = 1 + 0.035 * np.sin(2 * np.pi * 38 * t)
sc = np.zeros(m)
for f in (620, 655, 940, 1310):
    ph = np.cumsum(f * rise * vib) / SR
    sc += 2 * (ph % 1.0) - 1
sc = sc / 4 + 0.45 * np.convolve(rng.standard_normal(m), np.ones(2) / 2, 'same')
sc += 1.4 * np.sin(2 * np.pi * 55 * t) * np.exp(-t / 0.09)
sc = np.tanh(3.5 * sc)
envs = np.minimum(1, t / 0.004) * np.minimum(1, (SDUR - t) / 0.01)
sc = sc * envs; sc = sc / np.abs(sc).max() * 10 ** (-1 / 20)   # peak -1 dBFS
i = int(TS * SR); j = min(len(mix), i + m)
mix[i:j] *= 0.05
mix[i:j, 0] += sc[:j - i]; mix[i:j, 1] += np.roll(sc, 7)[:j - i]
mix = np.clip(mix, -0.999, 0.999)
w = wave.open('esc_audio.wav', 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
w.writeframes((mix * 32767).astype(np.int16).tobytes()); w.close(); print('ok', 'game peak', 20*np.log10(np.abs(np.delete(mix, np.s_[i:j], 0)).max()), 'scream peak', 20*np.log10(np.abs(mix[i:j]).max()))
