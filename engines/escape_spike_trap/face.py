# Procedural screamer face (100% generated, no photo). python3 face.py [VARIANT_SEED] -> face_base.png + face_preview.png
# Variant knobs change one detail each night (tilt, smile, gaze, hair) while keeping the same level of fear.
import numpy as np, cv2, math, sys
VSEED = int(sys.argv[1]) if len(sys.argv) > 1 else 7
rv = np.random.default_rng(VSEED)
S = 1.6                                   # supersampling of the 1080x1920 canvas (zoom headroom)
W, H = int(1080 * S), int(1920 * S)
TILT = rv.uniform(-7, 7)                  # head tilt (deg)
SMILE_UP = rv.uniform(55, 95)             # how high the smile corners go
SMILE_ASYM = rv.uniform(-25, 25)          # one corner higher than the other
GAZE = rv.uniform(-6, 6, 2)               # tiny pupil offset (still staring at the camera)
HAIR_IN = rv.uniform(235, 270)            # how much the hair eats the sides
rng = np.random.default_rng(VSEED + 100)

def P(x, y): return (int(round(x * S)), int(round(y * S)))
def soft(mask, sig): return cv2.GaussianBlur(mask, (0, 0), sig * S)
def ell(cx, cy, ax, ay, ang=0, sig=0):
    m = np.zeros((H, W), np.float32)
    cv2.ellipse(m, P(cx, cy), (int(ax * S), int(ay * S)), ang, 0, 360, 1.0, -1, cv2.LINE_AA)
    return soft(m, sig) if sig else m
def poly(pts, sig=0):
    m = np.zeros((H, W), np.float32)
    cv2.fillPoly(m, [np.array([P(x, y) for x, y in pts], np.int32)], 1.0, cv2.LINE_AA)
    return soft(m, sig) if sig else m
def lay(img, mask, col, a=1.0):
    m = (mask * a)[..., None]; img[:] = img * (1 - m) + np.array(col, np.float32)[None, None] * m

img = np.zeros((H, W, 3), np.float32)        # BGR, 0..1
# background: dark, damp wall with blotches
lowf = cv2.resize(rng.standard_normal((24, 14)).astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
img[:] = (0.035 + 0.012 * lowf)[..., None] * np.array([0.9, 1.0, 0.85])
CXF, CYF = 540, 960
# ---------- skin ----------
face = ell(CXF, CYF, 335, 650, 0, 6)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32) / S
d = np.sqrt(((xx - CXF) / 335) ** 2 + ((yy - CYF + 60) / 650) ** 2)
shade = np.clip(1.05 - 0.75 * d ** 2.2, 0.15, 1)                   # weak flash from the front
blot = cv2.resize(rng.standard_normal((40, 24)).astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
skin = np.array([0.56, 0.64, 0.57])                                 # pale grey-green (BGR)
lay(img, face, (0, 0, 0))
img += face[..., None] * (skin[None, None] * (shade * (1 + 0.06 * blot))[..., None])
# hollow cheeks, temples, under-cheekbone shadows
for sx in (-1, 1):
    lay(img, ell(CXF + sx * 225, 1150, 85, 175, sx * 12, 40), (0.07, 0.09, 0.07), 0.75)
    lay(img, ell(CXF + sx * 270, 640, 70, 160, 0, 45), (0.06, 0.07, 0.06), 0.6)
    lay(img, ell(CXF + sx * 120, 1000, 40, 60, 0, 30), (0.2, 0.24, 0.2), 0.35)   # under-eye sag
# forehead wrinkle lines
for k in range(3):
    y0 = 520 + 38 * k
    pts = np.array([P(CXF - 170 + 340 * u, y0 + 12 * math.sin(u * 6 + k) - 18 * (1 - (2 * u - 1) ** 2)) for u in np.linspace(0, 1, 30)], np.int32)
    m = np.zeros((H, W), np.float32); cv2.polylines(m, [pts], False, 1.0, int(3 * S), cv2.LINE_AA)
    lay(img, soft(m, 2), (0.15, 0.18, 0.15), 0.5)
# ---------- nose ----------
lay(img, poly([(CXF + 18, 820), (CXF + 48, 820), (CXF + 70, 1110), (CXF + 25, 1100)], 14), (0.08, 0.1, 0.08), 0.7)
lay(img, ell(CXF, 1120, 80, 26, 0, 14), (0.05, 0.06, 0.05), 0.85)
for sx in (-1, 1): lay(img, ell(CXF + sx * 26, 1108, 15, 9, sx * 20, 2), (0.01, 0.01, 0.01), 0.95)
lay(img, ell(CXF - 12, 980, 10, 90, 0, 10), (0.75, 0.82, 0.75), 0.25)        # faint bridge highlight
# ---------- eyes ----------
EY = 835
for sx in (-1, 1):
    ex = CXF + sx * 150
    lay(img, ell(ex, EY + 5, 140, 120, sx * 8, 26), (0.0, 0.0, 0.0), 0.97)   # very dark sockets
    lay(img, ell(ex, EY + 5, 175, 150, sx * 8, 50), (0.0, 0.0, 0.0), 0.55)
    R = 66 + (5 if sx > 0 else 0)                                             # bulging eyeballs
    eye = ell(ex, EY, R, R * 0.93, 0, 1.2)
    ey_d = np.sqrt((xx - ex) ** 2 + (yy - EY) ** 2) / R
    white = np.array([0.80, 0.86, 0.88]) * np.clip(1.08 - 0.5 * ey_d ** 3, 0.3, 1)[..., None]
    img[:] = img * (1 - eye[..., None]) + white * eye[..., None]
    # red veins: random walks from the rim towards the pupil
    vm = np.zeros((H, W), np.float32)
    for v in range(16):
        a = rng.uniform(0, 2 * math.pi); r0 = R * 0.98
        x, y = ex + r0 * math.cos(a), EY + r0 * math.sin(a); pts = [P(x, y)]
        for st in range(int(rng.integers(5, 10))):
            a2 = math.atan2(EY - y, ex - x) + rng.normal(0, 0.8); stp = rng.uniform(4, 8)
            x += stp * math.cos(a2); y += stp * math.sin(a2); pts.append(P(x, y))
        cv2.polylines(vm, [np.array(pts, np.int32)], False, 1.0, max(1, int(1.4 * S)), cv2.LINE_AA)
    lay(img, soft(vm, 0.6) * eye, (0.12, 0.10, 0.62), 0.9)
    lay(img, ell(ex, EY - R * 0.55, R * 1.05, R * 0.45, 0, 10) * eye, (0.15, 0.15, 0.15), 0.45)  # lid shadow
    px, py = ex - sx * 3 + GAZE[0], EY + 4 + GAZE[1]                          # staring at the camera
    lay(img, ell(px, py, 17, 17, 0, 1), (0.22, 0.24, 0.2), 0.8)
    lay(img, ell(px, py, 8.5, 8.5, 0, 0.6), (0.0, 0.0, 0.0), 1.0)
    lay(img, ell(px + 4, py - 4, 2.2, 2.2, 0, 0.4), (0.9, 0.9, 0.9), 0.7)     # tiny catch-light (camera flash)
    lay(img, ell(ex, EY, R + 6, R * 0.93 + 6, 0, 3) - eye, (0.02, 0.03, 0.02), 0.6)  # rim
    # eyebrow-less heavy brow ridge shadow
    lay(img, ell(ex + sx * 10, EY - 120, 135, 32, sx * 10, 16), (0.05, 0.06, 0.05), 0.55)
# ---------- smile ----------
MY = 1250; HW = 305
def up_y(u):   return MY - SMILE_UP * u ** 2 - SMILE_ASYM * u * 0.5 * (u > 0) - 8 * (1 - u * u)
def lo_y(u):   return MY + 92 * (1 - u ** 2) ** 1.2 - SMILE_UP * u ** 2 - SMILE_ASYM * u * 0.5 * (u > 0)
us = np.linspace(-1, 1, 80)
upper = [(CXF + HW * u, up_y(u)) for u in us]; lower = [(CXF + HW * u, lo_y(u)) for u in us[::-1]]
lip = [(CXF + HW * 1.04 * u, up_y(u) - 14 * (1 - u * u)) for u in us] + [(CXF + HW * 1.04 * u, lo_y(u) + 22 * (1 - u * u) ** 0.8) for u in us[::-1]]
lay(img, poly(lip, 5), (0.20, 0.22, 0.30), 0.85)                 # thin cracked lips
lay(img, poly(upper + lower, 1.5), (0.0, 0.0, 0.0), 1.0)         # black open mouth
# teeth: one row hanging from the upper lip
nt = 22
for k in range(nt):
    u0, u1 = -0.86 + 1.72 * k / nt, -0.86 + 1.72 * (k + 1) / nt
    um = (u0 + u1) / 2
    hgt = (40 + 14 * rng.uniform(-1, 1)) * (1 - 0.55 * um * um)
    top0, top1 = up_y(u0) - 2, up_y(u1) - 2
    xa, xb = CXF + HW * u0 + 2.2, CXF + HW * u1 - 2.2
    bot = (top0 + top1) / 2 + hgt
    tooth = poly([(xa, top0), (xb, top1), (xb - 2, bot - 8), ((xa + xb) / 2, bot), (xa + 2, bot - 8)], 0.9)
    tc = np.array([0.55, 0.70, 0.74]) * (0.75 + 0.25 * rng.random()) * (1 - 0.45 * abs(um))
    lay(img, tooth, tuple(tc), 1.0)
    lay(img, ell((xa + xb) / 2, bot - 5, (xb - xa) * 0.45, 7, 0, 3) * tooth, (0.2, 0.32, 0.4), 0.5)
# smile creases running up the cheeks
for sx in (-1, 1):
    u = sx * 1.0
    x0, y0 = CXF + HW * u, up_y(u)
    pts = [P(x0 + sx * 10 * k, y0 - 22 * k + 2 * k * k) for k in range(8)]
    m = np.zeros((H, W), np.float32); cv2.polylines(m, [np.array(pts, np.int32)], False, 1.0, int(6 * S), cv2.LINE_AA)
    lay(img, soft(m, 4), (0.03, 0.04, 0.03), 0.8)
    lay(img, ell(x0 + sx * 4, y0 + 4, 16, 12, 0, 4), (0.0, 0.0, 0.0), 0.9)
lay(img, ell(CXF, 1450, 140, 40, 0, 30), (0.06, 0.07, 0.06), 0.45)   # chin shadow
# ---------- long black hair eating the sides ----------
inner = ell(CXF, CYF + 30, HAIR_IN, 640, 0, 22)
top = ell(CXF, 300, 380, 230, 0, 30)
hair = np.clip(1 - inner + top * 0.0, 0, 1)
part = poly([(CXF - 10, 250), (CXF + 10, 250), (CXF + 200, 560), (CXF - 200, 560)], 30)
hair = np.clip(np.maximum(hair, ell(CXF, 330, 330, 170, 0, 30)) - 0.0 * part, 0, 1)
lay(img, hair, (0.012, 0.014, 0.012), 0.97)
# strands: faint dim highlights + a few crossing the face
sm = np.zeros((H, W), np.float32)
for k in range(260):
    side = -1 if k % 2 else 1
    x = CXF + side * rng.uniform(150, 560); y = rng.uniform(150, 400)
    pts = []
    for st in range(60):
        pts.append(P(x, y)); y += 30; x += side * rng.uniform(-1, 4) + 3 * math.sin(y / 120 + k)
    cv2.polylines(sm, [np.array(pts, np.int32)], False, float(rng.uniform(0.3, 1)), max(1, int(rng.uniform(1, 2.5) * S)), cv2.LINE_AA)
lay(img, soft(sm, 0.8) * hair, (0.10, 0.11, 0.10), 0.5)
cm = np.zeros((H, W), np.float32)
for k in range(14):                                                    # stray strands over the forehead/cheeks
    side = -1 if k % 2 else 1
    x = CXF + side * rng.uniform(120, 250); y = rng.uniform(380, 460)
    pts = []
    for st in range(int(rng.integers(10, 30))):
        pts.append(P(x, y)); y += 22; x += side * rng.uniform(0, 3.5)
    cv2.polylines(cm, [np.array(pts, np.int32)], False, 1.0, max(1, int(rng.uniform(1.5, 3) * S)), cv2.LINE_AA)
lay(img, soft(cm, 0.7), (0.01, 0.012, 0.01), 0.85)
# ---------- night photo look: vignette, slight blur ----------
vig = np.clip(1.15 - 0.85 * (((xx - 540) / 620) ** 2 + ((yy - 950) / 1050) ** 2), 0.05, 1)
img *= vig[..., None]
img = cv2.GaussianBlur(img, (0, 0), 1.1 * S)
M = cv2.getRotationMatrix2D((W / 2, H / 2), TILT, 1.0)
img = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
out = np.clip(img * 255, 0, 255).astype(np.uint8)
cv2.imwrite('face_base.png', out)
print('variant', VSEED, 'tilt %.1f smile_up %.0f asym %.0f gaze %s hair_in %.0f' % (TILT, SMILE_UP, SMILE_ASYM, np.round(GAZE, 1), HAIR_IN))
