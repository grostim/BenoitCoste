# Annexe généalogique

Cette arborescence contient le chapitre généalogique séparé du manuscrit
original. Le texte imprimé se trouve dans `chapitre.tex` et est inclus à la
fin de `Memoires de Benoit Coste.tex`.

## Source et périmètre

La régénération locale utilise le rapport Gramps `two_way_fan_chart` avec :

- la famille centrale configurée dans `report.toml` ;
- deux générations ascendantes et une génération descendante ;
- les portraits autorisés par `publication_safe` ;
- le tag exact `Cité dans les Mémoires de Benoît Coste` pour le repérage des
  personnes citées ;
- un graphe relationnel séparé pour les collatéraux cités.

Le tag est résolu par son nom dans Gramps. Aucun handle technique n'est codé
dans le chapitre ou dans les dessins publics. Les six citations de `S2212`
qui ne permettent pas de remonter à une personne restent des cas d'audit et ne
sont pas rattachées automatiquement.

## Régénération offline

Le test reproductible sans réseau ni données privées est :

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/update_genealogy.py \
  --config genealogie/report.toml \
  --fixture tests/fixtures/genealogy_fixture.json \
  --dry-run
```

Ce mode valide la configuration, le filtrage public, le graphe, le SVG et les
conversions sans écrire dans `genealogie/assets/`.

## Régénération live, uniquement en local

Le rapport réel ne doit être lancé qu'avec l'addon qui expose l'option
`highlight_tag`. Les identifiants sont lus depuis l'environnement du processus
ou un fichier situé hors du dépôt :

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/update_genealogy.py \
  --config genealogie/report.toml \
  --env-file /home/sorg/CloudCLI/Homelab/.env
```

Le pipeline s'arrête si l'addon distant ne propose pas `highlight_tag`, si le
SVG contient une ressource externe ou si une information technique apparaît
dans la projection publique. Il ne faut pas utiliser
`--allow-missing-highlight` pour une publication.

Avant toute application du tag, exécuter `scripts/audit_s2212.py` en lecture
seule puis faire relire le manifeste d'approbation. Le script
`scripts/apply_cited_tag.py` refuse un manifeste sans
`approval.status = "approved"`, sauvegarde les objets complets hors dépôt et
vérifie chaque écriture par relecture. Les sauvegardes et manifestes de travail
restent sous `/tmp/` ou dans un autre emplacement externe.

## Artefacts

La sortie public-safe comprend :

- `arbre-benoit-coste.svg` : artefact canonique ;
- `arbre-benoit-coste.pdf` et `.png` : dérivés du SVG canonique ;
- `arbre-benoit-coste-a4-overview.*` : vue d'ensemble A4 paysage ;
- `arbre-benoit-coste-a4-1.*` à `a4-4.*` : vues vectorielles de détail ;
- `parente-citee.svg`, `.pdf` et `.png` : graphe des parentés collatérales ;
- `manifest.json` : dimensions, paramètres publics et empreintes SHA-256.

Le poster complet n'est pas réduit directement pour remplacer les vues de
lecture A4 : la vue d'ensemble sert au repérage et les panneaux de détail à la
lecture. Le graphe collatéral conserve les personnes intermédiaires nécessaires
au lien familial, mais masque leur identité lorsqu'elles sont privées.

Les PDF et PNG doivent toujours être régénérés depuis le SVG validé. Ne jamais
retoucher manuellement un SVG pour corriger un nom, une date, une filiation ou
un repère de citation.
