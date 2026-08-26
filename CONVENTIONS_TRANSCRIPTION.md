# Conventions de transcription des Mémoires de Benoît Coste

Ce document consigne l'ensemble des règles éditoriales, typographiques, techniques et organisationnelles pour la transcription en LaTeX des mémoires manuscrites et dactylographiées de Benoît Coste (1781--1845).

---

## 1. Organisation du projet & Gestion de version (Git)

### 1.1 Dépôt Git
- Le projet est versionné sous Git dans le répertoire racine.
- Les fichiers sources originaux (scans PDF) sont conservés dans `Originaux/`.
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
\title{\Huge \textbf{Mémoires de Benoît Coste}}
\author{\textbf{Benoît Coste} \\ 
\small Fils d'Isaac Coste et de Jeanne Jordan (1756--1853) \\
\small Père de : Marie (épouse de François Félix Berloty), Blandine (religieuse), François}
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

### 3.5 Interventions et résumés éditoriaux
- Les passages résumés ou les ajouts contextuels introduits par le transcripteur sont placés en italique et entre parenthèses :
  ```latex
  \textit{(Après le départ de M. Satin, Benoît Coste est confié à un Sulpicien, M. Molin...)}
  ```
- Les coupures ou omissions sont signalées par `(...)` ou `...... (...)`.

### 3.6 Prise en compte des corrections manuscrites
- Les documents originaux combinent texte dactylographié et corrections manuscrites (mots barrés, ajouts interlinéaires ou marginaux).
- **Règle absolue :** La transcription doit intégrer le texte final corrigé par la main de l'auteur ou du correcteur historique.
- L'analyse des scans est effectuée par lecture visuelle directe (Vision multimodal) pour distinguer finement les ajouts manuscrits des coquilles de machine à écrire.

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
| **Ch 1** | `Originaux/Ch 1.pdf` | Premières années et Jeunesse (1781--1800) | Transcrit |
| **Ch 2** | `Originaux/Ch 2.pdf` | Souvenirs du Siège de Lyon et de ses suites (1793) | Transcrit |
| **Ch 3** | `Originaux/Ch 3.pdf` | Souvenirs de Constance (1794--1796) | Transcrit |
| **Ch 4** | `Originaux/Ch 4.pdf` | Souvenirs de Noefels et pèlerinage à N.-D. des Hermites (1796--1797) | Transcrit |
| **Ch 5** | `Originaux/Ch 5.pdf` | Souvenirs de l'état de la religion en France (1797) | Transcrit |
| **Ch 6** | `Originaux/Ch 6.pdf` | Souvenirs de l'élection de Pie VII, du 18 brumaire et de mon entrée dans le commerce (1798--1800) | Transcrit |
| **Ch 7** | `Originaux/Ch 7.pdf` | Souvenirs des premières heures de liberté accordées à la religion (1800--1801) | Transcrit |
| **Ch 8** | `Originaux/Ch 8.pdf` | Souvenirs de la signature du Concordat | Transcrit |
| **Ch 9** | `Originaux/Ch 9.pdf` | Souvenirs de la publication du Concordat et de l'ouverture de l'église de Saint Jean | Transcrit |
| **Ch 10** | `Originaux/Ch 10.pdf` | Souvenirs de la première procession aux Chartreux et de l'ouverture de l'église de St Pierre | Transcrit |
| **Ch 11** | `Originaux/Ch 11.pdf` | Souvenirs de l'ouverture de l'église d'Écully, de quelques amis et de la mort de mon père | Transcrit |
| **Ch 12** | `Originaux/Ch 12.pdf` | Souvenirs de la rétractation du curé de St Pierre et de l'extinction du schisme | Transcrit |
| **Ch 13** | `Originaux/Ch 13.pdf` | Souvenirs du rétablissement du culte extérieur, de la fondation de l'œuvre des prisons et de celle des confréries du Saint Sacrement | Transcrit |
| **Ch 14** | `Originaux/Ch 14.pdf` | Souvenirs des deux passages du Pape à Lyon et de l'ouverture de l'église de Fourvières | Transcrit |
| **Ch 15** | `Originaux/Ch 15.pdf` | Souvenir du mariage de ma sœur, de mon entrée au bureau de bienfaisance et de mon mariage | Transcrit |
| **Ch 16** | `Originaux/Ch 16.pdf` | Souvenirs de la vocation de ma sœur Catherine et de notre vie de famille | Transcrit |
| **Ch 17** | `Originaux/Ch 17.pdf` | Souvenirs de la persécution exercée par Napoléon contre le Pape Pie VII | Transcrit |
| **Ch 18** | `Originaux/Ch 18.pdf` | Souvenirs de la campagne de Russie (1812) et de l'invasion de la France (1814-1815) | Transcrit |
| **Ch 19** | `Originaux/Ch 19.pdf` | Souvenirs du retour du Pape Pie VII à Rome et de la Restauration | Transcrit |
| **Ch 20** | `Originaux/Ch 20.pdf` | Souvenirs des Cent Jours et de ma captivité | Transcrit |
| **Ch 21** | `Originaux/Ch 21.pdf` | Souvenirs d'une procession à Fourvière, de l'érection de la croix de la place St Pierre et du rétablissement de la confrérie des Martyrs | Transcrit |
| **Ch 22** | `Originaux/Ch 22.pdf` | Souvenirs de ma vie militaire (Campagne de la Côte Saint-André) | Transcrit |
| **Ch 23** | `Originaux/Ch 23.pdf` | Mes souvenirs de soixante ans | À transcrire |
| **Ch 24--38** | `Originaux/Ch 24.pdf` à `Ch 38.pdf` | Chapitres suivants | À transcrire |
