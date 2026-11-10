#!/bin/sh
# MIDI 2026-11-10 — STRING CIRCLE RUSH, format COULEURS (4 couleurs), seed 986
# Couleurs : cyan (gagnant), rose (finaliste), jaune (2e éliminé), bleu (1er éliminé). Son de fil : C.
set -e
cd "$(dirname "$0")/../engines/string_circle_rush"
python3 search.py 0 1500 4 > /tmp/res.jsonl          # recherche headless
python3 render.py 986 v_noaudio.mkv 200 0.8 18 0.15  # rendu 1080x1920 60 fps (sans perte)
python3 audio.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 v_noaudio.mkv) C
ffmpeg -y -i v_noaudio.mkv -i audio.wav -map 0:v -map 1:a -vf "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p" \
  -c:v libx264 -profile:v high -level 4.2 -pix_fmt yuv420p -preset slow -crf 14 -maxrate 25M -bufsize 50M -g 120 \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest final.mp4
