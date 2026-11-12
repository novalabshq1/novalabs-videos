# Edit this per video: (name, string colour rgb 0-1, corner angle in degrees, y axis down)
# COULEURS format: name = "#RRGGBB" draws a solid colour ball.
# 4 balls -> corners 225, 315, 45, 135. The physics does not depend on names/colours.
def rgb(r, g, b): return (r / 255, g / 255, b / 255)
SPEC = [("#FFD700", rgb(255, 215, 0), 225),    # yellow  (out 2nd)
        ("#00D7FF", rgb(0, 215, 255), 315),    # cyan    (winner)
        ("#FF50B4", rgb(255, 80, 180), 45),    # pink    (finalist)
        ("#3CE65A", rgb(60, 230, 90), 135)]    # green   (out 1st)
