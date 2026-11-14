#!/bin/sh
# Vidéo du MATIN 2026-11-14 : PRESSE DIAGONALE (2 blocs haut-gauche / bas-droite, axe à 45°) + LA SURVIVANTE.
# Reproduit exactement videos/2026-11-14-matin-press-diag-survivor.mp4 avec engines/morning_press.
# (python3 avec numpy : ici /usr/bin/python3.13)
set -e
cd "$(dirname "$0")/../engines/morning_press"
# recherche (~790 graines testées, 13 valides ; 207 choisie : verte de gauche jamais écrasée, plein à 47,3 s)
# python3 search.py press_diag survivor 0 1500 out.jsonl
python3 audio.py 207 press_diag audio.wav
python3 render.py 207 press_diag audio.wav final.mp4
python3 qc.py final.mp4 207 press_diag
