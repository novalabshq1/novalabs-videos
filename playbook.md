# Playbook @novalabs.hq

Le guide créatif des vidéos. Chaque tâche le lit avant de créer une vidéo.

**Qui peut modifier quoi**
- Yanis peut tout modifier.
- La tâche automatique peut AJOUTER du contenu dans les sections marquées ✏️ (nouvelles familles, idées, styles, accroches, astuces). Elle ne supprime jamais une ligne écrite par Yanis et ne touche pas aux sections 🔒.
- Chaque ajout de la tâche se termine par `(ajout auto AAAA-MM-JJ : raison courte)` et va dans le journal en bas du fichier.

---

## 🔒 Recette d'une vidéo (obligatoire)
- Une RÈGLE simple comprise en 2 secondes ("every bounce = +1 ball", "every smash speeds up the rams").
- Un COMPTEUR bien visible, en gros chiffres colorés sous le titre, qui bouge (balls: 13, BANDS BROKEN 21/200, 11 RPM, 1kg, 20 folds = 105 m…).
- Une ESCALADE : ça accélère, grossit, se multiplie, chauffe.
- Un PAYOFF : explosion, éclosion, cassure, convergence parfaite, objectif atteint.
- Une accroche/question courte en anglais en haut + une raison de commenter.
- Durée 20 à 60 s.
- Ne jamais reprendre la même famille que l'une des 2 dernières vidéos, ni le même personnage ou mode son que la dernière.
- Au maximum 1 vidéo sur 4 (jamais 2 de suite) une VARIANTE nette d'un concept qui a marché (règle, personnage, son, palette, obstacles, accroche changés ; jamais une copie avec un autre seed).

## 🔒 Droits et sécurité
- Sons : synthétisés par la tâche, ou fichiers de sounds/ (choix de Yanis). Jamais de musique ou d'extrait protégé trouvé ailleurs.
- Mélodies : uniquement domaine public (œuvres publiées avant 1929).
- Personnages : dessinés en code ou images de assets/. Jamais de copie d'un personnage de marque, de dessin animé ou du personnage exact d'un autre créateur.
- Chiffres réels (hauteurs, distances, maths) : toujours calculés dans le script et vérifiés.
- Pas de voix synthétique robotique : sans fichier de mot dans sounds/, le mot n'apparaît qu'en texte à l'écran.

---

## ✏️ Familles de formats
a) **Multiplication** : "every bounce = +1 ball", la balle se divise, chaque touche ajoute un œuf, compteur "balls: N", traînées néon.
b) **Convergence / géométrie** : N balles lancées d'un même point dans une ellipse (propriété des foyers : elles se rejoignent toutes au 2e foyer), "Will they all hit the same point?", traînées arc-en-ciel, spirographe, cordes entre impacts, pendulum wave.
c) **Destruction** : "Red hot metal ball vs 200 rubber bands" (BANDS BROKEN x/200 + température), balle qui casse des couches, "THE EGG GOES DEEPER" (un œuf tombe à travers des couches colorées qui plient puis cèdent, son poids augmente), "How long until the box breaks?".
d) **Machines** : bras/marteau/vérin qui tourne dans un cercle et frappe ("every smash speeds up the rams", compteur RPM), arcs rotatifs aux coins d'une boîte, presse hydraulique, broyeur.
e) **Roulette / zones** : arène polygonale avec des zones-effets écrites dessus (BIG, SMALL, x5, x20, crâne = mort, forme = transformation), "Every spin does something different".
f) **Évasion** : anneaux rotatifs à ouverture, cercle qui rétrécit, labyrinthe, cercle à pics, "only 4 seconds to escape".
g) **Battle** : A vs B, équipes de couleurs, tournoi à élimination, dernier survivant, "Which one wins? 👇".
h) **Rayons** : des personnages glissent le long de lignes néon qui tournent autour d'un centre, se cognent au centre, rebondissent.
i) **Devinette musicale** : "Guess what song this is", chaque rebond = note suivante d'une mélodie célèbre du domaine public, réponse révélée à la fin ou en premier commentaire.
j) **Remplissage** : "how many eggs fit in the jar?", entonnoir, sablier, niveau qui monte.
k) **Échelle / maths visuelles** : quantité qui double à chaque étape comparée à des repères réels avec barre de progression vers un objectif ("How many folds to reach the Moon?" : papier 0,1 mm × 2^n, 20 plis = 105 m, 42 plis ≈ Lune). Caméra qui dézoome, repères en néon simplifié (maison, tour de Pise, Tour Eiffel, Burj Khalifa, Everest, avion, ISS, Lune) avec leur hauteur. Son qui monte d'un demi-ton par étape.

On peut combiner deux familles (destruction + œufs, roulette + chats…).

## ✏️ Banque d'idées (pas encore faites)
- Battle A vs B
- Traînée spirographe
- Hexagone qui rétrécit
- Pluie d'objets dans un entonnoir
- Cercle à pics
- Pendulum wave
- Cordes entre impacts
- Effet papillon
- Œuf qui se fissure à chaque rebond et éclot
- Chat qui grossit à chaque "FAH"
- Tournoi de 8 personnages dans une arène
- Nuggets qui tombent sur un plus gros nugget
- Grain de riz qui double jusqu'à remplir la Terre
- Combien de balles pour remplir la Tour Eiffel

## ✏️ Personnages
- Balle néon (classique)
- Dessinés en code : œuf blanc avec deux points pour les yeux, chat cartoon, nugget, citrouille, crâne, banane, cube avec visage, fantôme. Squash & stretch au rebond, yeux qui réagissent.
- Images de assets/ (voir assets/LISEZMOI.md), affichées à 200 px de diamètre max.
- En grand nombre, ça marche très bien (12 œufs, 30 chats).

## ✏️ Sons
- (A) Mot crié : fichier sounds/<mot>.mp3 joué sur chaque impact important + le mot en texte qui jaillit ("EGG!", "FAH!"). Pitch ±15 %, max ~8 mots/s ; si trop dense, 1 impact sur 2 ou 3 et effets courts pour les autres.
- (B) Effets synthétisés : bonk, boing, pop, impact grave saturé, craquement, whoosh, ding, riser avant le payoff, grosse explosion finale.
- (C) Mélodie domaine public note par note (obligatoire pour la devinette musicale).
- (D) Mix mélodie + mots/effets sur les moments forts.
- Mixage : -1 dBFS, pas de clipping, sons calés sur les impacts (< 30 ms).

## ✏️ Styles visuels
- Néon arc-en-ciel sur fond noir
- Minimaliste blanc sur noir, traits fins
- Couches colorées texturées
- Fond texturé sombre avec glow
- Effets brainrot (au moins 3) : texte qui jaillit, screen shake léger, zoom punch, flash à l'explosion, particules, compteur qui grossit quand il change.
- Zones interdites : 250 px du bas et bande droite de 140 px (interface des apps), sauf le watermark "@novalabs.hq".

## ✏️ Accroches et légendes qui marchent
- "Will they all hit the same point? 🤯"
- "How long until the box breaks?"
- "Every spin does something different"
- "Guess what song this is"
- "How many folds to reach the Moon?"
- "Which one wins? 👇"
- Hashtags de base : #satisfying #oddlysatisfying #physics + spécifiques de la veille.

## ✏️ Astuces techniques
- Metricool : TikTok exige tiktokData.title ; draft false + autoPublish true = publication automatique.
- Si le rendu dépasse 12 min, réduire la complexité plutôt que la durée.

---

## Journal des modifications
- 2026-10-28 : création du playbook (Yanis + Claude).
