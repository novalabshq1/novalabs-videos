# Procedural screamer face (100% generated, numpy/OpenCV). Old night photo: pale grey-green elongated face,
# long black hair eating the sides, dark sockets, bulging eyes with pinprick pupils + red veins,
# unnaturally wide grin with a row of teeth, hollow cheeks, nose shadow, grain, blur, JPEG artefacts.
# Usage: import face; img = face.make(variant_seed, tilt_deg, smile_curve, gaze_dx) -> BGR uint8 (H x W)
import numpy as np, cv2, math

def make(seed=7, tilt=-4.0, smile=1.3, gaze=(0.0, 0.0), W=1300, H=2300):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, H * 0.47
    img = np.zeros((H, W, 3), np.float32)
    # dim background: almost black with a faint dirty wall
    img[:] = (14, 16, 15)
    img += rng.normal(0, 4, (H, W, 1)).astype(np.float32)

    # --- head: elongated oval, slightly narrower chin
    fa, fb = W * 0.34, H * 0.36
    u = (xx - cx) / fa; v = (yy - cy) / np.where(yy > cy, fb * 0.72, fb)
    u = u * (1 + 0.38 * np.clip(v, 0, 1) ** 1.5)         # narrow towards the chin
    d = np.sqrt(u * u + v * v)
    face_m = np.clip((1.0 - d) * 18, 0, 1)
    # skin: pale grey-green, lit from slightly above-front (flash in the dark), falls off quickly
    light = np.clip(1.15 - 0.85 * np.sqrt(((xx - cx) / (W * 0.5)) ** 2 + ((yy - cy * 0.92) / (H * 0.45)) ** 2), 0, 1)
    skin = np.stack([150 + 0 * xx, 172 + 0 * xx, 160 + 0 * xx], -1)  # BGR grey-green
    skin = skin * (0.35 + 0.75 * light[..., None])
    # blotchy texture
    blot = cv2.GaussianBlur(rng.normal(0, 1, (H // 8, W // 8)).astype(np.float32), (0, 0), 3)
    blot = cv2.resize(blot, (W, H))
    skin *= (1 + 0.10 * blot[..., None])
    img = img * (1 - face_m[..., None]) + skin * face_m[..., None]

    def shade(mask, amount, col=(0, 0, 0)):
        nonlocal img
        m = np.clip(mask, 0, 1)[..., None] * amount
        img = img * (1 - m) + np.array(col, np.float32) * m

    def ell(x0, y0, a, b, ang=0.0):
        ca, sa = math.cos(ang), math.sin(ang)
        X = (xx - x0) * ca + (yy - y0) * sa; Y = -(xx - x0) * sa + (yy - y0) * ca
        return np.sqrt((X / a) ** 2 + (Y / b) ** 2)

    # hollow cheeks
    for s in (-1, 1):
        shade(np.clip(1.3 - ell(cx + s * W * 0.22, cy + H * 0.08, W * 0.11, H * 0.12), 0, 1), 0.55)
    # temples / brow shadow
    shade(np.clip(1.2 - ell(cx, cy - H * 0.13, W * 0.33, H * 0.05), 0, 1), 0.35)

    # --- eye sockets (very dark)
    ey = cy - H * 0.075; ex = W * 0.15
    for s in (-1, 1):
        sock = np.clip((1.25 - ell(cx + s * ex, ey, W * 0.13, H * 0.062, s * 0.12)) * 2.2, 0, 1)
        shade(sock, 0.93, (6, 8, 7))
    # --- bulging eyes: big whites, tiny black pupils, red veins
    for s in (-1, 1):
        x0 = cx + s * ex + rng.uniform(-6, 6); y0 = ey + rng.uniform(-4, 4)
        a, b = W * 0.085, H * 0.042
        e = ell(x0, y0, a, b)
        white = np.clip((1 - e) * 12, 0, 1)
        sclera = np.array([196, 210, 212], np.float32) * (0.8 + 0.25 * np.clip(1 - e, 0, 1))[..., None]
        img = img * (1 - white[..., None]) + sclera * white[..., None]
        # veins: random walks from the rim toward the iris
        vimg = np.zeros((H, W), np.float32)
        for k in range(16):
            ang = rng.uniform(0, 2 * math.pi); r = 0.98
            px, py = x0 + a * r * math.cos(ang), y0 + b * r * math.sin(ang)
            pts = [(px, py)]
            for _ in range(10):
                px += (x0 - px) * 0.09 + rng.normal(0, 4); py += (y0 - py) * 0.09 + rng.normal(0, 3)
                pts.append((px, py))
            cv2.polylines(vimg, [np.array(pts, np.int32)], False, 1.0, int(rng.integers(1, 3)), cv2.LINE_AA)
        vimg = vimg * white
        img = img * (1 - 0.85 * vimg[..., None]) + np.array([30, 25, 150], np.float32) * 0.85 * vimg[..., None]
        # iris ring (faint) + pinprick pupil, staring at the camera
        px, py = x0 + gaze[0] * a * 0.25, y0 + gaze[1] * b * 0.25
        iris = np.clip((1 - ell(px, py, a * 0.26, a * 0.26)) * 10, 0, 1) * white
        img = img * (1 - 0.45 * iris[..., None]) + np.array([70, 90, 90], np.float32) * 0.45 * iris[..., None]
        pup = np.clip((1 - ell(px, py, a * 0.085, a * 0.085)) * 8, 0, 1)
        shade(pup, 1.0, (2, 2, 2))
        # wet highlight
        hl = np.clip((1 - ell(px - a * 0.12, py - b * 0.25, 7, 6)) * 4, 0, 1)
        img = img * (1 - hl[..., None]) + 245 * hl[..., None]
        # lower lid dark rim
        shade(np.clip(1.0 - np.abs(ell(x0, y0 + b * 0.15, a * 1.05, b * 1.15) - 1) * 9, 0, 1) * (yy > y0), 0.6, (20, 15, 30))

    # --- nose: long shadow + nostrils
    ny = cy + H * 0.04
    shade(np.clip(1.1 - ell(cx + W * 0.03, ny - H * 0.03, W * 0.022, H * 0.085), 0, 1), 0.55)
    for s in (-1, 1):
        shade(np.clip((1 - ell(cx + s * W * 0.028, ny + H * 0.045, W * 0.016, H * 0.007)) * 1.5, 0, 1), 0.7)

    # --- grin: stretched almost ear to ear, corners raised, black open mouth with a row of teeth
    my = cy + H * 0.14; half = W * 0.335
    t = np.linspace(-1, 1, 200)
    up = smile * H * 0.075
    upper = np.stack([cx + half * t, my - up * np.abs(t) ** 2.6 - H * 0.004 * (1 - t ** 2) + 0 * t], -1)
    lower = np.stack([cx + half * t, my - up * np.abs(t) ** 2.6 + H * 0.07 * (1 - t ** 2) ** 1.6], -1)
    poly = np.concatenate([upper, lower[::-1]]).astype(np.int32)
    mm = np.zeros((H, W), np.uint8); cv2.fillPoly(mm, [poly], 255, cv2.LINE_AA)
    mouth = cv2.GaussianBlur(mm.astype(np.float32) / 255, (0, 0), 1.5)
    # cheek creases along the grin
    cr_ = np.zeros((H, W), np.float32)
    for s in (-1, 1):
        pts = [(cx + s * (half + 10 - 30 * k), my - up - 30 + 34 * k * k) for k in np.linspace(0, 1.4, 12)]
        cv2.polylines(cr_, [np.array(pts, np.int32)], False, 1.0, 9, cv2.LINE_AA)
    shade(cv2.GaussianBlur(cr_, (0, 0), 6), 0.6)
    # lips: slightly darker, purplish rim
    rim = cv2.GaussianBlur(cv2.dilate(mm, np.ones((19, 19), np.uint8)).astype(np.float32) / 255, (0, 0), 4) - mouth
    shade(np.clip(rim, 0, 1), 0.55, (60, 40, 70))
    shade(mouth, 1.0, (4, 3, 6))
    # teeth: one row hanging from the upper lip, yellowed, uneven
    teeth = np.zeros((H, W), np.float32)
    n = 22
    for k in range(n):
        tt = -0.92 + 1.84 * (k + 0.5) / n
        x = cx + half * tt; y = my - up * abs(tt) ** 2.6 - 2
        w_ = half * 1.84 / n * 0.46; hgt = H * (0.019 + 0.005 * rng.random()) * (1 - 0.5 * tt * tt)
        pts = np.array([(x - w_, y), (x + w_, y), (x + w_ * 0.8, y + hgt), (x - w_ * 0.8, y + hgt * 0.95)], np.int32)
        cv2.fillConvexPoly(teeth, pts, 1.0, cv2.LINE_AA)
    teeth = teeth * mouth
    tcol = np.array([120, 175, 190], np.float32) * (0.75 + 0.3 * rng.random())
    img = img * (1 - teeth[..., None]) + tcol * teeth[..., None]
    gaps = np.zeros((H, W), np.float32)  # dark lines between teeth
    for k in range(n + 1):
        tt = -0.92 + 1.84 * k / n; x = cx + half * tt; y = my - up * abs(tt) ** 2.6
        cv2.line(gaps, (int(x), int(y)), (int(x), int(y + H * 0.025)), 1.0, 3, cv2.LINE_AA)
    shade(gaps * teeth, 0.8)

    # --- long black hair: solid curtains that eat the sides of the face + wet strands over cheeks and forehead
    hair = np.zeros((H, W), np.float32)
    for s_ in (-1, 1):
        for k in range(90):
            x = cx + s_ * rng.uniform(W * 0.16, W * 0.6); y = rng.uniform(-80, H * 0.15)
            pts = []
            for j in range(44):
                x += s_ * rng.normal(0.8, 3.5); y += H / 40; pts.append((x, y))
            cv2.polylines(hair, [np.array(pts, np.int32)], False, 1.0, int(rng.integers(6, 34)), cv2.LINE_AA)
    for k in range(60):        # fringe, parted in the middle, covering the forehead
        s_ = rng.choice((-1, 1)); x = cx + s_ * rng.uniform(0, W * 0.04); y = cy - H * 0.40
        pts = []
        for j in range(26):
            x += s_ * rng.uniform(3, 15); y += rng.uniform(8, 17); pts.append((x, y))
        cv2.polylines(hair, [np.array(pts, np.int32)], False, 1.0, int(rng.integers(6, 22)), cv2.LINE_AA)
    hair = np.clip(cv2.GaussianBlur(hair, (0, 0), 1.6), 0, 1)

    # keep the eyes, nose and grin clear: hair only over the outer cheeks, temples and forehead
    clear = np.clip((1.12 - ell(cx, cy + H * 0.05, W * 0.24, H * 0.20)) * 3, 0, 1)
    clear = np.maximum(clear, np.clip((1.05 - ell(cx, my + H * 0.01, half * 0.92, H * 0.06)) * 3, 0, 1))
    wav = cv2.resize(cv2.GaussianBlur(rng.normal(0, 1, (H // 40, 2)).astype(np.float32), (0, 0), 1.2), (W, H))
    wav = np.where(xx < cx, wav[:, :1], wav[:, 1:2]) if False else np.where(xx < cx, wav[:, 0:1] * np.ones((1, W), np.float32), wav[:, -1:] * np.ones((1, W), np.float32))
    edge = W * 0.255 - 0.16 * W * np.clip((yy - cy) / H, -0.3, 0.3) + W * 0.035 * wav
    side = np.clip((np.abs(xx - cx) - edge) / (W * 0.035), 0, 1)
    side = np.maximum(side, np.clip((yy - (cy + H * 0.27)) / (H * 0.04), 0, 1))
    hair = np.maximum(hair, cv2.GaussianBlur(side.astype(np.float32), (0, 0), 6)) * (1 - clear * 0.97)
    # shadow cast by the hair on the face
    shade(cv2.GaussianBlur(hair, (0, 0), 30), 0.5)
    hcol = np.array([8, 9, 8], np.float32) + 10 * np.clip(blot, -1, 1)[..., None]
    img = img * (1 - hair[..., None]) + hcol * hair[..., None]

    # --- old night photo: vignette, slight blur, grain, green-ish cast, JPEG
    vig = np.clip(1.25 - 0.9 * np.sqrt(((xx - cx) / (W * 0.55)) ** 2 + ((yy - cy) / (H * 0.55)) ** 2), 0.05, 1)
    img *= vig[..., None]
    img = cv2.GaussianBlur(img, (0, 0), 1.6)
    img += rng.normal(0, 13, (H, W, 1)).astype(np.float32) + rng.normal(0, 5, (H, W, 3)).astype(np.float32)
    img = np.clip(img, 0, 255).astype(np.uint8)
    M = cv2.getRotationMatrix2D((cx, cy), tilt, 1.0)
    img = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REPLICATE)
    small = cv2.resize(img, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    ok, enc = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 22])
    img = cv2.resize(cv2.imdecode(enc, 1), (W, H), interpolation=cv2.INTER_CUBIC)
    ok, enc = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 45])
    return cv2.imdecode(enc, 1)

if __name__ == '__main__':
    import sys
    im = make()
    cv2.imwrite(sys.argv[1] if len(sys.argv) > 1 else 'face_test.jpg', im)
