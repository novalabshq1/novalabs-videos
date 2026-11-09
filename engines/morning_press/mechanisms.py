"""Mechanisms for morning_press. Each mechanism exposes the same interface:
  polys(u, du)      -> list of convex polygons [(verts Nx2, vx, vy, w, px, py)] at closure u in [0,1] (0 open, 1 closed), du = du/dt
  in_zone(x, y)     -> bool mask: ball centres inside the catch zone (evaluated when open, u=0)
  cage()            -> list of segments (x1,y1,x2,y2) that close the zone while the mechanism closes
  squash(x, y, vy, r, u) -> clamps caught balls inside the closing gap, returns (y, vy, ry) (ry = drawn half-height)
  spawn_candidates(x0, y0, rc, side) -> list of (x, y) candidate positions to eject a child on side -1 / +1
  eject_dir(side, rng) -> unit vector of a child's initial velocity
  draw(c, u) (in render.py, keyed by NAME)
New mechanisms are ADDED here and reused later (never start from scratch)."""
import numpy as np, math

CX, CY, R = 540.0, 1075.0, 450.0


class Press:
    """PRESSE: 2 big blocks (top and bottom) that slam together on the horizontal centre line."""
    NAME = 'press'

    def __init__(self, HW=95.0, D=150.0):
        self.HW, self.D = HW, D          # block half-width, open face distance from centre

    def face(self, u):
        return self.D * (1.0 - u)

    def polys(self, u, du):
        f = self.face(u); HW = self.HW; v = self.D * du   # face speed (towards centre when du>0)
        top = np.array([[CX - HW, CY - R - 60], [CX + HW, CY - R - 60], [CX + HW, CY - f], [CX - HW, CY - f]])
        bot = np.array([[CX - HW, CY + f], [CX + HW, CY + f], [CX + HW, CY + R + 60], [CX - HW, CY + R + 60]])
        return [(top, 0.0, v, 0.0, CX, CY), (bot, 0.0, -v, 0.0, CX, CY)]

    def in_zone(self, x, y):
        return (np.abs(x - CX) < self.HW) & (np.abs(y - CY) < self.D + 2)

    def cage(self):
        HW, D = self.HW, self.D + 4
        return [(CX - HW, CY - D, CX - HW, CY + D), (CX + HW, CY - D, CX + HW, CY + D)]

    def squash(self, x, y, vy, r, u):
        f = self.face(u)
        ry = np.minimum(r, f)
        lo, hi = CY - f + ry, CY + f - ry
        vy = np.where((y < lo) & (vy < 0), -vy, vy); vy = np.where((y > hi) & (vy > 0), -vy, vy)
        y = np.clip(y, lo, hi)
        x = np.clip(x, CX - self.HW + r, CX + self.HW - r)
        return x, y, vy, ry

    def spawn_candidates(self, x0, y0, rc, side):
        """Positions beside the press on `side`, ordered by distance from the preferred spot (next to the block, at y0)."""
        bx = CX + side * (self.HW + rc + 1.5)
        gx = bx + side * np.arange(0, R, 4.0)
        gy = CY + np.arange(-R, R + 1, 4.0)
        X, Y = np.meshgrid(gx, gy); X = X.ravel(); Y = Y.ravel()
        d = np.hypot(X - bx, (Y - y0) * 0.8)
        o = np.argsort(d, kind='stable')
        return list(zip(X[o], Y[o]))

    def eject_dir(self, side, rng):
        a = rng.uniform(-0.9, 0.9)
        return np.array([side * math.cos(a), math.sin(a)])


MECHS = {'press': Press}
