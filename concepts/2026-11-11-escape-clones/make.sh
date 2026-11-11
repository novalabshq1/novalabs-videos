# ESCAPE — CLONES (2026-11-11) : reproduit exactement videos/2026-11-11-escape-clones.mp4
# Règle : chaque balle morte fait apparaître 2 nouvelles balles au point de départ (une toutes les 1,2 s au plus) ; il faut qu'UNE seule sorte.
cd "$(dirname "$0")/../../engines/escape_clones"
python3 search.py 0 600 14 1.2                       # graines valides -> 222 retenue (montée 1 -> 6 balles en jeu)
python3 face.py 3 -9 1.15 -6 face_tonight.png        # visage du soir : graine 3, inclinaison -9°, sourire 1,15, regard à gauche
python3 render_clones.py 222 x.mp4 none 18.65 none 14 1.2 --events-only
python3 audio_esc.py 30.3 18.65 -1.5                 # cri calibré : -1 dBFS après AAC (bash calib.sh 30.3 18.65 -1.5)
python3 render_clones.py 222 final.mp4 esc_audio.wav 18.65 face_tonight.png 14 1.2
