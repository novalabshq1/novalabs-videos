#!/usr/bin/env python3
"""String Duel — Liverpool vs Arsenal (String Circle rules, 2 balls).

Rules
- Each ball moves in a straight line at constant speed. Its direction only changes when it
  hits the rim (elastic reflection) or the other ball (elastic reflection, no overlap).
- Each ball starts tied to the rim by 10 strings (ball -> fixed anchor on the rim).
- Every RIM hit adds +1 string from the ball to the impact point (ball-ball hits add nothing).
- A ball that passes through a string of the OTHER ball cuts it (removed for good). It never
  cuts its own strings, and cutting never changes its trajectory.
  Detection: per substep (12 per frame, < 1.2 px of travel) the distance from the cutter's
  centre to the string segment (which moves with its owner) is tested against the radius,
  i.e. the swept capsule of the ball against the swept string.
- A ball with 0 strings is eliminated. Fallback at T_LIMIT: most strings wins.

Autonomous: numpy + pillow + ffmpeg. Drawn at 2160x3840, LANCZOS down to 1080x1920, 60 fps.

    python3.13 string-duel.py --search 200
    python3.13 string-duel.py --seed N
    python3.13 string-duel.py --seed N --frames 0,0.25,0.5,0.75,0.95 --outdir keys/
    python3.13 string-duel.py --seed N --out video.mp4
"""
import argparse, math, os, subprocess, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, S = 1080, 1920, 60, 2
SR = 48000
SUB = 12
DT = 1.0 / (FPS * SUB)

CX, CY, RA = 540.0, 1075.0, 405.0
BR = 30.0
V = 560.0
N0 = 10
FADE_CUT = 0.15
HOLD = 3.6

TEAMS = [
    dict(code="LIV", name="LIVERPOOL", fill=(210, 22, 48), ring=(210, 22, 48), string=(226, 52, 72), text=(255, 255, 255)),
    dict(code="ARS", name="ARSENAL", fill=(246, 244, 240), ring=(219, 0, 7), string=(236, 234, 228), text=(219, 0, 7)),
]


def seg_dist(p, a, b):
    """distance from point p (2,) to segments a->b (n,2) each"""
    ab = b - a
    ap = p - a
    L2 = np.maximum((ab * ab).sum(1), 1e-9)
    t = np.clip((ap * ab).sum(1) / L2, 0.0, 1.0)
    q = a + ab * t[:, None]
    return np.hypot(*(p - q).T)


WIN_SCORE = 3
GAP = 1.15          # pause between knock-out and next round
GROW = 0.30         # new strings grow from the ball to the rim


def new_strings(rng, t):
    off = rng.uniform(0, 2 * math.pi)
    return [dict(ang=off + k * 2 * math.pi / N0 + rng.uniform(-0.12, 0.12), born=t, cut=None, gone=None, grow=True)
            for k in range(N0)]


def rand_dir(rng):
    a = rng.uniform(0, 2 * math.pi)
    return np.array([math.cos(a) * V, math.sin(a) * V])


def simulate(seed, tmax=70.0):
    rng = np.random.default_rng(seed)
    pos = np.array([[CX - 150 + rng.uniform(-40, 40), CY + rng.uniform(-120, 120)],
                    [CX + 150 + rng.uniform(-40, 40), CY + rng.uniform(-120, 120)]])
    vel = np.array([rand_dir(rng), rand_dir(rng)])
    strings = [new_strings(rng, -1.0), new_strings(rng, -1.0)]
    score = [0, 0]
    alive = [True, True]
    vis = [dict(spawn=-9.0, dead=None), dict(spawn=-9.0, dead=None)]
    vis_hist = [[], []]          # list of (spawn, dead) intervals per ball
    events = []
    frames = []
    rounds = []                  # (start, end, winner)
    t = 0.0
    round_start = 0.0
    pause_until = None           # time of next round start
    end_t = None
    winner = None
    while True:
        frames.append(dict(t=t, pos=pos.copy(), alive=list(alive), score=list(score),
                           counts=[sum(1 for s in strings[i] if s['cut'] is None and s['gone'] is None and s['born'] <= t) for i in range(2)]))
        if end_t is not None and t >= end_t + HOLD:
            break
        if t > tmax:
            raise RuntimeError("too long")
        for _ in range(SUB):
            playing = end_t is None and pause_until is None
            for i in range(2):
                if alive[i]:
                    pos[i] += vel[i] * DT
            for i in range(2):
                if not alive[i]:
                    continue
                d = pos[i] - (CX, CY)
                r = math.hypot(*d)
                if r > RA - BR:
                    n = d / r
                    vn = vel[i] @ n
                    if vn > 0:
                        vel[i] -= 2 * vn * n
                        ang = math.atan2(n[1], n[0])
                        if playing:
                            strings[i].append(dict(ang=ang, born=t, cut=None, gone=None, grow=False))
                            events.append((t, 'wall', i, CX + RA * n[0], CY + RA * n[1]))
                        else:
                            events.append((t, 'tap', i, CX + RA * n[0], CY + RA * n[1]))
                    pos[i] = (CX, CY) + n * (RA - BR)
            if alive[0] and alive[1]:
                d = pos[1] - pos[0]
                r = math.hypot(*d)
                if r < 2 * BR:
                    n = d / max(r, 1e-6)
                    hit = False
                    if vel[0] @ n > 0:
                        vel[0] -= 2 * (vel[0] @ n) * n; hit = True
                    if vel[1] @ n < 0:
                        vel[1] -= 2 * (vel[1] @ n) * n; hit = True
                    ov = 2 * BR - r
                    pos[0] -= n * ov / 2
                    pos[1] += n * ov / 2
                    if hit:
                        m = (pos[0] + pos[1]) / 2
                        events.append((t, 'bb', -1, m[0], m[1]))
            if playing and alive[0] and alive[1]:
                for a in range(2):
                    b = 1 - a
                    live = [s for s in strings[b] if s['cut'] is None and s['gone'] is None and s['born'] <= t]
                    if not live:
                        continue
                    angs = np.array([s['ang'] for s in live])
                    anc = np.stack([CX + RA * np.cos(angs), CY + RA * np.sin(angs)], 1)
                    u = anc - pos[b]
                    L = np.maximum(np.hypot(*u.T), 1e-6)
                    st = pos[b] + u * (np.minimum(BR, L) / L)[:, None]
                    dist = seg_dist(pos[a], st, anc)
                    hits = np.nonzero(dist < BR)[0]
                    for h in hits:
                        live[h]['cut'] = t
                        ab = anc[h] - st[h]
                        tt = np.clip(((pos[a] - st[h]) @ ab) / max(ab @ ab, 1e-9), 0, 1)
                        q = st[h] + ab * tt
                        events.append((t, 'cut', b, q[0], q[1]))
                    if len(hits) and not any(s['cut'] is None and s['gone'] is None for s in strings[b]):
                        alive[b] = False
                        vis[b]['dead'] = t
                        vis_hist[b].append((vis[b]['spawn'], t))
                        score[a] += 1
                        rounds.append((round_start, t, a))
                        if score[a] < WIN_SCORE:
                            for s in strings[a]:
                                if s['cut'] is None and s['gone'] is None:
                                    s['gone'] = t + 0.35
                        if score[a] >= WIN_SCORE:
                            end_t = t
                            winner = a
                            events.append((t, 'final', b, pos[b][0], pos[b][1]))
                        else:
                            pause_until = t + GAP
                            events.append((t, 'ko', b, pos[b][0], pos[b][1]))
                        break
            if pause_until is not None and t >= pause_until:
                # new round: loser respawns opposite the winner, both get 10 fresh strings
                b = 0 if not alive[0] else 1
                a = 1 - b
                for _try in range(200):
                    ang = rng.uniform(0, 2 * math.pi)
                    rr = rng.uniform(0, RA - BR - 60)
                    p = np.array([CX + rr * math.cos(ang), CY + rr * math.sin(ang)])
                    if np.hypot(*(p - pos[a])) > 330:
                        break
                pos[b] = p
                vel[b] = rand_dir(rng)
                alive[b] = True
                vis[b] = dict(spawn=t, dead=None)
                strings[a] += new_strings(rng, t)
                strings[b] += new_strings(rng, t)
                events.append((t, 'spawn', b, p[0], p[1]))
                round_start = t
                pause_until = None
            t += DT
    for i in range(2):
        if vis[i]['dead'] is None:
            vis_hist[i].append((vis[i]['spawn'], None))
    return dict(frames=frames, events=events, strings=strings, winner=winner, end_t=end_t,
                vis=vis_hist, rounds=rounds, seed=seed)


def stats(sim):
    r = sim['rounds']
    lens = [round(e - s, 1) for s, e, w in r]
    seq = ''.join(TEAMS[w]['code'][0] for s, e, w in r)
    sc = [0, 0]
    comeback = False
    tied = 0
    for s, e, w in r:
        sc[w] += 1
        if sc[0] == sc[1]:
            tied += 1
    walls = sum(1 for e in sim['events'] if e[1] == 'wall')
    cuts = sum(1 for e in sim['events'] if e[1] == 'cut')
    bb = sum(1 for e in sim['events'] if e[1] == 'bb')
    return dict(seed=sim['seed'], end=round(sim['end_t'], 1), seq=seq, lens=lens, minlen=min(lens),
                last=lens[-1], tied=tied, walls=walls, cuts=cuts, bb=bb)


def _search(seed):
    try:
        return stats(simulate(seed))
    except Exception as e:
        return dict(seed=seed, err=str(e))


# ---------------------------------------------------------------- rendering
FONT_B = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
FONT_SB = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
FONT_M = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
_fc = {}


def font(path, px):
    k = (path, int(px))
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, int(px))
    return _fc[k]


BG = (8, 8, 10)
RIM = (205, 205, 210)


def ease(x):
    x = min(1, max(0, x))
    return x * x * (3 - 2 * x)


def text_c(dr, x, y, s, f, fill, anchor="mm"):
    dr.text((x * S, y * S), s, font=f, fill=fill, anchor=anchor)


def ball_state(sim, b, t):
    """scale, alpha of ball b at time t (None if invisible)"""
    for sp, dead in sim['vis'][b]:
        if t < sp:
            continue
        if dead is None or t < dead:
            k = ease((t - sp) / 0.35) if sp > 0 else 1.0
            return 0.55 + 0.45 * k, k
        if t < dead + 0.6:
            k = ease((t - dead) / 0.6)
            return 1 - 0.8 * k, 1 - k
    return None


def lerp_c(c, a):
    return tuple(int(BG[k] + (c[k] - BG[k]) * a) for k in range(3))


def last_change(sim, kind_set, b, t):
    best = -9
    for e in sim['events']:
        if e[0] > t:
            break
        if e[1] in kind_set and (b is None or e[2] == b):
            best = e[0]
    return best


def render_frame(sim, fi, T0=0.0):
    fr = sim['frames'][fi]
    t = fr['t']
    img = Image.new("RGB", (W * S, H * S), BG)
    dr = ImageDraw.Draw(img)
    end_t = sim['end_t']
    w = sim['winner']
    # hook
    text_c(dr, 540, 312, "LIVERPOOL vs ARSENAL", font(FONT_B, 66), (245, 245, 245))
    ko = ease((t - end_t - 0.45) / 0.25) if t > end_t + 0.45 else 0.0
    ke = ease((t - end_t - 0.75) / 0.35) if t > end_t + 0.75 else 0.0
    if ko < 1:
        text_c(dr, 540, 386, "who wins tomorrow?", font(FONT_M, 52), lerp_c((175, 175, 182), 1 - ko))
    if ke > 0:
        wc = TEAMS[w]['string'] if w == 0 else (245, 243, 238)
        text_c(dr, 540, 388, TEAMS[w]['name'] + " WINS", font(FONT_B, 60), lerp_c(wc, ke))
    # score + string counters
    sc = fr['score']
    c = fr['counts']
    for i, x in ((0, 320), (1, 760)):
        tm = TEAMS[i]
        col = tm['string'] if i == 0 else (240, 238, 232)
        text_c(dr, x, 470, tm['code'], font(FONT_SB, 36), (150, 150, 158))
        # score digit pops slightly when it changes
        lc = -9
        for r0, r1, ww in sim['rounds']:
            if ww == i and r1 <= t:
                lc = r1
        pop = 1 + 0.18 * max(0.0, 1 - (t - lc) / 0.25)
        text_c(dr, x, 540, str(sc[i]), font(FONT_B, 92 * pop), col)
        text_c(dr, x, 612, f"{c[i]} strings" if c[i] != 1 else "1 string", font(FONT_M, 28), lerp_c(col, 0.7))
    text_c(dr, 540, 532, "–", font(FONT_B, 64), (95, 95, 102))
    text_c(dr, 540, 612, "first to 3", font(FONT_M, 24), (95, 95, 102))
    # rim
    dr.ellipse(((CX - RA) * S, (CY - RA) * S, (CX + RA) * S, (CY + RA) * S), outline=RIM, width=int(2.4 * S))
    # strings
    for b in range(2):
        tm = TEAMS[b]
        p = fr['pos'][b]
        for s in sim['strings'][b]:
            if s['born'] > t:
                continue
            a = 1.0
            if s['cut'] is not None and s['cut'] <= t:
                a = 1 - (t - s['cut']) / FADE_CUT
            if s['gone'] is not None and s['gone'] <= t:
                a = min(a, 1 - (t - s['gone']) / 0.3)
            if a <= 0:
                continue
            ax, ay = CX + RA * math.cos(s['ang']), CY + RA * math.sin(s['ang'])
            ex, ey = ax, ay
            if s['grow'] and t - s['born'] < GROW:
                k = ease((t - s['born']) / GROW)
                ex, ey = p[0] + (ax - p[0]) * k, p[1] + (ay - p[1]) * k
            col = lerp_c(tm['string'], a * 0.9)
            dr.line((p[0] * S, p[1] * S, ex * S, ey * S), fill=col, width=int(1.5 * S))
            if not s['grow'] or t - s['born'] >= GROW:
                r0 = 2.6
                dr.ellipse(((ax - r0) * S, (ay - r0) * S, (ax + r0) * S, (ay + r0) * S), fill=col)
    # balls
    for b in range(2):
        st = ball_state(sim, b, t)
        if st is None:
            continue
        sc_, al = st
        if al <= 0.01:
            continue
        tm = TEAMS[b]
        p = fr['pos'][b]
        r = BR * sc_
        dr.ellipse(((p[0] - r) * S, (p[1] - r) * S, (p[0] + r) * S, (p[1] + r) * S), fill=lerp_c(tm['fill'], al))
        if b == 1:
            rr = r - 1.5
            dr.ellipse(((p[0] - rr) * S, (p[1] - rr) * S, (p[0] + rr) * S, (p[1] + rr) * S),
                       outline=lerp_c(tm['ring'], al), width=max(1, int(4 * S * sc_)))
        if sc_ > 0.6:
            text_c(dr, p[0], p[1] + 1, tm['code'], font(FONT_B, 19 * sc_), lerp_c(tm['text'], al))
    text_c(dr, 540, 1700, "@novalabs.hq", font(FONT_M, 24), (70, 70, 76))
    return img.resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- audio
def lp1(x, fc):
    a = math.exp(-2 * math.pi * fc / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def bp_noise(n, rng, f, q):
    """cheap band-passed noise via biquad"""
    x = rng.standard_normal(n)
    w0 = 2 * math.pi * f / SR
    alpha = math.sin(w0) / (2 * q)
    b0, b1, b2 = alpha, 0, -alpha
    a0, a1, a2 = 1 + alpha, -2 * math.cos(w0), 1 - alpha
    y = np.zeros(n)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(n):
        yi = (b0 * x[i] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2) / a0
        x2, x1 = x1, x[i]
        y2, y1 = y1, yi
        y[i] = yi
    return y / (np.abs(y).max() + 1e-9)


def make_snip(rng, pitch):
    n = int(0.07 * SR)
    tt = np.arange(n) / SR
    nz = bp_noise(n, rng, 4200 * pitch, 3.0)
    env = np.exp(-tt / 0.012)
    click = np.sin(2 * math.pi * 2600 * pitch * tt) * np.exp(-tt / 0.006)
    body = np.sin(2 * math.pi * 900 * pitch * tt) * np.exp(-tt / 0.018) * 0.35
    s = nz * env * 0.8 + click * 0.45 + body
    s[:int(0.0015 * SR)] *= np.linspace(0, 1, int(0.0015 * SR))
    return lp1(s, 7500)


def make_tic(pitch):
    n = int(0.12 * SR)
    tt = np.arange(n) / SR
    f = 1250 * pitch
    s = (np.sin(2 * math.pi * f * tt) + 0.25 * np.sin(2 * math.pi * 2.76 * f * tt) * np.exp(-tt / 0.012)) * np.exp(-tt / 0.045)
    s[:48] *= np.linspace(0, 1, 48)
    return lp1(s, 5000)


def make_thud(rng):
    n = int(0.16 * SR)
    tt = np.arange(n) / SR
    f = 150 * np.exp(-tt / 0.08) + 85
    ph = 2 * math.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-tt / 0.05) + lp1(rng.standard_normal(n), 900) * np.exp(-tt / 0.012) * 1.4
    s[:48] *= np.linspace(0, 1, 48)
    return s


def make_boom(rng):
    n = int(1.4 * SR)
    tt = np.arange(n) / SR
    f = 95 * np.exp(-tt / 0.25) + 48
    ph = 2 * math.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-tt / 0.35) + lp1(rng.standard_normal(n), 400) * np.exp(-tt / 0.06) * 0.8
    s[:96] *= np.linspace(0, 1, 96)
    return s


def make_chord():
    n = int(2.6 * SR)
    tt = np.arange(n) / SR
    s = np.zeros(n)
    for f, g in ((392.0, 1.0), (493.88, 0.8), (587.33, 0.7), (783.99, 0.45)):
        s += g * (np.sin(2 * math.pi * f * tt) + 0.3 * np.sin(4 * math.pi * f * tt) * np.exp(-tt / 0.3))
    env = np.minimum(1, tt / 0.01) * np.exp(-tt / 0.9)
    return lp1(s * env, 4000)


def build_audio(sim, T0, dur, path):
    rng = np.random.default_rng(7)
    n = int(dur * SR) + SR
    L = np.zeros(n); R = np.zeros(n)
    snips = [make_snip(rng, p) for p in (0.82, 0.9, 1.0, 1.1, 1.22)]
    tics = [make_tic(2 ** (k / 12)) for k in (0, 3, 5, 7, 10)]
    thud = make_thud(rng)

    def add(sig, t, g, x):
        i = int((t - T0) * SR)
        if i < 0 or i >= n:
            return
        pan = (x - 540) / 540 * 0.35
        gl, gr = g * math.sqrt((1 - pan) / 2) * 1.414, g * math.sqrt((1 + pan) / 2) * 1.414
        m = min(len(sig), n - i)
        L[i:i + m] += sig[:m] * gl
        R[i:i + m] += sig[:m] * gr

    # group events per frame (1/60 s) per kind
    groups = {}
    for (t, k, b, x, y) in sim['events']:
        key = (int(t * FPS), k)
        groups.setdefault(key, []).append((t, b, x, y))
    recent = []          # times of sounds, for density ducking
    ci = ti = 0
    for (fi, k) in sorted(groups):
        lst = groups[(fi, k)]
        t = lst[0][0]
        x = sum(e[2] for e in lst) / len(lst)
        recent = [r for r in recent if t - r < 0.5]
        duck = 1.0 / (1 + 0.06 * len(recent))
        if k == 'cut':
            nn = len(lst)
            g = (0.55 + 0.1 * min(nn - 1, 3)) * rng.uniform(0.75, 1.0) * duck
            add(snips[ci % 5], t, g, x)
            if nn > 1:
                add(snips[(ci + 2) % 5], t + 0.012, g * 0.5, x)
            ci += 1 + int(rng.integers(0, 2))
            recent.append(t)
        elif k == 'wall':
            add(tics[ti % 5], t, 0.32 * rng.uniform(0.7, 1.0) * duck, x)
            ti += 1 + int(rng.integers(0, 3))
            recent.append(t)
        elif k == 'bb':
            add(thud, t, 0.85, x)
            recent.append(t)
        elif k in ('elim', 'limit'):
            add(make_boom(rng), t, 1.1, 540)
            add(make_chord(), t + 0.45, 0.32, 540)
    # light reverb (few taps)
    for buf in (L, R):
        wet = np.zeros_like(buf)
        for d, g in ((0.031, 0.22), (0.047, 0.18), (0.071, 0.14), (0.113, 0.1), (0.167, 0.07)):
            k = int(d * SR)
            wet[k:] += buf[:-k] * g
        buf += lp1(wet, 3500)
    st = np.stack([L, R], 1)[:int(dur * SR)]
    st = np.tanh(st * 1.0)
    raw = path + ".raw.wav"
    with wave.open(raw, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(st / (np.abs(st).max() + 1e-9) * 0.7, -1, 1) * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af",
                    "loudnorm=I=-14:TP=-3:LRA=11", "-ar", str(SR), path], check=True)
    os.remove(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--search", type=int, default=0)
    ap.add_argument("--frames", default="")
    ap.add_argument("--outdir", default="keys")
    ap.add_argument("--out", default="")
    ap.add_argument("--t0", type=float, default=0.0)
    a = ap.parse_args()
    if a.search:
        with Pool(4) as p:
            res = p.map(_search, range(a.search))
        for r in res:
            print(r)
        return
    sim = simulate(a.seed)
    print(stats(sim))
    fr = sim['frames']
    i0 = int(a.t0 * FPS)
    if a.frames:
        os.makedirs(a.outdir, exist_ok=True)
        for x in a.frames.split(","):
            fi = i0 + int(float(x) * (len(fr) - 1 - i0))
            render_frame(sim, fi).save(os.path.join(a.outdir, f"f{float(x):.2f}.png"))
        return
    if a.out:
        dur = (len(fr) - i0) / FPS
        wav = a.out + ".wav"
        build_audio(sim, i0 / FPS, dur, wav)
        proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                 "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                                 "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                                 "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", a.out],
                                stdin=subprocess.PIPE)
        for fi in range(i0, len(fr)):
            proc.stdin.write(render_frame(sim, fi).tobytes())
        proc.stdin.close()
        proc.wait()
        os.remove(wav)


if __name__ == "__main__":
    main()
