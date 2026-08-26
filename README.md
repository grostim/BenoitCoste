# Mémoires de Benoît Coste (1781–1845)

[![Validation LaTeX & Publication](https://github.com/grostim/BenoitCoste/actions/workflows/ci-release.yml/badge.svg)](https://github.com/grostim/BenoitCoste/actions/workflows/ci-release.yml)
[![Dernière version](https://img.shields.io/github/v/release/grostim/BenoitCoste?label=Version&color=blue)](https://github.com/grostim/BenoitCoste/releases/latest)

Projet de transcription intégrale, d'édition critique et de mise en page sous **LaTeX** des mémoires manuscrites et dactylographiées de **Benoît Coste** (1781–1845), négociant et notable lyonnais, témoin privilégié de la Révolution française, du Siège de Lyon (1793), du Concordat, de l'Empire et de la Restauration.

---

## 📥 Téléchargements (Dernière version à jour)

Les documents sont automatiquement compilés et mis à disposition dans les trois formats suivants à chaque mise à jour :

| Format | Description | Lien de téléchargement |
| :--- | :--- | :---: |
| 📕 **PDF** | Version paginée officielle (mise en page typographique LaTeX) | [**Télécharger le PDF**](https://github.com/grostim/BenoitCoste/releases/latest/download/Memoires_de_Benoit_Coste.pdf) |
| 📱 **EPUB** | Version numérique adaptée aux liseuses, tablettes et smartphones | [**Télécharger l'EPUB**](https://github.com/grostim/BenoitCoste/releases/latest/download/Memoires_de_Benoit_Coste.epub) |
| 📄 **Markdown** | Version texte structurée pour consultation et traitement textuel | [**Télécharger le Markdown**](https://github.com/grostim/BenoitCoste/releases/latest/download/Memoires_de_Benoit_Coste.md) |

*(Vous pouvez également retrouver l'historique complet des versions sur la page des [Releases GitHub](https://github.com/grostim/BenoitCoste/releases)).*

---

## 📖 Présentation des Mémoires

Benoît Coste (1781–1845), fils d'Isaac Coste et de Jeanne Jordan, livre dans cet ouvrage un témoignage de premier plan sur l'histoire civile et religieuse de Lyon et de la France :
- **Enfance et jeunesse (1781–1800)** : éducation, costume d'époque, la vie sous l'Ancien Régime.
- **La Révolution et le Siège de Lyon (1793)** : la Terreur, le siège, l'évasion providentielle de son père.
- **L'exil et le retour** : séjours en Suisse (Constance, Noefels), la situation religieuse en France.
- **Le Concordat et le rétablissement du culte** : réouverture des églises (St Jean, St Pierre, Fourvière), visite du Pape Pie VII à Lyon.
- **L'Empire et les Cent-Jours** : persécutions napoléoniennes, arrestation et captivité de l'auteur en 1815.
- **La Restauration et la vie militaire / civique** : événements politiques et familiaux jusqu'au milieu du XIXᵉ siècle.

---

## 🗂 Structure du Dépôt

```
BenoitCoste/
├── .github/
│   └── workflows/
│       └── ci-release.yml          # Pipeline CI/CD (compilation LaTeX, génération multi-format & release)
├── Originaux/                      # Scans haute fidélité des fascicules originaux (Ch 1 à Ch 38)
│   ├── Ch 1.pdf
│   ├── ...
│   └── Ch 38.pdf
├── Memoires de Benoit Coste.tex   # Source LaTeX principal du document
├── CONVENTIONS_TRANSCRIPTION.md    # Guide des conventions éditoriales et typographiques
├── README.md                       # Présentation du projet et liens de téléchargement
└── .gitignore                      # Exclusion des fichiers temporaires LaTeX
```

---

## 🛠 Conventions et Principes d'Édition

1. **Fidélité au texte et corrections manuscrites** : La transcription intègre le texte final en tenant compte de toutes les ratures et ajouts manuscrits portés sur le tapuscrit.
2. **Mentions marginales** : Transcrites sous forme de sous-titres non numérotés (`\section*{...}`).
3. **Notes de bas de page** : Scrupuleusement conservées via `\footnote{...}`.
4. **Commits conventionnels en français** : Chaque transcription de chapitre ou correction fait l'objet d'un commit unitaire (`feat: ...`, `fix: ...`, `docs: ...`).
5. **Gestion automatisée des releases** :
   - Ajout d'un nouveau chapitre $\rightarrow$ **Release majeure** (`v21.0.0`, etc.).
   - Correction de coquille ou ajustement de mise en page $\rightarrow$ **Release mineure** (`v20.1.0`, etc.).

Pour le détail complet des règles typographiques et éditoriales, consultez le fichier [`CONVENTIONS_TRANSCRIPTION.md`](./CONVENTIONS_TRANSCRIPTION.md).
