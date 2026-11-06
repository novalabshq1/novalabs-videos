# ESCAPE - WIDER GAP (2026-11-06) : "EVERY DEATH WIDENS THE GAP"
# Fixed spiked ring, opening always centred at the bottom (90 deg), ring never rotates.
# Rule: each ball that dies on a spike turns grey (#3A3A3A) and stays as an obstacle, and the opening widens by 2 deg
# (14 deg -> 40 deg in this video). Grey balls sitting on spikes swallowed by the wider opening pop away.
# Reproduce (engine: engines/escape_wider_gap):
#   python3 search.py 0 600 14 2 4.5            -> valid seeds (seed 177 chosen: 14 tries, 43.35 s, last ball alive 6.5 s)
#   CRF=14 X264=filler=1 python3 render.py 177 final.mp4 14 2 [keyframes]   -> sim + audio + final TikTok-quality encode
#   python3 qc_frames.py ; python3 qc_logs.py   -> framing QC on key frames, physics QC on the sim log
SEED = 177; GAP0_DEG = 14; STEP_DEG = 2
TITLE = "EVERY DEATH WIDENS THE GAP"
RING = ["#1AE6F2 cyan", "#4D6BFF blue", "#FA4DCC magenta"]
