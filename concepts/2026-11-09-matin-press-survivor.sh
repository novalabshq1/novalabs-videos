#!/bin/bash
# MATIN 2026-11-09 : PRESSE (haut/bas) + LA SURVIVANTE (seed 0). Reproduit exactement videos/2026-11-09-matin-press-survivor.mp4
set -e
cd "$(dirname "$0")/../engines/morning_press"
# search used: ELEMENT=last python3.13 search.py 0 16 90 265   (seed 0: green ball born at t=0 never crushed, full at 44.68 s)
python3.13 render.py 0 out_0.mkv 90 265 30.03 survivor
python3.13 audio.py events_0.json audio_0.wav sfx
ffmpeg -y -i out_0.mkv -i audio_0.wav -c:v libx264 -profile:v high -level 4.2 -pix_fmt yuv420p -preset slow -crf 14 -maxrate 25M -bufsize 50M -g 120 -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 320k -ar 48000 -movflags +faststart final_0.mp4
python3.13 qc.py 0 final_0.mp4
