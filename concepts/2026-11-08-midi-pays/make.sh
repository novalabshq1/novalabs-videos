#!/bin/bash
# MIDI — PAYS 2026-11-08 : Coupe du monde 2026 (Espagne, Argentine, France, Angleterre)
# graine 1000, 4 balles, SURSIS=300 px, G=0.01, RAMP=0.22, son de fil B
# Balles : 0 Argentine (finaliste battu), 1 Angleterre, 2 France, 3 Espagne (gagnant)
set -e
D=$(cd "$(dirname "$0")" && pwd)
cd "$D/../../engines/color_rush"
/usr/bin/python3 search.py pays 4 300 0.01 0 1500
/usr/bin/python3 render.py "$D/spec.json" "$D/out_noaudio.mkv"
/usr/bin/python3 audio.py "$D/out_noaudio.events.json" "$D/audio.wav" B
ffmpeg -y -i "$D/out_noaudio.mkv" -i "$D/audio.wav" -map 0:v -map 1:a -c:v libx264 -profile:v high -level 4.2 -pix_fmt yuv420p -preset slow -crf 14 -maxrate 25M -bufsize 50M -g 120 -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest "$D/final.mp4"
cd "$D" && /usr/bin/python3 qc.py
