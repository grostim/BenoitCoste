# Mes souvenirs de soixante ans — Benoît Coste (1781–1845)

[![Validation LaTeX & Publication](https://github.com/grostim/BenoitCoste/actions/workflows/ci-release.yml/badge.svg)](https://github.com/grostim/BenoitCoste/actions/workflows/ci-release.yml)
[![Dernière version](https://img.shields.io/github/v/release/grostim/BenoitCoste?label=Version&color=blue)](https://github.com/grostim/BenoitCoste/releases/latest)

Projet de transcription intégrale, d'édition critique et de mise en page sous **LaTeX** de l'ouvrage <u>« Mes souvenirs de soixante ans »</u>, mémoires manuscrites et dactylographiées de **Benoît Coste** (1781–1845), négociant et notable lyonnais, témoin privilégié de la Révolution française, du Siège de Lyon (1793), du Concordat, de l'Empire et de la Restauration.

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

## 🌳 Annexe généalogique

Une annexe distincte du manuscrit présente la généalogie de Benoît Coste et
Joséphine Colomb de Gast. Elle est explicitement signalée dans le PDF comme
**« Note généalogique — hors document original »** et n'altère pas le
contenu des trente-huit chapitres transcrits.

Le pipeline local produit un éventail de deux générations ascendantes et d'une
génération descendante, avec portraits soumis au mode
`publication_safe`, ainsi qu'un graphe séparé des collatéraux cités. Les
personnes repérées dans l'ouvrage sont identifiées par le tag Gramps exact
`Cité dans les Mémoires de Benoît Coste` ; le signal combine forme et couleur
pour rester lisible en niveaux de gris.

La procédure complète est documentée dans [`genealogie/README.md`](./genealogie/README.md).
Le test hors ligne, sans réseau ni données privées, peut être lancé ainsi :

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/update_genealogy.py \
  --config genealogie/report.toml \
  --fixture tests/fixtures/genealogy_fixture.json \
  --dry-run
```

Les régénérations live sont réservées à l'environnement local ; aucun accès
GrampsWeb ni credential n'est utilisé par la CI publique.

---

## 📖 Présentation des Mémoires

Benoît Coste (1781–1845), fils d'Isaac Coste et de Jeanne Jordan, livre dans cet ouvrage un témoignage de premier plan sur l'histoire civile et religieuse de Lyon et de la France :
- **Enfance et jeunesse (1781–1800)** : éducation, costume d'époque, la vie sous l'Ancien Régime.
- **La Révolution et le Siège de Lyon (1793)** : la Terreur, le siège, l'évasion providentielle de son père.
- **L'exil et le retour** : séjours en Suisse (Constance, Noefels), la situation religieuse en France.
- **Le Concordat et le rétablissement du culte** : réouverture des églises (St Jean, St Pierre, Fourvière), visite du Pape Pie VII à Lyon.
- **L'Empire et les Cent-Jours** : persécutions napoléoniennes, arrestation et captivité de l'auteur en 1815.
- **La Restauration et la vie militaire / civique** : événements politiques et civiques, rétablissement des confréries et processions, souvenirs jusqu'au milieu du XIXᵉ siècle.

---

## 📊 État d'avancement de la transcription

- **Chapitres transcrits** : **38 / 38** (intégralité de l'ouvrage transcrite, du Chapitre 1 au Chapitre 38 inclus).
- **Dernier chapitre ajouté** : **Chapitre 38** (*Conclusion*).
- **Statut** : ✅ **Transcription complète de l'ouvrage** (*Mémoires de Benoît Coste*).

Consultez le tableau détaillé dans [`CONVENTIONS_TRANSCRIPTION.md`](./CONVENTIONS_TRANSCRIPTION.md#5-état-davancement-de-la-transcription).

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
├── genealogie/                     # Chapitre et configuration de régénération
├── scripts/                        # Audit, génération et contrôles public-safe
├── tests/                          # Fixtures et tests offline
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
