# Réglages ESCAPE (soir) : ouverture PILE EN BAS (90°), anneau fixe, lancer identique
import esc_sim as E, math
def apply(gap_deg=20.0):
    E.RO = 490.0; E.RING_T = 16.0; E.RI = E.RO - E.RING_T; E.BR = 26.0
    E.MAX_TRIES = 45; E.ROT = 0; E.NSPK = 88; E.SPK_HALF = math.pi / 88; E.SPK_H = 62; E.LEAN = 1.0
    E.G = 400; E.V0 = 360; E.GAP = math.radians(gap_deg); E.GAP_AT = math.radians(90); E.SPIKES = E.spike_angles()
    E.TRY_TIMEOUT = 12.0
    return E
