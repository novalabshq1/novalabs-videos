# escape_spike — ESCAPE du soir, règle SPIKE ESCAPE (classique) + screamer
Copie de spike_escape avec : ouverture PILE EN BAS (90°), lancer fixe (CX, CY-60) à -80° ±8°, 360 px/s ; screamer procédural (face.py).
1. python3 search.py 0 600 GAP_DEG 8        -> graines valides (30-45 s, ≥9 essais, faux espoirs)
2. python3 render_esc.py SEED esc_noaudio.mkv GAP_DEG SCREAM_T   (ffv1 sans perte, screamer 0,6 s intégré)
3. python3 audio_esc.py DUREE SCREAM_T      (jeu à -8 dBFS, cri à -1 dBFS, reste à 5 % pendant le cri)
4. ffmpeg -i esc_noaudio.mkv -i esc_audio.wav -c:v libx264 -profile:v high -level 4.2 -pix_fmt yuv420p -preset slow -crf 14 -maxrate 25M -bufsize 50M -g 120 -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest final.mp4
Largeur mesurée de l'anneau à l'écran : 1000 px (x 40→1039), centre (540, 1075).
