# Edit this per video: (name, string colour rgb 0-1, corner angle in degrees, y axis down)
# 4 balls -> corners 225, 315, 45, 135. COULEURS format: name "solid" = plain colour ball.
def C(r, g, b): return (r / 255, g / 255, b / 255)
SPEC = [("solid", C(255, 215, 0), 225),    # yellow
        ("solid", C(0, 215, 255), 315),    # cyan
        ("solid", C(255, 45, 60), 45),     # red
        ("solid", C(60, 230, 90), 135)]    # green
LABELS = ["yellow", "cyan", "red", "green"]
