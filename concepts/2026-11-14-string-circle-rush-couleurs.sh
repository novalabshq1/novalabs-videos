#!/bin/sh
# MIDI 2026-11-14 — String Circle Rush, format COULEURS (N = -1, odd), 5 colours.
# Engine: engines/string_circle_rush (validated string_circle + 4 rush changes). render_spec.py: orange/violet/rouge/vert/bleu at 270/342/54/126/198 deg.
# Seed search: 1500 seeds at 4 balls (50-60 s: 961 17.6 s duel used 3x already, 206 14.1 s used 11-13) and 1500 at 5 balls
# (50-60 s: 1307 13.8 s duel, 734 8.5 s, 566 8.0 s). Chose 1307: new game, longest fresh duel >= 12 s.
set -e
cd "$(dirname "$0")/../engines/string_circle_rush"
python3 render.py 1307 v_noaudio.mp4 200 0.8 18 0.15
python3 audio.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 v_noaudio.mp4) C
ffmpeg -y -i v_noaudio.mp4 -i audio.wav -map 0:v -map 1:a -c:v libx264 -profile:v high -level 4.2 -pix_fmt yuv420p -preset slow -crf 14 \
  -maxrate 25M -bufsize 50M -g 120 -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 320k -ar 48000 \
  -movflags +faststart -shortest ../../videos/2026-11-14-1200-string-circle-rush-couleurs.mp4
