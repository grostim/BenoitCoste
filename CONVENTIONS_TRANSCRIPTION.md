# Conventions de transcription des Mémoires de Benoît Coste

Ce document consigne l'ensemble des règles éditoriales, typographiques, techniques et organisationnelles pour la transcription en LaTeX des mémoires manuscrites et dactylographiées de Benoît Coste (1781--1845).

---

## 1. Organisation du projet & Gestion de version (Git)

### 1.1 Dépôt Git
- Le projet est versionné sous Git dans le répertoire racine.
- Les fichiers sources originaux sont conservés dans `Originaux/`. Les 38 scans du tapuscrit sont classés dans `Version dactylographiée - source Grosbois/` ; la transcription complémentaire est nommée `Transcription Jacques Lépine 2023.pdf`.
- Les scans de la copie manuscrite Berloty Boffard sont classés dans `Originaux/Version manuscrite. source Famille Berloty Boffard/`, par tome et numéro de scan. Ce numéro exprime l’ordre de lecture et ne remplace pas la pagination manuscrite. L’inventaire conserve les noms d’origine et les correspondances des PDF redondants ; les variantes annotées et les repères sont distincts des scans de référence.
- Le document principal est `Memoires de Benoit Coste.tex`.
- Les fichiers auxiliaires LaTeX (`*.aux`, `*.log`, `*.toc`, etc.) sont exclus via `.gitignore`.

### 1.2 Conventional Commits (en français uniquement)
Tous les messages de commit doivent strictement suivre la norme des *Conventional Commits* rédigés en français, avec la structure suivante :

```
<type>[portée optionnelle]: <description en français au présent de l'indicatif/infinitif>

[corps optionnel explicatif]
```

#### Types autorisés :
- `feat:` : Ajout d'une nouvelle transcription de chapitre ou de contenu textuel majeur (ex. `feat: transcription du chapitre 21`).
- `fix:` : Correction de transcription, de coquille, de ponctuation ou d'erreur LaTeX (ex. `fix: correction d'une coquille dans le chapitre 4`).
- `docs:` : Mise à jour de la documentation, du fichier de conventions ou de métadonnées (ex. `docs: ajout des règles de transcription`).
- `style:` : Ajustements de mise en page, d'espacement, de formatage LaTeX sans modification du texte (ex. `style: harmonisation des tirets d'incise`).
- `refactor:` : Réorganisation structurelle du code LaTeX (ex. `refactor: normalisation des titres de sections`).
- `chore:` : Tâches de maintenance, mise à jour du `.gitignore` ou scripts de travail.

---

## 2. Structure et Préambule LaTeX

### 2.1 Configuration globale
Le document utilise la classe `report` avec les packages suivants :
```latex
\documentclass[11pt,a4paper]{report}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[french]{babel}
\usepackage{amsmath}
\usepackage{geometry}
\geometry{margin=2.5cm}
\usepackage{hyperref}
\usepackage{parskip}
\usepackage{setspace}
```

### 2.2 Titre et métadonnées
```latex
\title{\Huge \textbf{Mes souvenirs de soixante ans}}
\author{\textbf{Benoît Coste}}
\date{}
```

---

## 3. Règles de Transcription et Mise en Page

### 3.1 Préservation de la structure et du chapitrage
- Les mémoires sont découpées en **38 chapitres** correspondant aux 38 fascicules/fichiers scannés (`Ch 1.pdf` à `Ch 38.pdf`).
- Chaque chapitre est introduit par un bloc de commentaires standardisé :
  ```latex
  % ===================================================
  % CHAPITRE X
  % ===================================================
  \chapter{Titre normalisé du chapitre (Dates)}
  ```

### 3.2 Normalisation des titres de chapitres
- Étant donné que les mémoires ont été rédigées sur une longue période avec des variations d'intitulés, les titres de chapitres sont normalisés dans la commande `\chapter{...}`.
- La structure générale adoptée est : `\chapter{Souvenirs de/du [Sujet] (Année--Année)}` ou `\chapter{Premières années et Jeunesse (1781--1800)}`.

### 3.3 Mentions dactylographiées en marge $\rightarrow$ Sous-titres (`\section*`)
- Les mentions tapuscrites figurant dans la marge gauche du document original doivent être transcrites sous forme de sous-titres non numérotés avec la commande `\section*{...}`.
- Si la mention comporte une année, formater sous la forme : `\section*{AAAA -- Titre de la section}` (ex. `\section*{1815 -- Mon arrestation}`, `\section*{1802 -- Publication du Concordat}`).
- Si la mention ne comporte pas d'année : `\section*{Titre de la section}` (ex. `\section*{Le costume d'enfance}`).
- Les majuscules intégrales de la marge sont converties en casse de titre standard (première lettre en majuscule, minuscules ensuite, sauf pour les noms propres).

### 3.4 Notes de bas de page (`\footnote`)
- Toutes les notes de bas de page présentes dans l'original doivent être scrupuleusement préservées.
- Utiliser la commande standard `\footnote{Texte de la note. (Note de l'auteur)}`.
- Si la note originale précise une mention d'auteur, la reproduire fidèlement : `(Note de l'auteur)` ou `(NOTE DE L'AUTEUR)`.

### 3.5 Source complémentaire et interventions éditoriales
- La transcription alternative est conservée dans `Originaux/Transcription Jacques Lépine 2023.pdf` ; les scans des 38 fascicules restent la source de base.
- Les passages de Benoît Coste plus développés dans cette source remplacent les résumés ou passages abrégés du premier tapuscrit. L'introduction de l'auteur et son plan en cinq époques sont rétablis avant la première époque.
- Conserver les 38 chapitres des fascicules : les limites des chapitres 1 à 4 diffèrent parfois dans la transcription alternative. Une différence de découpage ne justifie pas de répéter un passage.
- Préserver les informations et notes déjà présentes dans la source de base. Vérifier les écarts dans leur contexte : une note déplacée en bas de page du PDF ne constitue pas un complément nouveau.
- Les préfaces des éditeurs, gloses modernes, identifications généalogiques, légendes et illustrations de la transcription alternative ne sont pas des mots de Benoît Coste et ne sont pas incorporées à son récit.
- Les préambules de Léon Peillon (printemps 1987), de Michel de Viviès et Marie-Madeleine Plancher-Coste (mars 2009) et de Jacques Lépine (15 avril 2023) sont reproduits séparément après la note du transcripteur et avant l'introduction de l'auteur, dans l'ordre chronologique. Chacun porte sa provenance et sa date. Le premier est issu du recueil annexe collationné par Jacques Lépine, conservé dans `Originaux/Recueil autour de Benoit Coste1.pdf`.
- Les ajouts importants portent un commentaire LaTeX indiquant les pages de cette source. Le relevé des restitutions figure dans `COMPLEMENTS_TRANSCRIPTION.md`.
- Si une lacune ne peut pas être rétablie, conserver son signalement ; ne pas reconstituer un passage de mémoire. Cette collation de deux transcriptions ne constitue pas une vérification directe du manuscrit autographe.

### 3.6 Prise en compte des corrections manuscrites
- Les documents originaux combinent texte dactylographié et corrections manuscrites (mots barrés, ajouts interlinéaires ou marginaux).
- **Règle absolue :** La transcription doit intégrer le texte final corrigé par la main de l'auteur ou du correcteur historique.
- L'analyse des scans est effectuée par lecture visuelle directe (Vision multimodal) pour distinguer finement les ajouts manuscrits des coquilles de machine à écrire.

### 3.7 Citations latines et notes du transcripteur
- Pour chaque citation ou passage en latin dans le texte, une note de bas de page (`\footnote{...}`) est systématiquement ajoutée.
- La note doit impérativement préciser :
  1. La source scripturaire, patristique ou liturgique exacte (Psaume, Évangile, Épître, hymne liturgique, etc.).
  2. La traduction fidèle en français.
  3. La mention explicite `(Note du transcripteur)` pour la distinguer clairement des notes de l'auteur.
  Exemple :
  ```latex
  \textit{Non nobis Domine, non nobis, sed nomini tuo da gloriam}\footnote{Psaume 113b (115), 1 : « Non pas à nous, Seigneur, non pas à nous, mais à ton nom donne la gloire » (Note du transcripteur).}
  ```

---

## 4. Règles Typographiques et Orthotypographiques

### 4.1 Dialogues et incises
- Les répliques de dialogue sont introduites par un tiret demi-cadratin (`--`) :
  ```latex
  -- Monsieur, lui dis-je, on vous appelle.
  ```
- Les incises dans le texte sont encadrées par des tirets demi-cadratins :
  ```latex
  mon père, -- au contraire soumis à l'influence de Chalier, -- favorisait les fauteurs de désordre.
  ```

### 4.2 Intervalles de dates et nombres
- Utiliser le double tiret pour les plages temporelles : `(1781--1800)`, `(1794--1796)`.

### 4.3 Abréviations et exposants
- Utiliser la commande `\up{...}` de `babel[french]` pour les exposants :
  - $4^{\text{e}}$ étage $\rightarrow$ `4\up{e} étage`
  - $1^{\text{er}}$ $\rightarrow$ `1\up{er}`
  - Saint $\rightarrow$ `St` ou `Ste` (ex. `St Pierre`, `Ste Marie`).
  - Messieurs $\rightarrow$ `M.M.` ou `Messieurs`, Monsieur $\rightarrow$ `M.` ou `monsieur`.

### 4.4 Ligatures et caractères spéciaux
- Utiliser les ligatures françaises : `cœur`, `sœur`, `œuvre`, `vœu`.
- Conserver les majuscules accentuées (`À`, `É`, `È`, etc.) selon l'usage moderne.
- Les termes latins ou en langue étrangère sont mis en italique : `\textit{in petto}`, `\textit{Télémaque}`.

### 4.5 Casse des noms propres
- Dans le tapuscrit d'origine, certains noms propres apparaissaient en capitales d'imprimerie intégrales (ex. `M. TESTE`, `M. ROYER`, `M. ZINDEL`).
- **Règle de normalisation :** Tous les noms propres de personnes, de lieux ou d'institutions doivent être uniformisés en bas de casse avec initiale majuscule (Title Case) : `M. Teste`, `M. Royer`, `M. Zindel`, `Monseigneur Spina`, `M. de Fitz-James`. Seuls les chiffres romains (ex. `Pie VII`, `Louis XVI`) et les sigles/abréviations d'époque (`N.-D.`, `M.M.`) conservent des majuscules multiples.

### 4.6 Espacements et paragraphes
- Les changements de paragraphe sont marqués par une ligne vide (géré via `parskip`).
- La ponctuation haute (`;`, `:`, `!`, `?`) bénéficie de l'espacement automatique géré par `babel[french]`.

---

## 5. État d'avancement de la transcription

| Chapitre | Fichier source | Titre normalisé | Statut |
| :---: | :---: | :--- | :---: |
| **Ch 1** | `Originaux/Version dactylographiée - source Grosbois/Ch 1.pdf` | Premières années et Jeunesse (1781--1800) | Transcrit |
| **Ch 2** | `Originaux/Version dactylographiée - source Grosbois/Ch 2.pdf` | Souvenirs du Siège de Lyon et de ses suites (1793) | Transcrit |
| **Ch 3** | `Originaux/Version dactylographiée - source Grosbois/Ch 3.pdf` | Souvenirs de Constance (1794--1796) | Transcrit |
| **Ch 4** | `Originaux/Version dactylographiée - source Grosbois/Ch 4.pdf` | Souvenirs de Noefels et pèlerinage à N.-D. des Hermites (1796--1797) | Transcrit |
| **Ch 5** | `Originaux/Version dactylographiée - source Grosbois/Ch 5.pdf` | Souvenirs de l'état de la religion en France (1797) | Transcrit |
| **Ch 6** | `Originaux/Version dactylographiée - source Grosbois/Ch 6.pdf` | Souvenirs de l'élection de Pie VII, du 18 brumaire et de mon entrée dans le commerce (1798--1800) | Transcrit |
| **Ch 7** | `Originaux/Version dactylographiée - source Grosbois/Ch 7.pdf` | Souvenirs des premières heures de liberté accordées à la religion (1800--1801) | Transcrit |
| **Ch 8** | `Originaux/Version dactylographiée - source Grosbois/Ch 8.pdf` | Souvenirs de la signature du Concordat | Transcrit |
| **Ch 9** | `Originaux/Version dactylographiée - source Grosbois/Ch 9.pdf` | Souvenirs de la publication du Concordat et de l'ouverture de l'église de Saint Jean | Transcrit |
| **Ch 10** | `Originaux/Version dactylographiée - source Grosbois/Ch 10.pdf` | Souvenirs de la première procession aux Chartreux et de l'ouverture de l'église de St Pierre | Transcrit |
| **Ch 11** | `Originaux/Version dactylographiée - source Grosbois/Ch 11.pdf` | Souvenirs de l'ouverture de l'église d'Écully, de quelques amis et de la mort de mon père | Transcrit |
| **Ch 12** | `Originaux/Version dactylographiée - source Grosbois/Ch 12.pdf` | Souvenirs de la rétractation du curé de St Pierre et de l'extinction du schisme | Transcrit |
| **Ch 13** | `Originaux/Version dactylographiée - source Grosbois/Ch 13.pdf` | Souvenirs du rétablissement du culte extérieur, de la fondation de l'œuvre des prisons et de celle des confréries du Saint Sacrement | Transcrit |
| **Ch 14** | `Originaux/Version dactylographiée - source Grosbois/Ch 14.pdf` | Souvenirs des deux passages du Pape à Lyon et de l'ouverture de l'église de Fourvières | Transcrit |
| **Ch 15** | `Originaux/Version dactylographiée - source Grosbois/Ch 15.pdf` | Souvenir du mariage de ma sœur, de mon entrée au bureau de bienfaisance et de mon mariage | Transcrit |
| **Ch 16** | `Originaux/Version dactylographiée - source Grosbois/Ch 16.pdf` | Souvenirs de la vocation de ma sœur Catherine et de notre vie de famille | Transcrit |
| **Ch 17** | `Originaux/Version dactylographiée - source Grosbois/Ch 17.pdf` | Souvenirs de la persécution exercée par Napoléon contre le Pape Pie VII | Transcrit |
| **Ch 18** | `Originaux/Version dactylographiée - source Grosbois/Ch 18.pdf` | Souvenirs de la campagne de Russie (1812) et de l'invasion de la France (1814-1815) | Transcrit |
| **Ch 19** | `Originaux/Version dactylographiée - source Grosbois/Ch 19.pdf` | Souvenirs du retour du Pape Pie VII à Rome et de la Restauration | Transcrit |
| **Ch 20** | `Originaux/Version dactylographiée - source Grosbois/Ch 20.pdf` | Souvenirs des Cent Jours et de ma captivité | Transcrit |
| **Ch 21** | `Originaux/Version dactylographiée - source Grosbois/Ch 21.pdf` | Souvenirs d'une procession à Fourvière, de l'érection de la croix de la place St Pierre et du rétablissement de la confrérie des Martyrs | Transcrit |
| **Ch 22** | `Originaux/Version dactylographiée - source Grosbois/Ch 22.pdf` | Souvenirs de ma vie militaire (Campagne de la Côte Saint-André) | Transcrit |
| **Ch 23** | `Originaux/Version dactylographiée - source Grosbois/Ch 23.pdf` | Souvenirs de famille et de l'administration des prisons (1817) | Transcrit |
| **Ch 24** | `Originaux/Version dactylographiée - source Grosbois/Ch 24.pdf` | Souvenirs de la naissance du duc de Bordeaux, de celle de mes filles et du voyage de Bellevaux (1818--1821) | Transcrit |
| **Ch 25** | `Originaux/Version dactylographiée - source Grosbois/Ch 25.pdf` | Souvenirs de l'établissement de l'œuvre de la Propagation de la Foi (1822) | Transcrit |
| **Ch 26** | `Originaux/Version dactylographiée - source Grosbois/Ch 26.pdf` | Souvenirs de la naissance de mes garçons, de la première messe de mon beau-frère et de la mort de ma mère (1822--1826) | Transcrit |
| **Ch 27** | `Originaux/Version dactylographiée - source Grosbois/Ch 27.pdf` | Souvenirs du Jubilé (1826) | Transcrit |
| **Ch 28** | `Originaux/Version dactylographiée - source Grosbois/Ch 28.pdf` | Souvenirs de la mort de Pierre, de la première communion de mes filles et de quelques événements de famille (1826--1829) | Transcrit |
| **Ch 29** | `Originaux/Version dactylographiée - source Grosbois/Ch 29.pdf` | Souvenirs de la Révolution de Juillet (1830) | Transcrit |
| **Ch 30** | `Originaux/Version dactylographiée - source Grosbois/Ch 30.pdf` | Souvenirs de la mort de mon beau-père, de celle de ma belle-mère et de la procession de La Guillotière (1831) | Transcrit |
| **Ch 31** | `Originaux/Version dactylographiée - source Grosbois/Ch 31.pdf` | Souvenirs des journées de novembre (1831) | Transcrit |
| **Ch 32** | `Originaux/Version dactylographiée - source Grosbois/Ch 32.pdf` | Souvenirs de l'invasion du choléra en France (1832) | Transcrit |
| **Ch 33** | `Originaux/Version dactylographiée - source Grosbois/Ch 33.pdf` | Souvenirs de la première communion de François, de la naissance et de la mort de Joséphine et autres souvenirs de famille (1833) | Transcrit |
| **Ch 34** | `Originaux/Version dactylographiée - source Grosbois/Ch 34.pdf` | Souvenirs des journées d'avril (1834) | Transcrit |
| **Ch 35** | `Originaux/Version dactylographiée - source Grosbois/Ch 35.pdf` | Souvenirs de nos voyages de famille, de la mort de ma sœur Franchet, du mariage de Marie, etc. (1835--1839) | Transcrit |
| **Ch 36** | `Originaux/Version dactylographiée - source Grosbois/Ch 36.pdf` | Tristes souvenirs de 1840 | Transcrit |
| **Ch 37** | `Originaux/Version dactylographiée - source Grosbois/Ch 37.pdf` | Souvenirs de mon départ de Lyon et de mon voyage jusqu'à Londres (1840) | Transcrit |
| **Ch 38** | `Originaux/Version dactylographiée - source Grosbois/Ch 38.pdf` | Conclusion (Partie religieuse, Partie politique, Partie personnelle, Actions de grâces) | Transcrit |
