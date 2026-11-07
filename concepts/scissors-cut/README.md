# Scissors Cut (2026-11-07, MATIN)
Ciseaux au centre d'un cercle ; chaque balle prise entre les lames qui se ferment est coupée en 4. À 400 balles l'anneau se fissure puis explose.

    PHIMAX=34 python3 sim.py 1 s.npz
    PHIMAX=34 python3 pen.py s.npz          # contrôle : aucune balle ne traverse les ciseaux
    PHIMAX=34 python3 render.py s.npz v.mkv
    python3 audio.py s.npz 41.55 a.wav
    ffmpeg -i v.mkv -i a.wav -c:v libx264 -profile:v high -level 4.2 -pix_fmt yuv420p -preset slow \
      -b:v 14M -minrate 14M -maxrate 14M -bufsize 28M -x264-params nal-hrd=cbr:filler=1 -g 120 \
      -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest out.mp4
    python3 qc.py out.mp4 0.02,2,12,24,34,38.5 qcdir

search.py : recherche de graines. Besoin de Poppins Bold (fontconfig) et de libcairo.
