#!/bin/sh
# MIDI 2026-11-11 — STRING CIRCLE RUSH, format COULEURS (yellow, cyan, red, green), seed 608, snap sound C
cd "$(dirname "$0")/../engines/string_circle_rush"
python3 search.py 4 0 1500 4 > search4.jsonl        # pick: 50-60 s, longest final duel
python3 render.py 608 video_noaudio.mp4 200 0.8 18 0.15
python3 audio.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 video_noaudio.mp4) C
ffmpeg -y -i video_noaudio.mp4 -i audio.wav -c:v copy -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest final.mp4
