#!/bin/sh
# MIDI — COULEURS 2026-11-08 : String Circle RUSH, 4 couleurs, graine 748, violet bat orange.
# Spec : engines/string_circle_rush/render_spec.py (orange 225°, vert 315°, violet 45°, cyan 135°)
set -e
cd "$(dirname "$0")/../engines/string_circle_rush"
python3 search.py 0 1500 4 | grep VALID          # -> 748 (51,2 s, duel 14,7 s, x40,6)
python3 qc_logs.py 748
python3 render.py 748 video_noaudio.mp4 200 0.8 18 0.15
python3 audio.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 video_noaudio.mp4) C
ffmpeg -y -i video_noaudio.mp4 -i audio.wav -map 0:v -map 1:a -c:v libx264 -profile:v high -level 4.2 -pix_fmt yuv420p \
  -preset slow -crf 14 -maxrate 25M -bufsize 50M -g 120 -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
  -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest ../../videos/2026-11-08-midi-couleurs-rush.mp4
