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

## string_circle_rush (vidéo de MIDI, depuis le 2026-11-08)
Copie exacte de string_circle avec 4 changements seulement : aucun texte, +10 fils par contact au bord (~1° d'écart),
vitesse progressive v = 200 × e^∫(0,008 + 0,25·lissage((t−t2)/6)) (t2 = 2 balles restantes), dt = min(1/120, 3/v) avec traînée fine,
balles de couleur pleine (SOLID dans render.py) pour le format COULEURS.
cd engines/string_circle_rush
1. render_spec.py (4 balles : 225/315/45/135 ; 5 balles : 270/342/54/126/198)
2. python3 search.py 0 1500 4   -> JSON par graine (tot, duel, deaths, lead_changes, comeback)
3. python3 qc.py SEED           -> contrôles physiques (ALL OK obligatoire)
4. python3 render.py SEED video_noaudio.mp4 200 0.8 18 0.15
5. python3 audio.py DUREE C|B ; puis export ffmpeg TikTok (voir concepts/2026-11-08-midi-couleurs-rush/make.sh)
Publication Zernio : call_tool media_get_media_presigned_url (filename, content_type, size) -> curl PUT -> posts_publish_now avec publicUrl.
