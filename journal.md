# Journal des vidéos du soir ESCAPE

| Date | Vidéo | Ouverture | Essais | Couleurs | Durée | Débit vidéo | Liens |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | ESCAPE — WIDER GAP (« EVERY DEATH WIDENS THE GAP », graine 177) | 14° → 40° (+2° par mort) | 14 (13 morts, la 14e sort après 6,5 s) | anneau cyan → bleu → magenta ; balles teintes vives différentes à chaque essai | 43,35 s | 24,9 Mb/s (publié, filler x264) ; copie du repo 0,6 Mb/s mêmes images | TikTok : post Zernio 6aee5fb32c168f22f85a56a5 (publié) · YouTube : post Zernio 6aee5fc74dd0a95e744c7f07 (publié) · Instagram : ÉCHEC ×2, aucun compte Instagram connecté dans Zernio |

Notes 2026-11-06 :
- Règles ESCAPE précédentes : aucune vidéo du soir dans le journal (seulement le test validé SPIKE ESCAPE dans engines/spike_escape).
- Débit : avec les flags exacts (CRF 14) le fond noir donne 0,6 Mb/s ; même CRF 1 ne dépasse pas 1,2 Mb/s. Ajout de `-x264-params filler=1` (bourrage, image identique) -> 24,9 Mb/s.
- Le fichier publié (135 Mo) dépasse la limite GitHub de 100 Mo : videos/2026-11-06-escape-wider-gap.mp4 est le même rendu sans bourrage ; sha256 du fichier publié dans videos/2026-11-06-escape-wider-gap.published.sha256.
- QC : 16 images clés, cadrage OK (centre 539,5/1074,5, largeur 998, marges 41/41, ouverture centrée x=540, titre centré, base y=440) ; logs : 0 traversée de pic/obstacle/mur, 13 morts sur pic = 13 élargissements de 2°, évasion à 103,9° (dans l'ouverture). Audio pic -1,0 dBFS, sons calés sur les événements de la simu (décalage ≤ 17 ms).
