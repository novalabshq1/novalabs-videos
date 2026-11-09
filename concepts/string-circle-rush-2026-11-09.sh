#!/bin/sh
# MIDI 2026-11-09 — COULEURS — String Circle Rush, seed 961 (cyan wins vs pink, snap sound C)
cd engines/string_circle_rush
python3 search.py 0 1500 4 > res.txt          # headless search
python3 render.py 961 video_noaudio.mp4 200 0.8 18 0.15
python3 audio.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 video_noaudio.mp4) C
ffmpeg -y -i video_noaudio.mp4 -i audio.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest final.mp4
python3 qc.py 961
