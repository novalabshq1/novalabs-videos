# Visage de screamer 100 % procédural (numpy + OpenCV). Usage: python3 face.py VARIANT_SEED out.png
import numpy as np, cv2, math, sys
def make_face(seed=13, tilt=-4.0, smile_up=0.20, gaze=(0.0, 0.0), W=1080, H=1920):
    rng = np.random.default_rng(seed)
    S = 2  # supersample
    w, h = W * S, H * S
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2, h * 0.47
    img = np.zeros((h, w, 3), np.float32)  # BGR, 0..1
    # dim background: dark brownish wall with noise
    img[:] = (0.035, 0.04, 0.045)
    # face: elongated ellipse
    fa, fb = 0.40 * w, 0.41 * h
    d = ((xx - cx) / fa) ** 2 + ((yy - cy) / fb) ** 2
    # narrow chin
    chin = np.clip((yy - cy) / fb, 0, 1)
    d = ((xx - cx) / (fa * (1 - 0.35 * chin ** 1.6))) ** 2 + ((yy - cy) / fb) ** 2
    face_mask = np.clip((1.0 - d) / 0.06, 0, 1)
    skin = np.array([0.58, 0.66, 0.60], np.float32)  # BGR pale grey-green
    shade = np.clip(1.15 - 0.85 * d, 0.15, 1.0)  # darker towards edges (one weak light from front)
    # light from slightly above-left
    shade *= np.clip(1.0 + 0.25 * ((cx - xx) / fa) - 0.15 * ((yy - cy) / fb), 0.5, 1.3)
    face = skin[None, None, :] * shade[..., None]
    def blob(x, y, rx, ry, k=1.0, ang=0.0):
        ca, sa = math.cos(ang), math.sin(ang)
        u = ((xx - x) * ca + (yy - y) * sa) / rx; v = (-(xx - x) * sa + (yy - y) * ca) / ry
        return k * np.exp(-(u * u + v * v))
    dark = np.zeros((h, w), np.float32)
    # hollow cheeks
    for s in (-1, 1):
        dark += blob(cx + s * 0.25 * w, cy + 0.11 * h, 0.07 * w, 0.10 * h, 0.55)
        dark += blob(cx + s * 0.31 * w, cy - 0.02 * h, 0.04 * w, 0.12 * h, 0.4)
    # temples
    for s in (-1, 1):
        dark += blob(cx + s * 0.30 * w, cy - 0.17 * h, 0.06 * w, 0.06 * h, 0.5)
    # nose shadow (long thin, under-nose)
    dark += blob(cx + 0.025 * w, cy + 0.02 * h, 0.022 * w, 0.075 * h, 0.55)
    dark += blob(cx, cy + 0.085 * h, 0.06 * w, 0.014 * h, 0.75)
    for s in (-1, 1):
        dark += blob(cx + s * 0.035 * w, cy + 0.08 * h, 0.013 * w, 0.008 * h, 1.2)  # nostrils
    # eye sockets: very dark
    ex, ey = 0.165 * w, cy - 0.105 * h
    for s in (-1, 1):
        dark += blob(cx + s * ex, ey, 0.15 * w, 0.085 * h, 2.4, s * 0.15)
        dark += blob(cx + s * ex, ey + 0.035 * h, 0.12 * w, 0.03 * h, 1.2)
    # smile-line creases
    for s in (-1, 1):
        dark += blob(cx + s * 0.20 * w, cy + 0.12 * h, 0.012 * w, 0.06 * h, 0.5, -s * 0.5)
    face = face * np.exp(-1.6 * dark)[..., None]
    img = img * (1 - face_mask[..., None]) + face * face_mask[..., None]
    # hair: long black hair framing face, eating the sides
    ytop = cy - 0.40 * h
    edge = np.clip((yy - ytop) / (0.20 * h), 0, 1) ** 0.6 * 0.255 * w + 0.012 * w
    edge = edge + 0.012 * w * np.sin(yy / h * 23 + 1.3) + 0.03 * w * np.clip((yy - (cy + 0.1 * h)) / (0.2 * h), 0, 1)
    hair = np.clip((np.abs(xx - cx + 0.01 * w) - edge) / (0.015 * w), 0, 1)
    hair = np.maximum(hair, np.clip((d - 0.92) / 0.08, 0, 1) * (yy < cy + 0.25 * h))
    strands = np.zeros((h, w), np.float32)
    for _ in range(260):
        s = rng.choice([-1, 1]); x = cx + s * rng.uniform(0.0, 0.08) * w; y = cy - 0.42 * h + rng.uniform(-0.03, 0.03) * h
        pts = []
        for k in range(30):
            pts.append((x, y)); y += h * 0.03; x += s * max(0.0, (0.03 - 0.0035 * k)) * w * rng.uniform(0.5, 1.6) + rng.normal(0, 0.004) * w
        cv2.polylines(strands, [np.int32(pts)], False, rng.uniform(0.6, 1.0), int(rng.uniform(4, 16) * S), cv2.LINE_AA)
    strands = cv2.GaussianBlur(strands, (0, 0), 3 * S)
    hmask = np.clip(np.maximum(hair, strands * 0.9), 0, 1)
    hcol = 0.006 + 0.014 * np.clip(strands, 0, 1)
    img = img * (1 - 0.97 * hmask[..., None]) + hcol[..., None] * hmask[..., None]
    # bulging eyes
    for s in (-1, 1):
        ecx, ecy = cx + s * ex + rng.uniform(-6, 6), ey + 0.005 * h
        erx, ery = 0.098 * w, 0.050 * h
        e = ((xx - ecx) / erx) ** 2 + ((yy - ecy) / ery) ** 2
        em = np.clip((1 - e) / 0.08, 0, 1)
        white = np.array([0.80, 0.86, 0.86], np.float32) * np.clip(1.08 - 0.45 * e, 0, 1)[..., None]
        # red veins: random walks from edge toward the iris
        vein = np.zeros((h, w), np.float32)
        for _ in range(14):
            a = rng.uniform(0, 2 * math.pi)
            px, py = ecx + erx * 0.98 * math.cos(a), ecy + ery * 0.98 * math.sin(a)
            pts = [(px, py)]
            for k in range(10):
                tx, ty = ecx - px, ecy - py; L = math.hypot(tx, ty) + 1e-6
                px += tx / L * 9 * S + rng.normal(0, 4 * S); py += ty / L * 5 * S + rng.normal(0, 4 * S)
                pts.append((px, py))
            cv2.polylines(vein, [np.int32(np.array(pts))], False, 1.0, max(1, int(rng.uniform(1, 2.5) * S)), cv2.LINE_AA)
        vein = cv2.GaussianBlur(vein, (0, 0), 1.2 * S)
        white = white * (1 - 0.8 * vein[..., None]) + np.array([0.08, 0.10, 0.62], np.float32) * (0.8 * vein[..., None])
        # tiny pupils staring at camera
        pcx, pcy = ecx + gaze[0] * erx * 0.2 - s * 0.03 * erx, ecy + gaze[1] * ery * 0.2
        ir = ((xx - pcx) ** 2 + (yy - pcy) ** 2) / (0.020 * w) ** 2
        white = white * (1 - np.clip((1 - ir) / 0.25, 0, 1)[..., None] * 0.65)  # faint iris ring
        pu = np.clip((1 - ((xx - pcx) ** 2 + (yy - pcy) ** 2) / (0.0085 * w) ** 2) / 0.2, 0, 1)
        white = white * (1 - pu[..., None] * 0.97)
        # lid shadow on top
        white *= np.clip(0.55 + 0.6 * ((yy - (ecy - ery)) / (2 * ery)), 0.4, 1.0)[..., None]
        img = img * (1 - em[..., None]) + white * em[..., None]
        # tiny specular so it looks wet
        img += blob(pcx - 0.012 * w, pcy - 0.010 * h, 0.004 * w, 0.0025 * h, 0.6)[..., None]
    # mouth: ear-to-ear smile
    my = cy + 0.16 * h; mw = 0.275 * w
    xs = np.linspace(-1, 1, 400)
    up = smile_up * h
    def curve(open_):
        top = my - 0.012 * h - up * np.abs(xs) ** 2.6 + 0.012 * h * np.cos(xs * 9) * 0.3
        bot = my + open_ * (1 - xs ** 2) ** 0.8 - up * np.abs(xs) ** 2.4
        return top, bot
    top, bot = curve(0.06 * h)
    px_ = cx + xs * mw
    poly = np.concatenate([np.stack([px_, top], 1), np.stack([px_[::-1], bot[::-1]], 1)])
    mm = np.zeros((h, w), np.float32)
    cv2.fillPoly(mm, [np.int32(poly)], 1.0, cv2.LINE_AA)
    mm = cv2.GaussianBlur(mm, (0, 0), 2 * S)
    # lips: dark grey-purple rim
    rim = cv2.GaussianBlur(mm, (0, 0), 9 * S) - mm
    img *= (1 - 0.6 * np.clip(rim * 3, 0, 1))[..., None]
    inner = np.array([0.01, 0.01, 0.025], np.float32)
    img = img * (1 - mm[..., None]) + inner * mm[..., None]
    # teeth: one row hanging from upper lip, slightly uneven
    teeth = np.zeros((h, w), np.float32); tcol = np.zeros((h, w), np.float32)
    n = 26
    for k in range(n):
        u0, u1 = -0.93 + 1.86 * k / n, -0.93 + 1.86 * (k + 1) / n
        i0, i1 = int((u0 + 1) / 2 * 399), int((u1 + 1) / 2 * 399)
        x0, x1 = px_[i0] + 2 * S, px_[i1] - 2 * S
        y0 = min(top[i0], top[i1]) - 4 * S
        ln = (bot[(i0 + i1) // 2] - top[(i0 + i1) // 2]) * rng.uniform(0.38, 0.55) * (1 - 0.4 * abs(u0)) + 6 * S
        y1 = max(top[i0], top[i1]) + ln
        pts = np.int32([[x0, y0], [x1, y0], [x1 - 2 * S, y1], [(x0 + x1) / 2 + rng.uniform(-3, 3) * S, y1 + 4 * S], [x0 + 2 * S, y1]])
        cv2.fillPoly(teeth, [pts], 1.0, cv2.LINE_AA)
        cv2.fillPoly(tcol, [pts], rng.uniform(0.75, 1.0), cv2.LINE_AA)
    teeth = teeth * mm
    tshade = np.clip(1.1 - 0.9 * np.abs(xx - cx) / mw, 0.25, 1)
    tc = np.array([0.42, 0.60, 0.66], np.float32)[None, None, :] * (tcol * tshade)[..., None]
    img = img * (1 - teeth[..., None]) + tc * teeth[..., None]
    # tilt
    M = cv2.getRotationMatrix2D((cx, cy), tilt, 1.0)
    img = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
    img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
    # night photo: vignette, low light, green cast, blur, grain, jpeg
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    vig = np.clip(1.25 - 1.1 * (((X - W / 2) / (W * 0.75)) ** 2 + ((Y - H * 0.47) / (H * 0.6)) ** 2), 0.05, 1)
    img = img * vig[..., None] * 0.95
    img = img * np.array([0.92, 1.0, 0.95], np.float32)
    img = cv2.GaussianBlur(img, (0, 0), 1.6)
    img = img + rng.normal(0, 0.045, (H, W, 1)).astype(np.float32) + rng.normal(0, 0.015, (H, W, 3)).astype(np.float32)
    img = np.clip(img, 0, 1) ** 1.05
    out = np.uint8(np.clip(img * 255, 0, 255))
    ok, buf = cv2.imencode('.jpg', out, [cv2.IMWRITE_JPEG_QUALITY, 18])
    return cv2.imdecode(buf, 1)
if __name__ == '__main__':
    cv2.imwrite(sys.argv[2], make_face(int(sys.argv[1])))
