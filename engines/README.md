# Moteurs validés par Yanis

Ces moteurs reproduisent EXACTEMENT les vidéos test validées. Ne change pas les réglages physiques/visuels.
Dépendances : python3, numpy, ffmpeg, libcairo (appelée via ctypes dans cr.py, aucun pip nécessaire), police Poppins Bold.

## string_circle (bataille de pays)
cd engines/string_circle
1. Édite render_spec.py (pays, couleurs, coins) et ajoute le dessin exact de chaque drapeau dans la fonction flag() de render.py.
2. python3 search.py 0 600  -> liste des graines valides (préférer un retournement : un pays à 1-5 fils qui gagne ou dure).
3. python3 render.py SEED video_noaudio.mp4 200 0.8 18 0.15
4. python3 audio.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 video_noaudio.mp4)
5. ffmpeg -y -i video_noaudio.mp4 -i audio.wav -c:v copy -c:a aac -b:a 192k -shortest final.mp4
(Change le titre via TITLE dans render.py.)

## spike_escape (anneau fixe à pics, balles mortes = obstacles gris)
cd engines/spike_escape
1. python3 search.py 0 600  -> graines valides (faux espoirs au début inclus).
2. python3 render_esc.py SEED esc_noaudio.mp4   (couleurs de l'anneau : C1/CM/C2 ; titre : TITLE)
3. python3 audio_esc.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 esc_noaudio.mp4)
4. ffmpeg -y -i esc_noaudio.mp4 -i esc_audio.wav -c:v copy -c:a aac -b:a 192k -shortest final.mp4
