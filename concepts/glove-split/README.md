# Glove Split (2026-11-08, MATIN — ÉCHELLE)
Deux gants de boxe sur un bras qui tourne à vitesse constante (ω = 1,3 rad/s) au centre d'un cercle.
Chaque balle touchée par le mécanisme se divise en 2 balles de la couleur suivante de l'échelle
(blanc → vert → jaune → orange → rouge → rose → violet → bleu → cyan, rayon ×0,85). Le cyan ne se divise plus.
À 200 balles l'anneau se fissure (0,6 s) puis éclate : toutes les balles s'envolent, 1,5 s de pause, fin.

    export OMEGA=1.3 IMM0=2.0 IMMUNE=3.4
    python3 sim.py 3 s.npz             # paliers 0.6/2.8/4.9/8.8/12.5/17.4/21.0/24.7 s, explosion 36.8 s
    python3 checklog.py s.npz          # divisions ×2 couleur suivante, 0 balle hors du cercle, 0 px dans le mécanisme
    python3 render.py s.npz v.mkv      # 1080x1920 60 fps, cairo (Poppins Bold via fontconfig)
    PEAK=-4 python3 audio.py s.npz 39.95 a.wav
    ffmpeg -i v.mkv -i a.wav -vf "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p" -c:v libx264 -profile:v high -level 4.2 \
      -pix_fmt yuv420p -preset slow -crf 14 -maxrate 25M -bufsize 50M -g 120 -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
      -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest out.mp4
    python3 qc.py out.mp4 0.2,2.9,4.95,8.8,12.6,17.4,21.1,24.7,30,34,36.6 qcdir

search.py : recherche graine/vitesse/immunité sans rendu.
