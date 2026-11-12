# ESCAPE — SPIKE ESCAPE (2026-11-12)
Moteur : engines/escape_spike/ (copie de spike_escape : ouverture pile en bas à 90°, lancer fixe −80° ±8° à 360 px/s depuis (540, 1015), screamer procédural + cri).
cd engines/escape_spike
1. python3 search.py 0 600 [GAP_DEG]  -> graines valides (30–45 s, ≥ 9 essais, essais ≤ 8 s, ≥ 2 faux espoirs < 70 px avant 15 s)
2. python3 render_esc.py 271 19.6 final.mp4 [temps des images clés...]   (sim -> esc_log.json, audio_esc.py -> esc_audio.wav, screamer.py/face.py, encodage final TikTok en une passe)
3. python3 qc.py 1176 1212   (cadrage, titre, lancers, morts)
Réglages : graine 271, ouverture 20°, 10 essais, évasion 36,45 s, durée 38,05 s, screamer 19,6 → 20,2 s (51 %).
Anneau cyan (0.10,0.90,0.85) -> bleu (0.20,0.45,1.00) -> magenta (0.85,0.25,1.00) ; titre « CAN ONE ESCAPE? ».
Visage : tête inclinée de −5°, sourire de 345 px avec coins relevés de 150 px, 22 dents, cheveux seed 3.
Anneau mesuré à l'écran : 1000 px de large, centre (539,5 ; 1070,5), marges 40/40, milieu de l'ouverture x = 539,5.
