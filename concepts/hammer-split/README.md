# Hammer Split (2026-11-06, MATIN)
python3 sim.py 7 s7.npz && python3 render.py s7.npz v.mkv && python3 audio.py s7.npz 49.6667 a.wav
then the section 7 ffmpeg command with -crf 7 (to get ≥ 12 Mb/s).
Needs Poppins Bold installed (fontconfig) and libcairo.
