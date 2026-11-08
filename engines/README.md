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

## color_rush (vidéo de MIDI : formats COULEURS et PAYS, aucun texte)
Bataille dans un cercle (R=450, centre 540,1075) : chaque balle (r=32) défend ses fils ancrés au bord ; un fil adverse touché (< 32 px) casse ; mur = +10 à 15 fils ; 0 fil = morte. Vitesse commune v(t) = 150 × e^(∫taux), taux = 0 avant FLAT, puis G + 0,012 × éliminées + RAMP × lissage((t − t2)/6). RAMP 0,45 (COULEURS) ou 0,22 (PAYS). Pas dt = min(1/120, 3/v), aligné sur les images à 60 fps.
Dépendances : /usr/bin/python3 (numpy), libcairo via cr.py, ffmpeg. 4 processus en parallèle.
cd engines/color_rush
1. python3 search.py couleurs|pays N FLAT G 0 1500   -> graines valides (critères du prompt, triées par score)
   Avec FLAT=10/20 aucune partie ne dure 45 s (médiane ~28-32 s) : FLAT=30, G=0,04 donne des parties de 45-50 s (2026-11-08).
2. Écris spec.json : {"seed","n","ramp","flat","g","teams":[{"rgb":[r,g,b],"flag":null}, ...]} (index = balle de la simu ;
   la simu ne dépend pas des équipes : choisis la partie, puis attribue couleurs/pays selon winner / dernier éliminé).
   Format PAYS : mets "flag":"nom" et ajoute un module flags.py avec draw(ctx, nom, x, y, r) qui dessine le drapeau dans le disque (à créer au 1er usage).
3. python3 render.py spec.json out_noaudio.mkv      -> vidéo sans son + out_noaudio.events.json (événements + logs QC)
4. python3 audio.py out_noaudio.events.json audio.wav
5. ffmpeg -i out_noaudio.mkv -i audio.wav -map 0:v -map 1:a <flags d'export du prompt> -shortest final.mp4
QC : concepts/2026-11-08-midi-couleurs/qc.py (cadrage sur 14 images clés, zone du haut noire, logs physiques).
Publication Zernio : call_tool media_get_media_presigned_url -> curl PUT du fichier -> posts_publish_now avec publicUrl.
