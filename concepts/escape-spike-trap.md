# ESCAPE — SPIKE TRAP (2026-11-08)
Règle : chaque balle morte devient un NOUVEAU PIC là où elle meurt (son corps gris reste, on rebondit dessus, et un pic mortel en pousse, pointé vers le centre de l'anneau).
Moteur : engines/escape_spike_trap/ (copie de escape_spike ← spike_escape ; ouverture pile en bas à 90°, lancer fixe −80° ±8° à 360 px/s depuis (CX, CY−60)).
1. python3 sweep.py 20 20 28 0 600       -> graines valides (ouverture 20°, pic-piège 20 px, demi-angle de base 28°)
2. python3 face.py 8                     -> face_base.png (variante 8 : inclinaison −2,4°, sourire relevé 94, asymétrie −9, regard (3.5, 4.4))
3. python3 render_esc.py 407 final.mp4 20 -> vidéo finale avec son et screamer, encodage TikTok
Graine 407 · 15 essais · faux espoirs 56 px (2,6 s) et 12 px (14,4 s) · la gagnante survit 5,2 s · screamer à 24,45 s (58 %) · 42,4 s.
Anneau : orange (1.00,0.58,0.10) -> rose vif (1.00,0.20,0.52) -> violet (0.55,0.28,1.00).
Note : une version « mine à pics » (balle morte = étoile mortelle sans rebond) rendait l'évasion impossible (0/600 graines) : rejetée.
