import numpy as np, wave, sys
SR = 48000
DUR = float(sys.argv[1])
ev = np.load('events.npy')
rng = np.random.default_rng(3)
N = int(DUR * SR) + SR
L = np.zeros(N); Rt = np.zeros(N)

def add(sig, t, gain, pan):
    i = int(t * SR); j = min(N, i + len(sig)); s = sig[:j - i] * gain
    L[i:j] += s * np.sqrt(1 - pan); Rt[i:j] += s * np.sqrt(pan)

def snap_C(f):
    # C (70 %) : aigu et sec, petit "tic" de fil fin qui casse — validé par Yanis
    n = int(0.09 * SR); t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    crack = np.diff(np.diff(nz, prepend=0), prepend=0) * np.exp(-t / 0.0015)
    fi = 700 * f + 1300 * f * np.exp(-t / 0.008)
    ph = 2 * np.pi * np.cumsum(fi) / SR
    body = np.sin(ph) * np.exp(-t / 0.02) * (1 - np.exp(-t / 0.0003))
    return 0.25 * crack + 0.6 * body

def snap_B(f):
    # B (30 %) : grave et épais, gros élastique qui claque "THWACK" — validé par Yanis
    n = int(0.22 * SR); t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    crack = np.diff(nz, prepend=0) * np.exp(-t / 0.003)
    fi = 120 * f + 380 * f * np.exp(-t / 0.018)
    ph = 2 * np.pi * np.cumsum(fi) / SR
    body = (np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph)) * np.exp(-t / 0.06) * (1 - np.exp(-t / 0.0006))
    thwap = np.convolve(nz, np.ones(14) / 14, 'same') * np.exp(-t / 0.012)
    return 0.18 * crack + 0.7 * body + 0.5 * thwap

# ONE snap sound for the WHOLE video: "C" (70 % of String Circle videos) or "B" (30 %).
# Usage: python3 audio.py DURATION C|B   (the task picks C or B from journal.md to keep 7/3 over 10 videos)
SNAP = sys.argv[2].upper() if len(sys.argv) > 2 else ('C' if np.random.default_rng().random() < 0.7 else 'B')
assert SNAP in ('C', 'B'), SNAP
print('snap sound for this video:', SNAP)
def twang(f):
    return snap_C(f) if SNAP == 'C' else snap_B(f)

def die_hit():
    # same "crunch-pop" as the Spike Escape spike hit (validated by Yanis)
    n = int(0.3 * SR); t = np.arange(n) / SR
    fr = 120 + 700 * np.exp(-t / 0.02)
    s = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t / 0.07)
    nz = np.convolve(rng.standard_normal(n), np.ones(5) / 5, 'same') * np.exp(-t / 0.012)
    return 0.8 * s + 0.6 * nz

def pluck(f):
    n = int(0.18 * SR); p = int(SR / f)
    buf = rng.uniform(-1, 1, p); out = np.zeros(n)
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = 0.5 * (buf[i % p] + buf[(i + 1) % p]) * 0.985
    return out * np.exp(-np.arange(n) / SR / 0.06)

def tok():
    n = int(0.09 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * 150 * t) * np.exp(-t / 0.025) + 0.3 * rng.standard_normal(n) * np.exp(-t / 0.002)

def pop():
    n = int(0.45 * SR); t = np.arange(n) / SR
    fr = 60 + 200 * np.exp(-t / 0.05)
    s = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t / 0.14)
    nz = rng.standard_normal(n) * np.exp(-t / 0.03)
    nz = np.convolve(nz, np.ones(12) / 12, 'same')
    return 0.9 * s + 0.8 * nz

def win():
    out = np.zeros(int(0.9 * SR))
    for k, f in enumerate([392, 523.25, 659.25, 783.99]):
        n = int(0.55 * SR); t = np.arange(n) / SR
        s = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * np.exp(-t / 0.18) * (1 - np.exp(-t / 0.004))
        i = int(k * 0.09 * SR); out[i:i + n] += s[:len(out) - i]
    return out

pl = [pluck(f) for f in (660, 740, 830, 880, 990)]
last_snap = -1
last_hit = -1e9        # RUSH: crunch-pop limited to 1 every 60 ms
HIT_GAP = 0.060
SNAP_MAX_LAG = 0.15    # RUSH: drop a string snap that would sound > 0.15 s after the cut
n_snap = n_snap_drop = n_hit = n_hit_drop = 0
for t, k, x in ev:
    k = int(k)
    if k in (0, 1):
        if t - last_hit < HIT_GAP:
            n_hit_drop += 1; continue
        last_hit = t; n_hit += 1
    if k == 0:
        add(die_hit(), t, 0.42, rng.uniform(0.3, 0.7))   # ball touches the circle
    elif k == 1:
        add(die_hit(), t, 0.48, 0.5)                      # two countries collide
    elif k == 2:
        j = int(x)                       # j-th string cut in the same substep
        if j * 0.011 > SNAP_MAX_LAG:
            n_snap_drop += 1; continue
        n_snap += 1
        add(twang(rng.uniform(0.85, 1.2)), t + j * 0.011, 0.5, rng.uniform(0.25, 0.75))
    elif k == 3:
        add(pop(), t, 0.6, 0.5)
    elif k == 4:
        add(win(), t + 0.15, 0.28, 0.5)

mix = np.stack([L, Rt], 1)[:int(DUR * SR)]
mix = np.tanh(mix * 1.4) / np.tanh(1.4)
mix = mix / np.abs(mix).max() * 0.89
fo = (np.minimum(1, (len(mix) - np.arange(len(mix))) / (0.3 * SR)))[:, None]
mix *= fo
w = wave.open('audio.wav', 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
w.writeframes((mix * 32767).astype(np.int16).tobytes()); w.close()
print('ok', len(mix) / SR, 'snaps', n_snap, 'dropped', n_snap_drop, 'hits', n_hit, 'hits dropped', n_hit_drop, 'peak_dBFS', 20*np.log10(np.abs(mix).max()))
