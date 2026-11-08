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
Bataille dans un cercle (R=450, centre 540,1075) : chaque balle (r=32) défend ses fils ancrés au bord ; un fil adverse touché (< 32 px) casse ; mur = +10 à 15 fils.
SURSIS : 1 seul par balle ; la 1re fois à 0 fil, elle clignote et peut encore parcourir SURSIS px (distance) ; mur avant = sauvée, sinon morte ; ensuite 0 fil = morte.
Vitesse commune v(t) = 200 × e^(∫taux), taux = G + 0,012 × éliminées + RAMP × lissage((t − t2)/6). RAMP 0,30 (COULEURS) ou 0,22 (PAYS). Pas dt = min(1/120, 3/v), aligné sur les images à 60 fps.
RÉGLAGE ACTUEL (2026-11-08, PAYS) : SURSIS=300 px, G=0,01. Avec G=0,02 la médiane est ~29 s quel que soit SURSIS (300-600) ; G=0,01 donne ~12 parties valides / 1500.
Dépendances : /usr/bin/python3 (numpy, PIL), libcairo via cr.py, ffmpeg. 4 processus en parallèle.
cd engines/color_rush
1. /usr/bin/python3 search.py couleurs|pays N SURSIS G 0 1500   -> graines valides (50-60 s, 1re élim. >= 5 s, duel 10-15 s, ×15 en COULEURS), triées par score (sauvetages, fin serrée)
2. Écris spec.json : {"seed","n","ramp","sursis","g","teams":[{"rgb":[r,g,b],"flag":null|"nom"}, ...]} (index = balle de la simu ;
   la simu ne dépend pas des équipes : choisis la partie, puis attribue couleurs/pays selon winner / ordre d'élimination).
   Format PAYS : drapeaux dans flags.py (Spain, Argentina, France, England pour l'instant ; ajoute-en en suivant le même modèle, vérifie au zoom).
3. /usr/bin/python3 render.py spec.json out_noaudio.mkv      -> vidéo sans son + out_noaudio.events.json (événements, fils cassés, logs QC)
4. /usr/bin/python3 audio.py out_noaudio.events.json audio.wav C|B   (un seul son de fil par vidéo : C 7/10, B 3/10, d'après journal.md)
5. ffmpeg -i out_noaudio.mkv -i audio.wav -map 0:v -map 1:a <flags d'export du prompt> -shortest final.mp4
Exemple complet : concepts/2026-11-08-midi-pays/make.sh ; QC : concepts/2026-11-08-midi-pays/qc.py.
Publication Zernio : call_tool media_get_media_presigned_url -> curl PUT du fichier -> posts_publish_now avec publicUrl (Instagram : aucun compte connecté au 2026-11-08).
