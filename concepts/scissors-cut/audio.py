"""Scissors Cut — sound effects only (BRUITAGES). python3 audio.py sim.npz DURATION out.wav"""
import sys, wave, numpy as np
SR = 48000
d = np.load(sys.argv[1]); dur = float(sys.argv[2]); out = sys.argv[3]
ev_t, ev_k, ev_s, ev_x = d['ev_t'], d['ev_k'], d['ev_s'], d['ev_x']
ev_t = ev_t - 1 / 60   # frame fi shows sim time (fi+1)/60
N = int(dur * SR) + SR
L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(3)
def env(n, a, dec):
    t = np.arange(n) / SR; e = np.exp(-t / dec)
    na = int(a * SR)
    if na > 0: e[:na] *= np.linspace(0, 1, na)
    return e
def bp(x, f, q=4.0):
    # simple biquad bandpass
    w = 2 * np.pi * f / SR; al = np.sin(w) / (2 * q)
    b0, b2 = al, -al; a0, a1, a2 = 1 + al, -2 * np.cos(w), 1 - al
    y = np.zeros_like(x); x1 = x2 = y1 = y2 = 0.0
    for i in range(len(x)):
        yi = (b0 * x[i] + b2 * x2 - a1 * y1 - a2 * y2) / a0
        x2, x1 = x1, x[i]; y2, y1 = y1, yi; y[i] = yi
    return y
NOISE = rng.standard_normal(SR * 2); HPN = np.diff(NOISE, prepend=0)
def clac():
    # scissors snapping shut: scrape + bright metallic clack
    n = int(0.30 * SR); t = np.arange(n) / SR
    scr = bp(NOISE[:n].copy(), 5200, 2.5) * env(n, 0.0, 0.025) * 1.4
    ring = (np.sin(2*np.pi*2950*t) + 0.6*np.sin(2*np.pi*4370*t) + 0.4*np.sin(2*np.pi*6810*t)) * env(n, 0.0005, 0.045)
    thud = np.sin(2*np.pi*(180*(1+np.exp(-t/0.01)))*t) * env(n, 0.0005, 0.03)
    click = HPN[:n] * env(n, 0, 0.0025)
    return 0.55*scr + 0.35*ring + 0.5*thud + 0.6*click
def snip(f0):
    n = int(0.12 * SR); t = np.arange(n) / SR
    o = rng.integers(0, SR); x = bp(HPN[o:o+n].copy(), 7000, 1.5) * env(n, 0.0, 0.018)
    f = f0 * (1 + 1.3 * (1 - np.exp(-t / 0.015)))
    popsig = np.sin(2*np.pi*np.cumsum(f)/SR) * env(n, 0.002, 0.03)
    return 0.7*x + 0.8*popsig
def tick(dec=0.004, n_ms=25):
    n = int(n_ms / 1000 * SR); o = rng.integers(0, len(HPN) - n)
    return HPN[o:o+n] * env(n, 0, dec)
def tink(f):
    n = int(0.08 * SR); t = np.arange(n) / SR
    return (np.sin(2*np.pi*f*t) + 0.3*np.sin(2*np.pi*f*2.76*t)) * env(n, 0.0005, 0.015) + 0.3*tick(0.002, 80)
def crack():
    n = int(0.18 * SR); o = rng.integers(0, len(HPN) - n); t = np.arange(n) / SR
    sp = (rng.random(n) < 0.004) * rng.standard_normal(n) * 3 * env(n, 0, 0.06)
    return 0.6*HPN[o:o+n]*env(n, 0, 0.03) + sp + 0.6*np.sin(2*np.pi*95*t)*env(n, 0, 0.05)
def boom():
    n = int(2.6 * SR); t = np.arange(n) / SR
    low = np.sin(2*np.pi*np.cumsum(38 + 70*np.exp(-t/0.12))/SR) * env(n, 0.002, 0.6)
    o = rng.integers(0, SR); nz = NOISE[:n] if n <= len(NOISE) else np.resize(NOISE, n)
    sm = np.convolve(nz, np.ones(24)/24, 'same') * env(n, 0.001, 0.35) * 2.2
    return 1.1*low + sm + 0.6*np.resize(HPN, n)*env(n, 0, 0.05)
def add(sig, t, gain, pan=0.0):
    i = int(round(t * SR))
    if i < 0 or i >= N: return
    n = min(len(sig), N - i)
    L[i:i+n] += sig[:n] * gain * np.sqrt(0.5*(1-pan)); R[i:i+n] += sig[:n] * gain * np.sqrt(0.5*(1+pan))
def pan_of(x): return float(np.clip((x - 540) / 540, -1, 1)) * 0.6
t_boom = float(ev_t[ev_k == 'boom'][0])
CLAC = clac()
budget = {}   # max sounds per 15 ms bucket per kind
lim = {'wall': 2, 'clack': 2, 'tink': 2, 'cut': 3}
for t, k, x, s in sorted(zip(ev_t, ev_k, ev_x, ev_s), key=lambda e: e[0]):
    b = (k, int(t / 0.015))
    if k in lim:
        if budget.get(b, 0) >= lim[k]: continue
        budget[b] = budget.get(b, 0) + 1
    p = pan_of(x)
    if k == 'clac': add(CLAC, t, 0.55)
    elif k == 'cut': add(snip(rng.uniform(520, 760)), t, 0.42, p)
    elif k == 'wall': add(tick(0.004), t, 0.10 * min(1, s / 600), p)
    elif k == 'clack': add(tick(0.0025, 15), t, 0.05 * min(1, s / 700), p)
    elif k == 'tink' and t < t_boom: add(tink(rng.uniform(2100, 2600)), t, 0.06 * min(1, s / 600), p)
    elif k == 'crack_start':
        for j in range(16): add(crack(), t + j * 2.25 / 16 + rng.uniform(0, 0.05), 0.35 + 0.02*j, rng.uniform(-0.5, 0.5))
    elif k == 'boom': add(boom(), t, 0.9)
n = int(dur * SR); L, R = L[:n], R[:n]
st = np.stack([L, R], 1)
# level: pre-boom peak at -4.5 dBFS, then a look-ahead limiter keeps everything under -1 dBFS
from numpy.lib.stride_tricks import sliding_window_view
ib = int(t_boom * SR)
st *= 10 ** (-5.0 / 20) / np.abs(st[:10 * SR]).max()
pk = np.abs(st).max(1)
w = int(0.006 * SR)
envp = sliding_window_view(np.pad(pk, (w, w)), 2 * w + 1).max(1)
g = np.minimum(1.0, 0.85 / np.maximum(envp, 1e-9))
gs = np.convolve(np.pad(g, (240, 240), mode='edge'), np.ones(481) / 481, 'valid'); gs = np.minimum(gs, g)
st = st * gs[:, None]
st *= min(1.0, 10 ** (-1.05 / 20) / np.abs(st).max())
fo = int(0.5 * SR); st[-fo:] *= np.linspace(1, 0, fo)[:, None]
with wave.open(out, 'wb') as wf:
    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
    wf.writeframes((np.clip(st, -1, 1) * 32767).astype(np.int16).tobytes())
print('peak dBFS', 20 * np.log10(np.abs(st).max()), 'events', len(ev_t))
