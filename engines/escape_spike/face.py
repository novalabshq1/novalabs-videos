# Procedural screamer face (100% generated with numpy/OpenCV, no photos). base_face(seed, variant) -> BGR float image 1080x1920
import numpy as np, cv2, math
W, H = 1080, 1920

def gblur(a, s):
    k = int(s * 3) * 2 + 1
    return cv2.GaussianBlur(a, (k, k), s)

def ell_mask(cx, cy, rx, ry, ang=0, blur=0):
    m = np.zeros((H, W), np.float32)
    cv2.ellipse(m, (int(cx), int(cy)), (int(rx), int(ry)), ang, 0, 360, 1.0, -1, cv2.LINE_AA)
    return gblur(m, blur) if blur else m

def poly_mask(pts, blur=0):
    m = np.zeros((H, W), np.float32)
    cv2.fillPoly(m, [np.round(np.array(pts)).astype(np.int32)], 1.0, cv2.LINE_AA)
    return gblur(m, blur) if blur else m

def mix(img, mask, col):
    col = np.array(col, np.float32)
    img[:] = img * (1 - mask[..., None]) + col * mask[..., None]

def base_face(seed=7, tilt=-5.0, smile_w=345, smile_lift=150, look=(0, 0), hair_seed=3):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    img = np.zeros((H, W, 3), np.float32)
    # background: almost black, faint green-grey noise
    img[:] = (0.035, 0.045, 0.04)
    FX, FY, RX, RY = 540, 900, 400, 650
    skin = np.array((0.60, 0.70, 0.64), np.float32)   # BGR pale grey-green
    face = ell_mask(FX, FY, RX, RY, 0, 14)
    # light falloff: weak frontal flash, dark rim
    d = np.sqrt(((xx - FX) / RX) ** 2 + ((yy - FY + 120) / RY) ** 2)
    light = np.clip(1.22 - 0.62 * d ** 2.4, 0.12, 1.0)
    shade = skin[None, None] * light[..., None]
    # mottled skin
    mott = gblur(rng.standard_normal((H, W)).astype(np.float32), 18) * 2.5
    shade *= (1 + 0.10 * mott)[..., None]
    img[:] = img * (1 - face[..., None]) + shade * face[..., None]
    # hollow cheeks + temples
    for sx in (-1, 1):
        mix(img, ell_mask(FX + sx * 245, FY + 150, 110, 210, sx * 12, 45) * 0.85, (0.05, 0.07, 0.06))
        mix(img, ell_mask(FX + sx * 300, FY - 260, 90, 200, 0, 50) * 0.55, (0.05, 0.06, 0.05))
    # brow ridge highlight and deep sockets
    for sx in (-1, 1):
        ex = FX + sx * 172
        mix(img, ell_mask(ex, FY - 255, 150, 50, sx * 8, 25) * 0.25, (0.80, 0.88, 0.82))
        mix(img, ell_mask(ex, FY - 175, 175, 150, sx * 10, 34) * 1.0, (0.01, 0.015, 0.012))
    # nose: bridge highlight, side shadow, nostrils
    mix(img, poly_mask([(FX - 18, FY - 170), (FX + 14, FY - 170), (FX + 30, FY + 60), (FX - 30, FY + 60)], 14) * 0.3, (0.82, 0.9, 0.84))
    mix(img, poly_mask([(FX + 22, FY - 150), (FX + 70, FY + 40), (FX + 30, FY + 90), (FX + 5, FY - 120)], 20) * 0.7, (0.03, 0.04, 0.035))
    mix(img, ell_mask(FX, FY + 95, 85, 40, 0, 22) * 0.6, (0.04, 0.05, 0.045))
    for sx in (-1, 1):
        mix(img, ell_mask(FX + sx * 36, FY + 92, 20, 12, sx * 20, 4), (0.0, 0.0, 0.0))
    # EYES: bulging sclera, tiny pupils, red veins
    for sx in (-1, 1):
        ex, ey = FX + sx * 172, FY - 175
        rx, ry = 92, 74
        scl = ell_mask(ex, ey, rx, ry, 0, 2)
        sc = np.stack([np.full((H, W), 0.80), np.full((H, W), 0.86), np.full((H, W), 0.88)], -1).astype(np.float32)
        # shading on the eyeball (round)
        de = np.sqrt(((xx - ex) / rx) ** 2 + ((yy - ey) / ry) ** 2)
        sc *= np.clip(1.05 - 0.45 * de ** 2, 0.3, 1)[..., None]
        img[:] = img * (1 - scl[..., None]) + sc * scl[..., None]
        # veins
        vein = np.zeros((H, W), np.float32)
        for _ in range(26):
            a = rng.uniform(0, 2 * math.pi); r = 1.0
            px, py = ex + rx * r * math.cos(a), ey + ry * r * math.sin(a)
            pts = [(px, py)]
            for _k in range(rng.integers(4, 9)):
                a2 = math.atan2(ey - py, ex - px) + rng.normal(0, 0.7)
                st = rng.uniform(6, 14)
                px += st * math.cos(a2); py += st * math.sin(a2); pts.append((px, py))
                if math.hypot(px - ex, py - ey) < 30: break
            cv2.polylines(vein, [np.array(pts, np.int32)], False, rng.uniform(0.5, 1.0), 1 + int(rng.random() < 0.3), cv2.LINE_AA)
        vein = gblur(vein, 0.8) * scl
        mix(img, np.clip(vein, 0, 1) * 0.85, (0.08, 0.06, 0.62))
        # pupil: tiny, black, staring at camera, with a pinprick catchlight
        px, py = ex - sx * 6 + look[0], ey + 2 + look[1]
        mix(img, ell_mask(px, py, 26, 26, 0, 3) * 0.55, (0.20, 0.25, 0.22))   # faint iris ring
        mix(img, ell_mask(px, py, 12, 12, 0, 1), (0.0, 0.0, 0.0))
        mix(img, ell_mask(px - 4, py - 4, 3, 3, 0, 1) * 0.8, (0.9, 0.95, 0.95))
        # dark rim / lids around the eye
        rim = ell_mask(ex, ey, rx + 10, ry + 9, 0, 5) - ell_mask(ex, ey, rx, ry, 0, 2)
        mix(img, np.clip(rim, 0, 1) * 0.9, (0.02, 0.02, 0.03))
        # red raw lower lid
        mix(img, np.clip(ell_mask(ex, ey + 12, rx + 4, ry + 4, 0, 4) - ell_mask(ex, ey - 2, rx + 2, ry, 0, 3), 0, 1) * 0.55, (0.10, 0.10, 0.40))
    # MOUTH: unnaturally wide grin, corners lifted
    MY = FY + 300
    us = np.linspace(-1, 1, 120)
    up = [(FX + smile_w * u, MY - 20 - smile_lift * u ** 4 - 25 * u ** 2 + 12 * u) for u in us]
    lo = [(FX + smile_w * u, MY - 20 - smile_lift * u ** 4 - 25 * u ** 2 + 12 * u + 120 * (1 - u ** 2) ** 1.3) for u in us]
    mpoly = up + lo[::-1]
    # lips / crease shadow around the mouth
    mix(img, poly_mask(mpoly, 9) * 0.5, (0.05, 0.05, 0.06))
    mouth = poly_mask(mpoly, 1.5)
    mix(img, mouth, (0.0, 0.0, 0.01))
    # teeth row along the upper lip
    teeth = np.zeros((H, W), np.float32); tcol = np.zeros((H, W, 3), np.float32)
    nt = 22
    for k in range(nt):
        u0 = -0.9 + 1.8 * k / nt; u1 = -0.9 + 1.8 * (k + 1) / nt
        def yu(u): return MY - 20 - smile_lift * u ** 4 - 25 * u ** 2 + 12 * u
        hgt = (52 + rng.uniform(-8, 8)) * (1 - 0.55 * ((u0 + u1) / 2) ** 2)
        x0, x1 = FX + smile_w * u0 + 2, FX + smile_w * u1 - 2
        pts = [(x0, yu(u0) - 6), (x1, yu(u1) - 6), (x1 - 2, yu(u1) + hgt * 0.9), ((x0 + x1) / 2, yu((u0 + u1) / 2) + hgt), (x0 + 2, yu(u0) + hgt * 0.9)]
        m = poly_mask(pts, 1.2)
        g = rng.uniform(0.8, 1.0)
        teeth = np.maximum(teeth, m)
        tcol += m[..., None] * np.array((0.55 * g, 0.72 * g, 0.80 * g), np.float32)
    teeth *= mouth
    tc = tcol / np.maximum(teeth, 1e-3)[..., None] * (1 - 0.5 * np.clip((yy - (MY - 20)) / 70, 0, 1))[..., None]
    img[:] = img * (1 - teeth[..., None]) + tc * teeth[..., None]
    # smile creases up to the cheeks
    for sx in (-1, 1):
        cpts = [(FX + sx * (smile_w + 8 - 40 * s), MY - 20 - smile_lift - 25 - 250 * s) for s in np.linspace(0, 1, 20)]
        cr_ = np.zeros((H, W), np.float32); cv2.polylines(cr_, [np.array(cpts, np.int32)], False, 1.0, 10, cv2.LINE_AA)
        mix(img, gblur(cr_, 8) * 0.6, (0.03, 0.04, 0.035))
    # HAIR: long black strands eating the sides and top
    hr = np.random.default_rng(hair_seed)
    hair = np.zeros((H, W), np.float32)
    # solid dark mass on sides
    for sx in (-1, 1):
        pts = [(FX + sx * 230, -10), (FX + sx * 255, 300), (FX + sx * 300, 650), (FX + sx * 285, 1100), (FX + sx * 320, 1500), (FX + sx * 380, 1930),
               (FX + sx * 700, 1930), (FX + sx * 700, -10)]
        hair = np.maximum(hair, poly_mask(pts, 30))
    hair = np.maximum(hair, ell_mask(FX, 60, 520, 290, 0, 40))
    strands = np.zeros((H, W), np.float32)
    for _ in range(420):
        sx = hr.choice([-1, 1])
        x = FX + sx * hr.uniform(215, 330); y = hr.uniform(-50, 300)
        pts = [(x, y)]
        ang = math.pi / 2 - sx * hr.uniform(0.0, 0.08)
        for _k in range(40):
            ang += hr.normal(0, 0.015)
            x += 40 * math.cos(ang); y += 40 * math.sin(ang)
            pts.append((x, y))
        cv2.polylines(strands, [np.array(pts, np.int32)], False, hr.uniform(0.6, 1.0), int(hr.integers(2, 6)), cv2.LINE_AA)
    hair = np.clip(np.maximum(hair, gblur(strands, 1.2)), 0, 1)
    hl = gblur(hr.standard_normal((H, W)).astype(np.float32), 2) * 0.012
    hcol = np.stack([0.012 + hl, 0.014 + hl, 0.012 + hl], -1)
    img[:] = img * (1 - hair[..., None]) + hcol * hair[..., None]
    # tilt
    M = cv2.getRotationMatrix2D((FX, FY), tilt, 1.0)
    img = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    # night photo look: slight blur, green-yellow cast, crushed blacks
    img = gblur(img, 1.6)
    img = np.clip(img, 0, 1) ** 1.05
    return img

def photo_fx(img8, rng, q=22):
    # grain + jpeg
    n = rng.normal(0, 14, img8.shape[:2])[..., None] + rng.normal(0, 5, img8.shape)
    out = np.clip(img8.astype(np.float32) + n, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode('.jpg', out, [cv2.IMWRITE_JPEG_QUALITY, q])
    return cv2.imdecode(buf, 1)

if __name__ == '__main__':
    im = base_face()
    im8 = (np.clip(im, 0, 1) * 255).astype(np.uint8)
    cv2.imwrite('face_preview.png', photo_fx(im8, np.random.default_rng(1)))
