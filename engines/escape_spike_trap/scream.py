# Screamer frames from face_base.png: hard cut, brutal zoom x1.55 -> x1.10 in 0.05 s, slow push, shake, red split, grain, JPEG.
import numpy as np, cv2, math
W, H, FPS, DUR = 1080, 1920, 60, 0.6
NFR = int(round(DUR * FPS))

class Screamer:
    def __init__(self, path='face_base.png', seed=3):
        self.base = cv2.imread(path).astype(np.float32)
        self.S = self.base.shape[1] / W
        self.rng = np.random.default_rng(seed)
    def frame(self, i):
        t = i / FPS; r = self.rng
        z = 1.55 - 0.45 * min(1, t / 0.05) if t < 0.05 else 1.10 + 0.07 * (t - 0.05) / (DUR - 0.05)
        dx, dy = r.uniform(-18, 18), r.uniform(-18, 18); rot = r.uniform(-2, 2)
        bh, bw = self.base.shape[:2]
        s = 1.32 * z / self.S                                    # base pixels -> output pixels (1.32: face fills the screen)
        M = cv2.getRotationMatrix2D((bw / 2, bh / 2), rot, s)
        M[0, 2] += W / 2 - bw / 2 + dx; M[1, 2] += H / 2 - bh / 2 + dy
        img = cv2.warpAffine(self.base, M, (W, H), flags=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        img *= 0.92 + 0.16 * r.random()                   # flash flicker
        img += r.normal(0, 13, (H, W, 1)).astype(np.float32) + r.normal(0, 5, (H, W, 3)).astype(np.float32)   # grain
        sh = int(r.integers(4, 15))
        img[..., 2] = np.roll(img[..., 2], sh, axis=1)    # red channel shifted 4..14 px
        img = np.clip(img, 0, 255).astype(np.uint8)
        ok, enc = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 30])
        return cv2.imdecode(enc, cv2.IMREAD_COLOR)

if __name__ == '__main__':
    sc = Screamer()
    for i in (0, 3, 18, 35):
        cv2.imwrite(f'scream_{i:02d}.png', sc.frame(i))
