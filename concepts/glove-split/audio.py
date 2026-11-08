"""Glove Split — BRUITAGES only (no melody).
pouf of the glove on every punch, pop on every split whose pitch climbs with the colour
(pentatonic, green = low ... cyan = high), soft ticks on bounces, crack + boom at the end.
python3 audio.py sim.npz DURATION out.wav
"""
import sys, wave, numpy as np
SR = 48000
d = np.load(sys.argv[1]); dur = float(sys.argv[2]); out = sys.argv[3]
ev = d['ev'].copy()
ev[:, 0] -= 1 / 60          # frame fi shows sim time (fi+1)/60 and is displayed at fi/60
t_boom = float(d['t_boom'])
N = int(dur * SR)
L = np.zeros(N + SR); R = np.zeros(N + SR)
rng = np.random.default_rng(5)

def env(n, a, dec):
    t = np.arange(n) / SR; e = np.exp(-t / dec)
    na = int(a * SR)
    if na > 0: e[:na] *= np.linspace(0, 1, na)
    return e
def lp(x, fc):
    a = np.exp(-2 * np.pi * fc / SR); y = np.empty_like(x); s = 0.0
    for i in range(len(x)): s = (1 - a) * x[i] + a * s; y[i] = s
    return y
NOISE = rng.standard_normal(SR * 3)
HPN = np.diff(NOISE, prepend=0) * 0.5

def pouf():
    """boxing-glove thump: soft low body + muffled leather slap"""
    n = int(0.22 * SR); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * np.cumsum(70 + 90 * np.exp(-t / 0.018)) / SR) * env(n, 0.001, 0.06)
    slap = lp(NOISE[:n].copy(), 1400) * env(n, 0.0005, 0.025) * 2.6
    return 0.9 * body + 0.8 * slap
PENTA = [60, 62, 64, 67, 69, 72, 74, 76, 79]   # colour 1 (green) .. 8 (cyan)
def pop(midi):
    n = int(0.16 * SR); t = np.arange(n) / SR
    f0 = 440 * 2 ** ((midi - 69) / 12)
    f = f0 * (1 + 0.5 * np.exp(-t / 0.008))
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = (np.sin(ph) + 0.25 * np.sin(2 * ph)) * env(n, 0.001, 0.055)
    return s + 0.25 * HPN[:n] * env(n, 0, 0.002)
POPS = {c: pop(PENTA[c - 1]) for c in range(1, 9)}
POUF = pouf()
def tick(f):
    n = int(0.05 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t) * env(n, 0.0005, 0.01) + 0.4 * HPN[:n] * env(n, 0, 0.0015)
TICKS = [tick(f) for f in (1700, 1900, 2150, 2400)]
def crack():
    n = int(0.12 * SR); o = rng.integers(0, SR); t = np.arange(n) / SR
    return HPN[o:o + n] * env(n, 0, 0.02) * 2 + 0.5 * np.sin(2 * np.pi * 120 * t) * env(n, 0, 0.03)
def boom():
    n = int(2.4 * SR); t = np.arange(n) / SR
    low = np.sin(2 * np.pi * np.cumsum(40 + 80 * np.exp(-t / 0.1)) / SR) * env(n, 0.002, 0.55)
    rumble = lp(np.resize(NOISE, n), 300) * env(n, 0.002, 0.5) * 3
    whoosh = lp(np.resize(HPN, n), 3000) * env(n, 0.05, 0.4) * 1.5
    return 1.0 * low + rumble + whoosh

def add(sig, t, gain, pan=0.0):
    i = int(round(t * SR))
    if i < 0 or i >= N: return
    n = min(len(sig), N + SR - i)
    L[i:i + n] += sig[:n] * gain * np.sqrt(0.5 * (1 - pan)); R[i:i + n] += sig[:n] * gain * np.sqrt(0.5 * (1 + pan))
def pan_of(x): return float(np.clip((x - 540) / 450, -1, 1)) * 0.5

# --- splits: pouf + pop, density-limited (max 3 pops per 40 ms window, 1 pouf per 50 ms)
sp = ev[ev[:, 1] == 0]
last_pouf = -1; recent = []
for (t, _, x, y, v, c0) in sp:
    c1 = int(c0) + 1
    recent = [r for r in recent if r > t - 0.04]
    if len(recent) >= 3: continue
    recent.append(t)
    g = 0.55 if len(sp) < 40 else 0.45
    add(POPS[c1], t, g, pan_of(x))
    if t - last_pouf > 0.05:
        add(POUF, t, 0.8, pan_of(x) * 0.5); last_pouf = t
# glove hits on balls that can no longer split (cyan / immune): pouf only, sparse
gh = ev[ev[:, 1] == 3]
for (t, _, x, y, v, c0) in gh:
    if t - last_pouf > 0.12 and v > 300:
        add(POUF, t, 0.35, pan_of(x) * 0.5); last_pouf = t
# bounces: soft ticks, max 1 per 35 ms
lt = -1
for (t, k, x, y, v, c0) in ev[(ev[:, 1] == 1) | (ev[:, 1] == 2)]:
    if t >= t_boom or t - lt < 0.035: continue
    lt = t
    add(TICKS[rng.integers(0, 4)], t, 0.10 * min(1, v / 900), pan_of(x))
# crack + boom
tc = ev[ev[:, 1] == 4][0, 0]
for q in range(6):
    add(crack(), tc + q * 0.6 / 6, 0.5, rng.uniform(-0.5, 0.5))
add(boom(), t_boom - 1 / 60, 1.0)

mix = np.stack([L[:N], R[:N]], 1)
mix = np.tanh(mix * 0.9) / 0.9 if np.abs(mix).max() > 1.2 else mix
mix *= 10 ** (float(__import__('os').environ.get('PEAK', '-4')) / 20) / np.abs(mix).max()      # peak -3 dBFS in PCM -> stays under -1 dBFS after AAC
with wave.open(out, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype('<i2').tobytes())
print('peak dBFS', round(20 * np.log10(np.abs(mix).max()), 2), 'splits', len(sp))
