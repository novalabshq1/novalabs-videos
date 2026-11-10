#!/bin/sh
# MATIN 2026-11-10 : PRESSE (2 blocs haut/bas) + LA SURVIVANTE (une verte de départ jamais écrasée), son BRUITAGES.
# Graine 1153 choisie parmi 1500 (13 parties valides) : plein à 48,05 s, 54 coups, 0 coup dans le vide.
set -e
cd "$(dirname "$0")/../engines/morning_press"
python3 search.py press survivor 0 1500 /tmp/surv.jsonl
python3 audio.py 1153 press /tmp/audio.wav
python3 render.py 1153 press /tmp/audio.wav /tmp/final.mp4
python3 qc.py /tmp/final.mp4 1153 press
