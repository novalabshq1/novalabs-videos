#!/bin/sh
# 2026-11-11 MATIN : PRESSE LATÉRALE + LA TRICHEUSE (graine 533, fente en haut du cercle)
cd "$(dirname "$0")/../engines/morning_press"
X='{"slit_ang": -1.4244373012951648, "slit_w": 34.0}'
python3 audio.py 533 press_side audio.wav "$X"
python3 render.py 533 press_side audio.wav final.mp4 "$X"
python3 qc.py final.mp4 533 press_side "$X"
