# ESCAPE — SPIKE ESCAPE (2026-11-07)
Moteur : engines/escape_spike/ (copie de engines/spike_escape, ouverture pile en bas à 90°, lancer fixe −80° ±8° à 360 px/s depuis (CX, CY−60)).
1. python3 search.py 0 600 20            -> graines valides (30-45 s, ≥9 essais, essais ≤8 s, 2 faux espoirs <70 px avant 15 s)
2. python3 face.py 7                     -> face_base.png (visage procédural, variante 7 : inclinaison 1,8°, sourire relevé 91, asymétrie 14)
3. python3 render_esc.py 134 final.mp4 20 [images_clés]
   (choisit le moment du screamer, génère esc_audio.wav via audio_esc.py, encode directement avec les réglages TikTok)
Graine 134 · ouverture 20° · 12 essais · screamer à 24,57 s (57 %) · durée 42,9 s.
Anneau : menthe (0.10,0.95,0.70) -> azur (0.15,0.55,1.00) -> violet (0.85,0.30,1.00).
