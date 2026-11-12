#!/bin/sh
# 2026-11-12 MATIN : MÂCHOIRES + LA RESCAPÉE (graine 726 ; une violette chassée des mâchoires à 20,0 s)
cd "$(dirname "$0")/../engines/morning_press"
X='{"rescue": 3.0, "rescue_v": 250.0, "rescue_nmax": 6}'
python3 audio.py 726 jaws audio.wav "$X"
python3 render.py 726 jaws audio.wav final.mp4 "$X"
python3 qc.py final.mp4 726 jaws "$X"
