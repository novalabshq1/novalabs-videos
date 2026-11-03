# Sound design (BRUITAGES mode): synthesized cracks/pops synced to the physics events.
# usage: python3 brick-breakout-audio.py events.npy DURATION out.wav
import sys, wave, numpy as np
ev = np.load(sys.argv[1]); DUR = float(sys.argv[2]); OUT = sys.argv[3]
SR = 48000; n = int(DUR * SR) + SR; L = np.zeros(n); R = np.zeros(n)
rng = np.random.default_rng(3)
def env(m, tau): return np.exp(-np.arange(m) / (tau * SR))
def lp(x, a):  # one-pole low-pass
    y = np.empty_like(x); s = 0.0
    for i in range(len(x)): s += a * (x[i] - s); y[i] = s
    return y
def add(t, sig, pan=0.0):
    i = int(t * SR); m = min(len(sig), n - i)
    if m <= 0: return
    L[i:i + m] += sig[:m] * (1 - pan) * 0.5 ** 0.5 * 1.2; R[i:i + m] += sig[:m] * (1 + pan) * 0.5 ** 0.5 * 1.2
def crack(gain=1.0, bright=1.0):
    m = int(0.18 * SR); tt = np.arange(m) / SR
    nz = rng.standard_normal(m); hp = nz - lp(nz, 0.25)
    s = hp * env(m, 0.012) * 0.55 * bright
    f = rng.uniform(1300, 2600)
    s += np.sin(2 * np.pi * f * tt) * env(m, 0.018) * 0.30 + np.sin(2 * np.pi * f * 1.51 * tt) * env(m, 0.010) * 0.15
    s += np.sin(2 * np.pi * rng.uniform(95, 140) * tt) * env(m, 0.035) * 0.55     # body thump
    for _ in range(3):  # tiny debris ticks
        d = int(rng.uniform(0.02, 0.11) * SR); k = int(0.006 * SR)
        s[d:d + k] += rng.standard_normal(k) * env(k, 0.0015) * 0.18
    s[:int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return s * gain
def pop(gain, f):
    m = int(0.09 * SR); tt = np.arange(m) / SR
    s = np.sin(2 * np.pi * f * tt * (1 - 0.35 * tt / 0.09)) * env(m, 0.020) * 0.6
    nz = rng.standard_normal(m); s += (nz - lp(nz, 0.3)) * env(m, 0.004) * 0.35
    return s * gain
for t, k, typ in ev:
    if typ == 0:
        add(t, crack(rng.uniform(0.75, 1.0)), rng.uniform(-0.4, 0.4))
    elif typ == 1:
        p_ = rng.uniform(-0.7, 0.7); add(t, pop(0.55, rng.uniform(500, 900)), p_); add(t, crack(0.35, 1.3), p_)
    elif typ == 2:
        m = int(0.9 * SR); tt = np.arange(m) / SR
        nz = rng.standard_normal(m); w = lp(nz, 0.08) * np.sin(np.pi * np.minimum(1, tt / 0.6)) ** 2 * 1.4
        add(t - 0.05, w * 0.6, 0)
        b = np.sin(2 * np.pi * 55 * tt * (1 - 0.3 * tt)) * env(m, 0.25) * 0.9
        add(t, b, 0)
mx = max(np.abs(L).max(), np.abs(R).max()); g = 0.89 / mx
L = np.tanh(L * g * 1.1) / np.tanh(1.1); R = np.tanh(R * g * 1.1) / np.tanh(1.1)
d = np.stack([L, R], 1)[:int(DUR * SR)]
with wave.open(OUT, 'wb') as wf:
    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
    wf.writeframes((np.clip(d, -1, 1) * 32000).astype('<i2').tobytes())
print('ok')
