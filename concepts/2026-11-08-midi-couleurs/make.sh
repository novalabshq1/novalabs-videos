#!/bin/bash
# MIDI — COULEURS 2026-11-08 : graine 240, 5 balles, FLAT=30 G=0.04 RAMP=0.45
# Balles : 0 jaune, 1 vert, 2 rouge (finaliste battu), 3 violet, 4 cyan (gagnant)
set -e
D=$(cd "$(dirname "$0")" && pwd)
cd "$D/../../engines/color_rush"
python3 search.py couleurs 5 30 0.04 0 1500
python3 render.py "$D/spec.json" "$D/out_noaudio.mkv"
python3 audio.py "$D/out_noaudio.events.json" "$D/audio.wav"
ffmpeg -y -i "$D/out_noaudio.mkv" -i "$D/audio.wav" -map 0:v -map 1:a -c:v libx264 -profile:v high -level 4.2 -pix_fmt yuv420p -preset slow -crf 14 -maxrate 25M -bufsize 50M -g 120 -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest "$D/final.mp4"
