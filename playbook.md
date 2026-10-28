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

## 🔒 Exigence de qualité (Yanis)
- La qualité doit être TOP à chaque vidéo : rendu net et fluide, animations propres, couleurs soignées, rien d'approximatif ou de "fait vite". Mieux vaut une idée simple très bien exécutée qu'une idée compliquée bâclée.
- Le concept doit être bon AVANT de coder : se demander "est-ce que je m'arrêterais en scrollant ?" et "est-ce qu'on a envie de voir la fin ?". Si la réponse est non, changer de concept.
- TON : jamais "gênant" ni forcé. Le brainrot vient du son, du rythme et du visuel, PAS des mots. Interdit à l'écran comme dans les légendes et commentaires : l'argot internet plaqué (LOL, OMG, BRUH, WTF, sigma, skibidi, rizz, aura, "no way", "fr fr"…), les emojis en rafale, les noms de personnages en argot. Les personnages sont nommés sobrement (couleur ou numéro : Red / Blue, #1 à #4, ou le code de l'équipe) ou pas du tout. Textes à l'écran : titre-question, compteur, chiffres ("+1", "-1 HP", "GOAL", "x5"), c'est tout. Légendes courtes et naturelles, comme les gros comptes du genre : "Which one wins?", "Will they all hit the same point?" — maximum 1 emoji. (demande de Yanis 2026-10-28 : Cat Battle avec chats nommés LOL/OMG/BRUH jugée gênante)
- Au contrôle qualité, si une image a l'air amateur (texte mal placé, objets qui se chevauchent bizarrement, physique qui bug, fin molle), corriger avant de programmer.

## 🔒 Droits et sécurité
- Sons : synthétisés par la tâche, ou fichiers de sounds/ (choix de Yanis). Jamais de musique ou d'extrait protégé trouvé ailleurs.
- Mélodies : uniquement domaine public (œuvres publiées avant 1929).
- Personnages : dessinés en code ou images de assets/. Jamais de copie d'un personnage de marque, de dessin animé ou du personnage exact d'un autre créateur.
- Chiffres réels (hauteurs, distances, maths) : toujours calculés dans le script et vérifiés.
- Pas de voix synthétique robotique.
- Logos d'équipes, de clubs ou de marques : ils sont protégés, donc ne jamais les dessiner ni les copier. Utiliser les couleurs du club et un nom court ou un code à 3 lettres (MTL, PSG, RMA…) sur la bille. Exception : si Yanis a déposé un logo dans assets/, c'est son choix et on peut l'utiliser.

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

l) **Match de foot (événement)** : à faire 1 à 2 jours AVANT un gros match (Ligue des champions, grand derby, Classico, sélections nationales, CF Montréal en match important ; repéré pendant la veille). Un grand cercle qui tourne avec une ouverture en forme de but (cage dessinée, filet), deux billes aux couleurs des deux équipes avec leur code ou nom court, elles rebondissent dans le cercle et chaque fois qu'une bille sort par le but = BUT pour son équipe. Tableau de score en haut ("PSG 2 - 1 RMA"), CHRONO 0' → 90' qui défile vite (toute la vidéo ≈ 40-50 s), mi-temps à 45', grosse célébration au coup de sifflet final (confettis aux couleurs du vainqueur). Accroche : "PSG vs Real Madrid — the physics predicts the score 👇" ; premier commentaire : "Who wins for real? Drop your score 👇". Son : uniquement des effets (rebonds, filet qui tremble, foule synthétisée, sifflet), pas de mot crié écrit à l'écran. Publier avant le match, jamais après.

m) **Révélation (« Guess what this is? »)** : une image cachée sous un masque noir, la balle efface le masque là où elle passe (traînée qui "creuse") et révèle petit à petit l'image ; compteur "11% FILLED" + barre de progression ; le spectateur essaie de deviner avant la fin, la réponse apparaît à 100 %. C'est le format qui génère le plus de partages ("send to a friend who guesses first"). Images autorisées : tableaux célèbres du domaine public (Joconde, La Nuit étoilée, Le Cri, La Grande Vague…), monuments et animaux dessinés en code, drapeaux, contours de pays, objets ; ou une image déposée par Yanis dans assets/reveal/. Jamais de photo de célébrité ou de personne réelle trouvée en ligne. Accroche : "Can you guess what this is?" / "Guess the painting before 50%". Son : note qui monte avec le pourcentage + petit "ding" tous les 10 %, gros payoff à la révélation.

On peut combiner deux familles (destruction + œufs, roulette + chats…).

## ✏️ Banque d'idées (pas encore faites)
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
- Série « Cat Battle Episode N » : mêmes 4 chats, classement des victoires cumulé affiché, « Who wins episode 2? » (ajout auto 2026-10-28 : les ball battles tournent en séries récurrentes, fidélise)

## ✏️ Personnages
- Objet principal : une boule/bille la plupart du temps (~3 vidéos sur 4). De temps en temps un autre objet pour surprendre (cube, œuf, goutte, gemme, sphère en bois ou métal à découper, fruit, pièce, dé, hexagone, ressort, personnage simple dessiné en code). Jamais 2 vidéos de suite sans boule. (Yanis)
- Balle néon (classique)
- Dessinés en code : œuf blanc avec deux points pour les yeux, chat cartoon, nugget, citrouille, crâne, banane, cube avec visage, fantôme. Squash & stretch au rebond, yeux qui réagissent.
- Images de assets/ (voir assets/LISEZMOI.md), affichées à 200 px de diamètre max. De temps en temps seulement : max 1 vidéo sur 4, jamais 2 de suite (Yanis).
- En grand nombre, ça marche très bien (12 œufs, 30 chats).

## ✏️ Sons
- (A) Mot crié : fichier sounds/<mot>.mp3 joué sur chaque impact important. De temps en temps seulement : max 1 vidéo sur 4, jamais 2 de suite (Yanis). SEULEMENT le son : ne PAS écrire le mot ("FAH", "EGG"…) à l'écran, le son suffit (demande de Yanis). Pitch ±15 %, max ~8 mots/s ; si trop dense, 1 impact sur 2 ou 3 et effets courts pour les autres.
- (B) Effets synthétisés : bonk, boing, pop, impact grave saturé, craquement, whoosh, ding, riser avant le payoff, grosse explosion finale.
- (C) Mélodie domaine public note par note (obligatoire pour la devinette musicale).
- (D) Mix mélodie + mots/effets sur les moments forts.
- Mixage : -1 dBFS, pas de clipping, sons calés sur les impacts (< 30 ms).

## ✏️ Styles visuels
- Style "minimal premium" (celui des plus gros comptes) : fond sombre uni, UN seul objet au centre, UN gros chiffre en haut (16 Cuts, 11% FILLED, balls: 13, 20 folds = 105 m) + éventuellement une barre de progression, une seule ligne de question, aucun autre texte. Objets avec du volume quand c'est possible (dégradé, reflet, ombre, texture bois/métal/verre) plutôt que des formes plates. À privilégier au moins 1 vidéo sur 2.
- Néon arc-en-ciel sur fond noir
- Minimaliste blanc sur noir, traits fins
- Couches colorées texturées
- Fond texturé sombre avec glow
- Effets (1 ou 2 maximum, discrets, au service de la clarté) : texte qui jaillit (chiffres, "+1", "GOAL", "-1 HP"… mais jamais le mot crié du son), screen shake léger, zoom punch, flash à l'explosion, particules, compteur qui grossit quand il change.
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
- TikTok limite à 5 hashtags par post : mettre 5 hashtags précis dans le texte Metricool. (ajout auto 2026-10-28 : veille hashtags 2026)
- Battle (attention au visuel : pas de légende de personnages ni de barres de vie multiples, un seul compteur) : délai de 0,8 s entre deux dégâts d'une même paire et arène qui rétrécit selon le nombre de survivants, sinon trop de coups au début et duel final interminable. (ajout auto 2026-10-28 : réglage de cat-battle.py)
- Ellipse / foyers : des rayons réfléchis de foyer en foyer se rabattent tous sur le grand axe après 3-4 allers (les billes finissent empilées en colonne). Pour garder un bel éventail, faire repartir les billes en éventail régulier à chaque rencontre. Positions calculées analytiquement (trajet foyer→mur→foyer = 2a) : arrivée parfaitement simultanée, aucune dérive. (ajout auto 2026-10-28 : réglage de focus-doubling.py)
- Rendu : envoyer les images brutes (rgb24) directement à ffmpeg par un pipe au lieu d'écrire des PNG temporaires (2000 images en 2160x3840 = plusieurs Go de disque). Traînées « string art » : luminosité divisée par (1 + N/56) quand le nombre de billes N augmente, sinon l'image devient une bouillie. (ajout auto 2026-10-28 : rendu de focus-doubling.py)

---

## Journal des modifications
- 2026-10-28 : (Yanis) objet principal = boule la plupart du temps, autre objet de temps en temps ; images de chats retirées par Yanis.
- 2026-10-28 : (Yanis) qualité pro exigée ; sons/images de Yanis max 1 vidéo sur 4 ; effets discrets ; style minimal premium par défaut.
- 2026-10-28 : (Yanis) famille « Révélation » (ballloopz) et style « minimal premium » (asmrtherapy, MathMango, NexusBoxLab).
- 2026-10-28 : création du playbook (Yanis + Claude).
- 2026-10-28 : (Yanis) règle de ton anti-gênant (pas d'argot LOL/OMG/BRUH, noms sobres).
- 2026-10-28 : (Yanis) exigence de qualité, famille « Match de foot », mots criés en son seulement (plus en texte), règle sur les logos.
- 2026-10-28 : (auto) 2 astuces techniques (5 hashtags TikTok, réglage battle) + idée « Cat Battle Episode N » ; « Battle A vs B » retirée de la banque (réalisée en Cat Battle).
- 2026-10-28 : (auto) 2 astuces techniques (ellipse/foyers en éventail régulier, pipe ffmpeg + traînées atténuées).
