"""Hammer Split — sound effects only (BRUITAGES). python3 audio.py sim.npz DURATION out.wav"""
import sys, wave, numpy as np
SR = 48000
d = np.load(sys.argv[1]); dur = float(sys.argv[2]); out = sys.argv[3]
ev_t, ev_k, ev_s, ev_x = d['ev_t'], d['ev_k'], d['ev_s'], d['ev_x']
SH = 1 / 60  # frame fi shows sim time (fi+1)/60 -> displayed 1 frame earlier
ev_t = ev_t - SH
N = int(dur * SR) + SR
L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(3)

def env(n, a, dec):
    t = np.arange(n) / SR
    e = np.exp(-t / dec); e[:int(a * SR)] *= np.linspace(0, 1, int(a * SR)) if a > 0 else 1
    return e

def lowpass(x, fc):
    a = np.exp(-2 * np.pi * fc / SR); y = np.zeros_like(x); s = 0.0
    for i in range(len(x)):
        s = (1 - a) * x[i] + a * s; y[i] = s
    return y

def bonk(f0):
    n = int(0.22 * SR); t = np.arange(n) / SR
    f = f0 * (0.55 + 0.45 * np.exp(-t / 0.03))
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * env(n, 0.001, 0.07) + 0.35 * np.sin(2.7 * ph) * env(n, 0.001, 0.025)
    click = rng.standard_normal(n) * env(n, 0, 0.004) * 0.5
    return body + click

def pop(f0):
    n = int(0.09 * SR); t = np.arange(n) / SR
    f = f0 * (1 + 1.2 * (1 - np.exp(-t / 0.012)))
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * env(n, 0.0015, 0.022)

NOISE = rng.standard_normal(SR * 3)
HP_NOISE = np.diff(NOISE, prepend=0)
def tick(dec=0.004, n_ms=25):
    n = int(n_ms / 1000 * SR); o = rng.integers(0, len(HP_NOISE) - n)
    return HP_NOISE[o:o + n] * env(n, 0, dec)

def crack():
    n = int(0.18 * SR); o = rng.integers(0, len(HP_NOISE) - n)
    x = HP_NOISE[o:o + n] * env(n, 0, 0.03)
    # crackle: sparse impulses
    sp = (rng.random(n) < 0.004) * rng.standard_normal(n) * 3 * env(n, 0, 0.06)
    t = np.arange(n) / SR
    low = np.sin(2 * np.pi * 95 * t) * env(n, 0, 0.05) * 0.6
    return 0.6 * x + sp + low

def add(sig, t, gain, pan=0.0):
    i = int(round(t * SR))
    if i < 0 or i >= N: return
    n = min(len(sig), N - i)
    gl = gain * np.sqrt(0.5 * (1 - pan)); gr = gain * np.sqrt(0.5 * (1 + pan))
    L[i:i + n] += sig[:n] * gl; R[i:i + n] += sig[:n] * gr

def pan_of(x): return float(np.clip((x - 540) / 540, -1, 1)) * 0.6

# voice limiting per 1/60 s window
budget = {'bonk': 2, 'split': 3, 'wall': 2, 'clack': 1}
used = {}
t_boom = float(ev_t[ev_k == 'boom'][0]); t_crack = float(ev_t[ev_k == 'crack_start'][0])  # already shifted
for t, k, s, x in zip(ev_t, ev_k, ev_s, ev_x):
    if t > dur: break
    if k not in budget: continue
    w = (k, int(t * 60))
    if used.get(w, 0) >= budget[k]: continue
    used[w] = used.get(w, 0) + 1
    p = pan_of(x)
    if k == 'bonk':
        add(bonk(rng.uniform(150, 190)), t, 0.55 * min(1, 0.35 + s / 900), p)
    elif k == 'split':
        nb = s
        g = 0.42 / (1 + nb / 120)
        add(pop(rng.uniform(520, 900)), t, max(g, 0.12), p)
    elif k == 'wall':
        if t > t_boom: continue
        add(tick(0.003, 20), t, 0.06 * min(1, s / 700), p)
    elif k == 'clack':
        add(tick(0.002, 15), t, 0.035, p)
# cracks: same schedule as render.py (16 notches over t_crack .. t_boom-0.15)
NCR = 16; span = t_boom - 0.15 - t_crack
for i in range(NCR):
    tc = np.ceil((t_crack + SH + (i + 1) / NCR * span) * 60 - 1e-6) / 60 - SH
    add(crack(), tc, 0.45 + 0.25 * i / NCR, rng.uniform(-0.5, 0.5))
# rumble rising during cracking
n = int((t_boom - t_crack) * SR); i0 = int(t_crack * SR)
rum = lowpass(rng.standard_normal(n), 140) * np.linspace(0, 1, n) ** 2 * 1.4
L[i0:i0 + n] += rum; R[i0:i0 + n] += rum
# BOOM
n = int(2.2 * SR); t = np.arange(n) / SR
f = 48 + 60 * np.exp(-t / 0.08)
boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, 0.55) * 1.0
boom += lowpass(rng.standard_normal(n), 900) * env(n, 0.001, 0.35) * 2.2
boom += HP_NOISE[:n] * env(n, 0, 0.05) * 0.35
add(boom, t_boom, 0.9)
# ring fragments + balls flying away: scattered pops/ticks
for j in range(60):
    tt = t_boom + rng.exponential(0.25)
    add(pop(rng.uniform(400, 1100)), tt, 0.12, rng.uniform(-0.8, 0.8))
for j in range(16):
    add(tick(0.01, 60), t_boom + rng.uniform(0, 0.4), 0.25, rng.uniform(-0.8, 0.8))
# hammer whoosh after the boom (empty screen): soft swish per revolution
theta = d['theta']; fps = 60
fi0 = int(t_boom * fps)
for fi in range(fi0 + 1, min(len(theta), int(dur * fps))):
    if int(theta[fi] / (2 * np.pi)) != int(theta[fi - 1] / (2 * np.pi)):
        n2 = int(0.35 * SR); w = lowpass(rng.standard_normal(n2), 500) * np.sin(np.linspace(0, np.pi, n2)) * 0.8
        add(w, (fi - 1) / fps - 0.17, 0.5)
mix = np.stack([L, R], 1)[:int(dur * SR)]
# soft limiter + normalize to -1.5 dBFS
mix = np.tanh(mix * 1.1) / np.tanh(1.1)
mix *= 10 ** (-1.5 / 20) / np.abs(mix).max()
pcm = (mix * 32767).astype('<i2')
with wave.open(out, 'wb') as wf:
    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(pcm.tobytes())
print('peak dBFS', 20 * np.log10(np.abs(mix).max()))
