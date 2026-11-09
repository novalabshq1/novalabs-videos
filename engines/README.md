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

## morning_press (vidéo du MATIN : un mécanisme écrase des balles qui se multiplient jusqu'au cercle plein)
Dépendances en plus : python3.13 (numpy), gcc (core.c est compilé automatiquement en core.so par sim.py).
cd engines/morning_press
- core.c : physique (balle-balle élastique sans chevauchement, cercle avec fente optionnelle, polygones convexes mobiles, segments « cage »), pas 1/240 s, vitesse constante 320 px/s.
- mechanisms.py : les MÉCANISMES (interface commune : polys, in_zone, cage, squash, spawn_candidates, eject_dir). Chaque nouveau mécanisme est AJOUTÉ ici (+ son dessin dans render.py) puis réutilisé.
  - press : PRESSE haut/bas (HW = demi-largeur des blocs, D = distance de la face au centre quand c'est ouvert). Réglage utilisé le 2026-11-09 : HW=90, D=265 (blocs fermés moins encombrants -> aucun chevauchement à la fin).
- sim.py : simulation SANS rendu. Le mécanisme ne se ferme que si au moins une balle a son centre dans la zone ; la cage retient les balles prises ; elles sont écrasées à la fermeture -> 2 balles de la couleur suivante éjectées de chaque côté (elles « poussent » en 0,1 s pour ne jamais tomber dans une autre balle). Fin : surface des balles >= 50 % du cercle, puis 2,5 s.
- search.py : ELEMENT=cheater MAXESC=1 python3.13 search.py START END HW D SLIT_W  (4 processus) -> graines valides (plein entre 42 et 57 s, aucun coup dans le vide, élément OK). ELEMENT=none pour sans fente.
  - LA TRICHEUSE : fente de SLIT_W px (30.03 = juste plus large que les balles de 15 px) à un endroit au hasard (côté gauche en général). Attention : sous la pression de la foule, la fente « aspire » les balles, il faut donc beaucoup de graines pour en trouver une avec UNE seule sortie.
- render.py SEED out.mkv HW D SLIT_W ELEMENT -> vidéo sans perte 1080x1920 60 fps + events_SEED.json (logs QC/audio).
- audio.py events_SEED.json audio.wav sfx|melody -> bruitages (boom par coup, pop pentatonique par balle écrasée, tic de rebond ≤ 1/60 ms, « fiou » pour la tricheuse). Mode melody : remplir MELODY_NOTES (MIDI).
- qc.py SEED video.mp4 -> contrôles (cadrage, coups, divisions, traversées, chevauchements, durée).
- Export final : ffmpeg -i out.mkv -i audio.wav (+ les options exactes du prompt) final.mp4
- Éléments testés : LA TRICHEUSE avec ce moteur est très difficile (sous la pression de la foule, la fente laisse sortir des balles en rafale : ~1 graine valide sur 300 et elle échouait au contrôle de chevauchement). ELEMENT=last (search.py) trouve LA SURVIVANTE / LA DERNIÈRE COULEUR : la couleur la plus basse encore présente n'a qu'une seule balle (champ "last" : lv 0 = une verte de départ jamais écrasée).
- Réglages de la vidéo du 2026-11-09 : HW=90, D=265 (search.py par défaut), ITERS 6 / 14 quand il y a >= 200 balles.
