import numpy as np, wave, sys
SR = 48000; DUR = float(sys.argv[1])
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
for t, k, x in ev:
    k = int(k)
    if k == 0: add(bounce(scale[rng.integers(len(scale))]), t, 0.12 + 0.25 * x, rng.uniform(0.3, 0.7))
    elif k == 1: add(wood(rng.uniform(260, 340)), t, 0.18 + 0.25 * x, rng.uniform(0.3, 0.7))
    elif k == 2: add(die(), t, 0.6)
    elif k == 3: add(spawn(), t, 0.15)
    elif k == 4: add(escape(), t, 0.5)
mix = np.stack([L, Rr], 1)[:int(DUR * SR)]
mix = np.tanh(mix * 1.3) / np.tanh(1.3); mix = mix / np.abs(mix).max() * 0.89
mix *= np.minimum(1, (len(mix) - np.arange(len(mix))) / (0.3 * SR))[:, None]
w = wave.open('esc_audio.wav', 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
w.writeframes((mix * 32767).astype(np.int16).tobytes()); w.close(); print('ok')
