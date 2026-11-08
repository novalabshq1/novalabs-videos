#!/bin/sh
# MIDI — COULEURS 2026-11-08 (String Circle RUSH, seed 986, snap sound C)
set -e
cd "$(dirname "$0")/../../engines/string_circle_rush"
cp ../../concepts/2026-11-08-midi-couleurs-rush/render_spec.py render_spec.py
python3 search.py 0 1500 4          # 4 balls: 419 candidates, only 4 at 50-60 s; seed 986 = longest duel (15.3 s)
python3 qc.py 986                   # -> ALL OK
python3 render.py 986 video_noaudio.mp4 200 0.8 18 0.15
python3 audio.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 video_noaudio.mp4) C
ffmpeg -y -i video_noaudio.mp4 -i audio.wav -c:v libx264 -profile:v high -level 4.2 -pix_fmt yuv420p -preset slow -crf 14 \
  -maxrate 25M -bufsize 50M -g 120 -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
  -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest ../../videos/2026-11-08-midi-couleurs-rush.mp4
