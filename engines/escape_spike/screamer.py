# Screamer frames: procedural face (face.py), hard cut, brutal zoom 1.55->1.10 in 0.05 s, slow push, shake, red shift.
import numpy as np, cv2, math, face
W, H, FPS, DUR = 1080, 1920, 60, 0.6
def frames(seed=12, **face_kw):
    rng = np.random.default_rng(seed)
    base = (np.clip(face.base_face(**face_kw), 0, 1) * 255).astype(np.uint8)
    n = int(round(DUR * FPS)); out = []
    for i in range(n):
        t = i / FPS
        z = 1.55 - 0.45 * min(1, t / 0.05) if t < 0.05 else 1.10 + 0.08 * (t - 0.05) / (DUR - 0.05)
        ang = rng.uniform(-2, 2); dx, dy = rng.uniform(-18, 18), rng.uniform(-18, 18)
        M = cv2.getRotationMatrix2D((W / 2, H / 2 - 40), ang, z); M[0, 2] += dx; M[1, 2] += dy
        im = cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        sh = int(rng.integers(4, 15))
        im[..., 2] = np.roll(im[..., 2], sh, axis=1)          # red channel offset
        im = face.photo_fx(im, rng, q=int(rng.integers(18, 30)))
        out.append(cv2.cvtColor(im, cv2.COLOR_BGR2BGRA))
    return out
if __name__ == '__main__':
    fr = frames()
    for k in (0, 3, 20, 35): cv2.imwrite(f'scream_{k:02d}.png', fr[k][..., :3])
    print(len(fr))
