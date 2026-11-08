"""Drapeaux dessinés dans le disque d'une balle (format PAYS) : draw(ctx, nom, x, y, r).

Le drapeau (rapport réel) est centré sur la balle, sa hauteur = diamètre du disque, et découpé par le disque.
Noms : Spain, Argentina, France, England.
"""
import math
import cr


def hexrgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rect(ctx, x, y, w, h, col):
    cr.rectangle(ctx, x, y, w, h)
    cr.set_rgb(ctx, *hexrgb(col))
    cr.fill(ctx)


def _spain(ctx, x, y, r):
    W = 3 * r                                   # drapeau 3:2, hauteur 2r
    _rect(ctx, x - W / 2, y - r, W, 2 * r, '#AA151B')
    _rect(ctx, x - W / 2, y - r / 2, W, r, '#F1BF00')
    # armoiries simplifiées, axe à h/2 de la hampe -> x - 0.5 r, hauteur ~ 2/5 du drapeau
    ax, ay = x - 0.5 * r, y + 0.02 * r
    for dx in (-0.30, 0.30):                    # colonnes d'Hercule
        _rect(ctx, ax + dx * r - 0.045 * r, ay - 0.26 * r, 0.09 * r, 0.56 * r, '#E8E8E8')
        _rect(ctx, ax + dx * r - 0.07 * r, ay - 0.30 * r, 0.14 * r, 0.05 * r, '#C8B100')
        _rect(ctx, ax + dx * r - 0.07 * r, ay + 0.28 * r, 0.14 * r, 0.05 * r, '#C8B100')
    sw, sh = 0.38 * r, 0.46 * r                 # écu écartelé
    sx, sy = ax - sw / 2, ay - 0.22 * r
    cr.save(ctx)
    cr.new_path(ctx)
    cr.move_to(ctx, sx, sy)
    cr.line_to(ctx, sx + sw, sy)
    cr.line_to(ctx, sx + sw, sy + sh * 0.6)
    cr.arc(ctx, ax, sy + sh * 0.6, sw / 2, 0, math.pi)
    cr.close_path(ctx)
    cr.clip(ctx)
    _rect(ctx, sx, sy, sw / 2, sh / 2, '#C8102E')               # Castille
    _rect(ctx, ax, sy, sw / 2, sh / 2, '#F4F4F4')               # León
    _rect(ctx, sx, sy + sh / 2, sw / 2, sh, '#F1BF00')          # Aragon
    for k in range(2):
        _rect(ctx, sx + (0.08 + 0.22 * k) * sw / 2 * 2, sy + sh / 2, sw * 0.07, sh, '#C8102E')
    _rect(ctx, ax, sy + sh / 2, sw / 2, sh, '#C8102E')          # Navarre
    cr.restore(ctx)
    _rect(ctx, ax - 0.03 * r, sy + 0.04 * r, 0.06 * r, 0.12 * r, '#F1BF00')   # château (Castille)
    _rect(ctx, ax + 0.06 * r, sy + 0.05 * r, 0.08 * r, 0.10 * r, '#7B2A8C')   # lion (León)
    cr.new_path(ctx)                            # couronne
    cx0, cy0 = ax, sy - 0.03 * r
    cr.move_to(ctx, cx0 - 0.17 * r, cy0)
    cr.line_to(ctx, cx0 - 0.19 * r, cy0 - 0.12 * r)
    cr.line_to(ctx, cx0 - 0.08 * r, cy0 - 0.06 * r)
    cr.line_to(ctx, cx0, cy0 - 0.17 * r)
    cr.line_to(ctx, cx0 + 0.08 * r, cy0 - 0.06 * r)
    cr.line_to(ctx, cx0 + 0.19 * r, cy0 - 0.12 * r)
    cr.line_to(ctx, cx0 + 0.17 * r, cy0)
    cr.close_path(ctx)
    cr.set_rgb(ctx, *hexrgb('#C8B100'))
    cr.fill(ctx)


def _argentina(ctx, x, y, r):
    W = 3.2 * r                                 # 1:1.6
    _rect(ctx, x - W / 2, y - r, W, 2 * r, '#74ACDF')
    _rect(ctx, x - W / 2, y - r / 3, W, 2 * r / 3, '#FFFFFF')
    # Soleil de Mai : 32 rayons (droits et ondulés alternés, ici triangles longs/courts)
    gold, brown = hexrgb('#F6B40E'), hexrgb('#85340A')
    ro, rs, ri = 0.31 * r, 0.25 * r, 0.13 * r
    cr.new_path(ctx)
    for k in range(32):
        a = -math.pi / 2 + k * 2 * math.pi / 32
        rr = ro if k % 2 == 0 else rs
        w = math.pi / 32 * 0.9
        cr.move_to(ctx, x + ri * math.cos(a - w), y + ri * math.sin(a - w))
        cr.line_to(ctx, x + rr * math.cos(a), y + rr * math.sin(a))
        cr.line_to(ctx, x + ri * math.cos(a + w), y + ri * math.sin(a + w))
        cr.close_path(ctx)
    cr.set_rgb(ctx, *gold)
    cr.fill(ctx)
    cr.new_path(ctx)
    cr.arc(ctx, x, y, ri, 0, 2 * math.pi)
    cr.set_rgb(ctx, *gold)
    cr.fill(ctx)
    cr.new_path(ctx)
    cr.arc(ctx, x, y, ri, 0, 2 * math.pi)
    cr.set_line_width(ctx, 0.025 * r)
    cr.set_rgb(ctx, *brown)
    cr.stroke(ctx)


def _france(ctx, x, y, r):
    W = 3 * r
    for i, col in enumerate(['#002395', '#FFFFFF', '#ED2939']):
        _rect(ctx, x - W / 2 + i * W / 3, y - r, W / 3 + 0.5, 2 * r, col)


def _england(ctx, x, y, r):
    W = 3.2 * r                                 # 3:5, croix = 1/5 de la hauteur
    _rect(ctx, x - W / 2, y - r, W, 2 * r, '#FFFFFF')
    cw = 2 * r / 5
    _rect(ctx, x - W / 2, y - cw / 2, W, cw, '#CE1124')
    _rect(ctx, x - cw / 2, y - r, cw, 2 * r, '#CE1124')


DRAW = dict(Spain=_spain, Argentina=_argentina, France=_france, England=_england)


def draw(ctx, name, x, y, r):
    cr.save(ctx)
    cr.new_path(ctx)
    cr.arc(ctx, x, y, r, 0, 2 * math.pi)
    cr.clip(ctx)
    DRAW[name](ctx, x, y, r)
    cr.restore(ctx)
    cr.new_path(ctx)
