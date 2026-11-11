# Visage du screamer 100 % généré par code (numpy/OpenCV). Usage: python3 face.py SEED TILT_DEG SMILE GAZE_X OUT.png
# Style : vieille photo de nuit (flash faible, grain, flou, JPEG). Change SEED/TILT/SMILE/GAZE chaque soir.
import numpy as np, cv2, sys, math
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 1
TILT = float(sys.argv[2]) if len(sys.argv) > 2 else -6.0
SMILE = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0      # 1.0 = sourire d'oreille à oreille
GAZE = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0       # décalage des pupilles (px)
OUT = sys.argv[5] if len(sys.argv) > 5 else 'face.png'
SCALE = 1.45
W, H = 1080, 1920
rng = np.random.default_rng(SEED)
Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
FX, FY, RX, RY = 540.0, 880.0, 300.0, 540.0
def g2(x0, y0, sx, sy, a=1.0):
    return a * np.exp(-(((X - x0) / sx) ** 2 + ((Y - y0) / sy) ** 2))
# ---------- height field of the face ----------
u = (X - FX) / RX; v = (Y - FY) / RY
inside = np.clip(1 - u ** 2 - v ** 2, 0, None)
h = np.sqrt(inside) * 260
EY = 735.0; EXS = 132.0
for s in (-1, 1):
    h -= g2(FX + s * EXS, EY, 105, 80, 85)              # deep eye sockets
    h += g2(FX + s * 150, EY - 105, 120, 30, 25)         # brow ridge
    h += g2(FX + s * 205, 870, 70, 50, 30)               # cheekbones
    h -= g2(FX + s * 185, 1010, 85, 110, 55)             # hollow cheeks
    h -= g2(FX + s * 120, 650, 40, 120, 10)
h += g2(FX, 860, 26, 120, 55) + g2(FX, 960, 42, 30, 40)  # nose ridge + tip
h -= g2(FX, 1205, 80, 40, 12)
h += g2(FX, 1300, 120, 70, 25)                           # chin
# ---------- shading (weak flash from the camera, slightly above) ----------
gy, gx = np.gradient(cv2.GaussianBlur(h, (0, 0), 6))
n = np.dstack([-gx, -gy, np.ones_like(h)]); n /= np.linalg.norm(n, axis=2, keepdims=True)
L = np.array([0.10, -0.45, 1.0]); L /= np.linalg.norm(L)
diff = np.clip(n @ L, 0, 1) ** 1.6
facemask = cv2.GaussianBlur((inside > 0).astype(np.float32), (0, 0), 14)
shade = 0.10 + 0.90 * diff
# occlusion in sockets / under nose / cheeks
occ = np.ones_like(h)
for s in (-1, 1):
    occ *= 1 - g2(FX + s * EXS, EY + 5, 100, 78, 0.93)
    occ *= 1 - g2(FX + s * 190, 1020, 80, 95, 0.55)
occ *= 1 - g2(FX + 10, 1000, 70, 22, 0.75)               # nose shadow
occ *= 1 - g2(FX - 22, 900, 18, 80, 0.45)
occ *= 1 - g2(FX, 1390, 260, 60, 0.6)                    # under the chin
alb = np.array([0.62, 0.70, 0.60], np.float32)            # pale grey-green (RGB)
mott = cv2.GaussianBlur(rng.standard_normal((H, W)).astype(np.float32), (0, 0), 9) * 0.35
img = (alb[None, None, :] * (shade * occ * (1 + 0.12 * mott))[..., None]) * facemask[..., None]
# dark veins on temples / forehead
def vein(x, y, ang, n, w, col, a):
    pts = [(x, y)]
    for _ in range(n):
        ang += rng.normal(0, 0.35); x += 7 * math.cos(ang); y += 7 * math.sin(ang); pts.append((x, y))
    lay = np.zeros((H, W), np.float32)
    cv2.polylines(lay, [np.int32(pts)], False, 1.0, w, cv2.LINE_AA)
    return cv2.GaussianBlur(lay, (0, 0), 1.2) * a
vm = np.zeros((H, W), np.float32)
for s in (-1, 1):
    for _ in range(4):
        vm += vein(FX + s * rng.uniform(200, 250), rng.uniform(560, 700), math.pi / 2 + s * rng.uniform(0.2, 0.9), 25, 2, 1, 0.35)
img *= (1 - vm[..., None] * np.array([0.6, 0.45, 0.5]))
# ---------- eyes : bulging, sclera all around, tiny pupils, red veins ----------
for s in (-1, 1):
    ex, ey = FX + s * EXS, EY + 8
    a, b = 74, 66
    em = ((X - ex) / a) ** 2 + ((Y - ey) / b) ** 2
    m = cv2.GaussianBlur((em < 1).astype(np.float32), (0, 0), 1.5)
    sph = np.sqrt(np.clip(1 - em, 0, 1))
    scl = np.dstack([0.86 + 0 * X, 0.86 + 0 * X, 0.80 + 0 * X]) * (0.45 + 0.55 * sph)[..., None]
    rim = np.clip(em, 0, 1) ** 3
    scl = scl * (1 - 0.5 * rim[..., None]) + rim[..., None] * np.array([0.35, 0.05, 0.05]) * 0.6
    # veins
    lay = np.zeros((H, W), np.float32)
    for _ in range(30):
        ang = rng.uniform(0, 2 * math.pi)
        x, y = ex + 0.98 * a * math.cos(ang), ey + 0.98 * b * math.sin(ang)
        pts = [(x, y)]; d = ang + math.pi
        for _ in range(int(rng.integers(5, 10))):
            d += rng.normal(0, 0.5); x += 5 * math.cos(d); y += 5 * math.sin(d); pts.append((x, y))
        cv2.polylines(lay, [np.int32(pts)], False, 1.0, 1, cv2.LINE_AA)
    lay = cv2.GaussianBlur(lay, (0, 0), 0.7) * 0.9
    scl = scl * (1 - lay[..., None]) + lay[..., None] * np.array([0.55, 0.04, 0.04])
    px, py = ex + GAZE - s * 3, ey - 2
    irm = np.clip(1 - np.hypot(X - px, Y - py) / 15, 0, 1)
    scl *= (1 - 0.55 * (irm > 0)[..., None] * np.array([1, 1, 1]))
    pm = cv2.GaussianBlur((np.hypot(X - px, Y - py) < 7.5).astype(np.float32), (0, 0), 0.8)
    scl *= (1 - pm[..., None])
    hl = g2(px + 9, py - 9, 3, 3, 0.8)                     # tiny catch light (camera flash)
    scl += hl[..., None]
    img = img * (1 - m[..., None]) + scl * m[..., None]
    # thin dark lids hugging the bulging eye
    lid = ((em > 0.92) & (em < 1.28)).astype(np.float32)
    img *= (1 - cv2.GaussianBlur(lid, (0, 0), 2)[..., None] * 0.8)
# ---------- mouth : unnaturally wide grin, corners up, black gap, row of teeth ----------
MY, MW = 1110.0, 245.0 * SMILE
uu = np.linspace(-1, 1, 400)
mx = FX + MW * uu
cy = MY - 55 * uu ** 2 - 95 * uu ** 6 + rng.uniform(-4, 4)
op = 58 * (1 - uu ** 2) ** 0.7 + 4 + 6 * np.sin(uu * 9 + SEED)
up_y = cy - op * 0.55; lo_y = cy + op
poly = np.int32(np.concatenate([np.stack([mx, up_y], 1), np.stack([mx, lo_y], 1)[::-1]]))
mm = np.zeros((H, W), np.float32); cv2.fillPoly(mm, [poly], 1.0, cv2.LINE_AA)
mmb = cv2.GaussianBlur(mm, (0, 0), 1.5)
inner = np.dstack([0.015 + 0 * X, 0.005 + 0 * X, 0.005 + 0 * X])
img = img * (1 - mmb[..., None]) + inner * mmb[..., None]
# lips : thin dark line + lip shadow around
lipm = np.zeros((H, W), np.float32)
cv2.polylines(lipm, [np.int32(np.stack([mx, up_y - 3], 1))], False, 1.0, 7, cv2.LINE_AA)
cv2.polylines(lipm, [np.int32(np.stack([mx, lo_y + 4], 1))], False, 0.7, 9, cv2.LINE_AA)
lipm = cv2.GaussianBlur(lipm, (0, 0), 3)
img *= (1 - 0.65 * lipm[..., None])
img *= (1 - g2(FX, MY + 70, 230, 40, 0.45))[..., None]       # shadow under lower lip
for s in (-1, 1):                                            # deep creases at raised corners
    cr_ = np.zeros((H, W), np.float32)
    x0, y0 = FX + s * MW, MY - 150
    cv2.ellipse(cr_, (int(x0 - s * 25), int(y0 + 30)), (40, 95), s * 20, -70, 70, 1.0, 4, cv2.LINE_AA)
    img *= (1 - cv2.GaussianBlur(cr_, (0, 0), 6) * 0.6)[..., None]
# teeth: one row hanging from the upper lip, narrower toward the corners
tm = np.zeros((H, W, 3), np.float32); ta = np.zeros((H, W), np.float32)
k = -0.92
while k < 0.92:
    wdt = 0.085 * (1 - 0.55 * abs(k)) * rng.uniform(0.85, 1.15)
    x0, x1 = FX + MW * k, FX + MW * (k + wdt)
    kc = k + wdt / 2
    ytop = MY - 55 * kc ** 2 - 95 * kc ** 6 - (58 * (1 - kc ** 2) ** 0.7 + 4 + 6 * math.sin(kc * 9 + SEED)) * 0.55
    hgt = 0.8 * (58 * (1 - kc ** 2) ** 0.7 + 4 + 6 * math.sin(kc * 9 + SEED)) * rng.uniform(0.8, 1.25)
    pts = np.int32([(x0 + 2, ytop - 2), (x1 - 2, ytop - 2), (x1 - 3, ytop + hgt * 0.9), ((x0 + x1) / 2, ytop + hgt), (x0 + 3, ytop + hgt * 0.9)])
    lay = np.zeros((H, W), np.float32); cv2.fillPoly(lay, [pts], 1.0, cv2.LINE_AA)
    shadeT = (1 - 0.6 * abs(kc)) * rng.uniform(0.7, 1.0)
    col = np.array([0.74, 0.68, 0.50]) * shadeT * (0.6 if rng.random() < 0.15 else 1.0)
    tm += lay[..., None] * col; ta = np.maximum(ta, lay)
    k += wdt + 0.006
tgrad = np.clip((Y - (MY - 60)) / 120, 0, 1)                 # teeth darker toward the gap
tm *= (1 - 0.5 * tgrad)[..., None]
ta = cv2.GaussianBlur(ta, (0, 0), 0.8) * mm
img = img * (1 - ta[..., None]) + tm * (ta > 0)[..., None] * 1.0
# nostrils
for s in (-1, 1):
    img *= (1 - g2(FX + s * 26, 985, 13, 8, 0.85))[..., None]
# ---------- long black hair eating the sides ----------
def hw(y):    # visible half-width of the face between the hair curtains
    return np.interp(y, [300, 450, 650, 900, 1150, 1350, 1500, 1920], [40, 150, 245, 265, 240, 175, 90, 60])
hm = np.zeros((H, W), np.float32)
dx = np.abs(X - FX - 0.02 * (Y - 880))
hm = np.clip((dx - hw(Y)) / 18 + 0.5, 0, 1)
ytop = 560 - 170 * np.exp(-((X - FX - 25) / 110) ** 2) - 60 * np.exp(-((X - FX) / 200) ** 2)
hm = np.maximum(hm, np.clip((ytop - Y) / 22 + 0.5, 0, 1))  # fringe with an off-centre parting
hm = np.maximum(hm, (Y < 300).astype(np.float32))
strands = np.zeros((H, W), np.float32); sheen = np.zeros((H, W), np.float32)
for i in range(900):
    side = -1 if i % 2 else 1
    x = FX + side * rng.uniform(0, 140); y = rng.uniform(150, 320)
    edge = rng.uniform(-30, 25) if rng.random() > 0.08 else rng.uniform(-45, -20)
    pts = []
    yy = y
    while yy < H + 20:
        target = FX + side * (hw(yy) + edge + 30 * math.sin(yy / 260 + i))
        x += (target - x) * 0.12 + rng.normal(0, 2)
        pts.append((x, yy)); yy += 16
    p = np.int32(pts)
    cv2.polylines(strands, [p], False, 1.0, int(rng.integers(2, 5)), cv2.LINE_AA)
    if rng.random() < 0.25:
        cv2.polylines(sheen, [p], False, float(rng.uniform(0.3, 1.0)), 1, cv2.LINE_AA)
strands = cv2.GaussianBlur(strands, (0, 0), 1.0)
hmask = np.clip(hm + 0.85 * strands * (np.abs(X - FX) > hw(Y) - 50), 0, 1)
hair_col = 0.012 + 0.16 * cv2.GaussianBlur(sheen, (0, 0), 1.2) * np.clip(1 - np.abs(X - FX) / 520, 0, 1)
img = img * (1 - hmask[..., None]) + (hair_col[..., None] * np.array([0.9, 1.0, 0.95])) * hmask[..., None]
img *= (1 - 0.6 * cv2.GaussianBlur((np.abs(np.abs(X - FX) - hw(Y)) < 14).astype(np.float32) * (1 - hm), (0, 0), 10))[..., None]
# ---------- night photo: falloff, colour cast, blur, grain, tilt ----------
fall = np.clip(1.15 - (((X - 540) / 620) ** 2 + ((Y - 860) / 820) ** 2), 0.03, 1) ** 1.3
img = img * fall[..., None] * np.clip(1.08 - 0.25 * (X - 300) / 600, 0.6, 1.1)[..., None]
img = img ** 0.95 * np.array([0.92, 1.0, 0.90]) + np.array([0.010, 0.016, 0.012])
M = cv2.getRotationMatrix2D((540, 860), TILT, SCALE)
img = cv2.warpAffine(img.astype(np.float32), M, (W, H), borderMode=cv2.BORDER_REPLICATE)
img = cv2.GaussianBlur(img, (0, 0), 1.6)
img += cv2.GaussianBlur(rng.standard_normal((H, W, 1)).astype(np.float32), (0, 0), 0.8)[..., None].reshape(H, W, 1) * 0.045
img = np.clip(img, 0, 1)
bgr = (img[..., ::-1] * 255).astype(np.uint8)
ok, enc = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 22]); bgr = cv2.imdecode(enc, 1)
cv2.imwrite(OUT, bgr); print('face', OUT)
