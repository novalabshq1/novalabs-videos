# Moteurs validés par Yanis

Ces moteurs reproduisent EXACTEMENT les vidéos test validées. Ne change pas les réglages physiques/visuels.
Dépendances : python3, numpy, ffmpeg, libcairo (appelée via ctypes dans cr.py, aucun pip nécessaire), police Poppins Bold.

## string_circle (bataille de pays)
cd engines/string_circle
1. Édite render_spec.py (pays, couleurs, coins) et ajoute le dessin exact de chaque drapeau dans la fonction flag() de render.py.
2. python3 search.py 0 600  -> liste des graines valides (préférer un retournement : un pays à 1-5 fils qui gagne ou dure).
3. python3 render.py SEED video_noaudio.mp4 200 0.8 18 0.15
4. python3 audio.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 video_noaudio.mp4) C   (C ou B : un seul son de fil pour toute la vidéo, 7 vidéos sur 10 en C, 3 sur 10 en B, d'après journal.md)
5. ffmpeg -y -i video_noaudio.mp4 -i audio.wav -c:v copy -c:a aac -b:a 192k -shortest final.mp4
(Change le titre via TITLE dans render.py.)

### Screamer (seulement quand le prompt le demande, environ 1 vidéo de pays sur 5)
6. python3 screamer.py                      -> scream_v.mp4 (0,9 s)
7. python3 scream_audio.py T                -> audio_scream.wav (T = seconde du screamer, ex. 31.0)
8. ffmpeg -y -i video_noaudio.mp4 -i scream_v.mp4 -i audio_scream.wav -filter_complex "[1:v]setpts=PTS-STARTPTS+T/TB[s];[0:v][s]overlay=0:0:enable='between(t,T,T+0.9)':eof_action=pass[v]" -map "[v]" -map 2:a -c:v libx264 -preset veryfast -crf 17 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest final.mp4
   (remplace T par la même valeur partout ; cette commande remplace l'étape 5)

## spike_escape (anneau fixe à pics, balles mortes = obstacles gris)
cd engines/spike_escape
1. python3 search.py 0 600  -> graines valides (faux espoirs au début inclus).
2. python3 render_esc.py SEED esc_noaudio.mp4   (couleurs de l'anneau : C1/CM/C2 ; titre : TITLE)
3. python3 audio_esc.py $(ffprobe -v error -show_entries format=duration -of csv=p=0 esc_noaudio.mp4)
4. ffmpeg -y -i esc_noaudio.mp4 -i esc_audio.wav -c:v copy -c:a aac -b:a 192k -shortest final.mp4

## morning_press (vidéo du MATIN : un mécanisme écrase des balles qui se multiplient jusqu'à remplir le cercle)
Règles fixes : cercle R 450 centré (540, 1075), fond noir, 2 balles vertes r 26 au départ, 320 px/s, pas de gravité,
collisions élastiques, pas 1/240 s, mécanisme qui ne se ferme que s'il y a au moins une balle dans sa zone
(fermeture 0,16 s / maintien 0,06 s / réouverture 0,3 s / pause 0,3 s), chaque balle écrasée -> 2 balles de la couleur
suivante (vert -> jaune -> orange -> rouge -> rose -> violet -> bleu -> cyan, rayon x0,88, min 15), fin quand la surface
des balles >= 50 % du cercle (la presse reste fermée) + 2,5 s.
Fichiers : sim.c (coeur physique C, compilé automatiquement), sim.py (wrapper, MECHS = mécanismes disponibles),
search.py (recherche parallèle), render.py (rendu + export TikTok), audio.py (bruitages / mélodie), qc.py (contrôle), diag.py.
cd engines/morning_press
1. python3 search.py MECH TWIST 0 1500 out.jsonl     MECH : press | press_side ; TWIST : survivor | tricheuse | lastcolor | any
   (lignes "OK" = parties valides : plein entre 42 et 57 s, aucun coup dans le vide, chevauchement <= 2,5 px, élément arrivé)
2. python3 audio.py SEED MECH audio.wav ['{"slit_ang":..,"slit_w":34}'] [--melody "E5,D5,C5,..."]
3. python3 render.py SEED MECH audio.wav final.mp4 ['{extra}']        (images clés : --frames 0,60,... --png-dir DIR)
4. python3 qc.py final.mp4 SEED MECH ['{extra}']                      -> doit afficher "QC OK"
Ajouter un mécanisme : géométrie/contraintes dans sim.c (mech_constrain, in_zone, point_ok, crush), entrée dans MECHS
(sim.py) et dessin dans render.py. Ne jamais repartir de zéro.
Mécanismes faits : press (2026-11-10). press_side = même code, axe horizontal (prêt, non encore publié).
