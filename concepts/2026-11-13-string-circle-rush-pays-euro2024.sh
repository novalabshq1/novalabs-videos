#!/bin/sh
# MIDI 2026-11-13 — String Circle Rush, format PAYS (Euro 2024 final four)
# Engine: engines/string_circle_rush (validated string_circle + 4 rush changes). Flags Spain/England/Netherlands added to flag().
# Seed search: python3 search.py 0 1500 4  -> 6 games in 50-60 s; longest duels 961 (17.6 s, used 11-09 and 11-12) and 206 (14.1 s, chosen).
set -e
cd "$(dirname "$0")/../engines/string_circle_rush"
python3 render.py 206 v_noaudio.mp4 200 0.8 18 0.15
python3 audio.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 v_noaudio.mp4) B
ffmpeg -y -i v_noaudio.mp4 -i audio.wav -map 0:v -map 1:a -c:v libx264 -profile:v high -level 4.2 -pix_fmt yuv420p -preset slow -crf 14 \
  -maxrate 25M -bufsize 50M -g 120 -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 320k -ar 48000 \
  -movflags +faststart -shortest ../../videos/2026-11-13-1200-string-circle-rush-pays-euro2024.mp4
