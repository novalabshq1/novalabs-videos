#!/bin/sh
# Vidéo du MATIN 2026-11-13 : IRIS (4 lames) + LA DERNIÈRE COULEUR (une seule jaune au milieu des balles froides).
# Reproduit exactement videos/2026-11-13-matin-iris-lastcolor.mp4 avec engines/morning_press.
set -e
cd "$(dirname "$0")/../engines/morning_press"
# recherche (528 graines testées, 3 valides : 292 jaune seule, 507 orange seule, 410 verte de départ = survivante, écartée)
# python3 search.py iris lastcolor 0 1500 out.jsonl --extra '{"lone_max": 3}'
python3 audio.py 292 iris audio.wav '{"lone_max":3}'
python3 render.py 292 iris audio.wav final.mp4 '{"lone_max":3}'
python3 qc.py final.mp4 292 iris '{"lone_max":3}'
