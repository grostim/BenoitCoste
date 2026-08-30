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
- les marqueurs de tag désactivés dans l'éventail public ;
- les prénoms d'usage utilisés pour les descendants visibles.

Le tag est résolu par son nom dans Gramps et sert uniquement au contrôle du
périmètre de publication. Aucun handle technique n'est codé dans le chapitre
ou dans les dessins publics. Les six citations de `S2212` qui ne permettent
pas de remonter à une personne restent des cas d'audit et ne sont pas
rattachées automatiquement.

## Régénération offline

Le test reproductible sans réseau ni données privées est :

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/update_genealogy.py \
  --config genealogie/report.toml \
  --fixture tests/fixtures/genealogy_fixture.json \
  --dry-run
```

Ce mode valide la configuration, le filtrage public, le SVG et les
conversions sans écrire dans `genealogie/assets/`.

## Régénération live, uniquement en local

Le rapport réel ne doit être lancé qu'avec l'addon qui expose les options
`highlight_tag` et `show_highlight_markers`. Les identifiants sont lus depuis
l'environnement du processus ou un fichier situé hors du dépôt :

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/update_genealogy.py \
  --config genealogie/report.toml \
  --env-file /home/sorg/CloudCLI/Homelab/.env
```

Le pipeline s'arrête si l'addon distant ne propose pas ces deux options, si le
SVG contient une ressource externe ou si une information technique apparaît
dans la projection publique. Il ne faut pas utiliser
`--allow-missing-highlight` pour une publication.

## Artefacts

La sortie public-safe comprend :

- `arbre-benoit-coste.svg` : artefact canonique ;
- `arbre-benoit-coste.pdf` et `.png` : dérivés du SVG canonique ;
- `arbre-benoit-coste-a4-overview.*` : vue A4 paysage insérée en pleine page
  dans le livre via `\includepdf[fitpaper]` ;
- `arbre-benoit-coste-a4-1.*` à `a4-4.*` : vues vectorielles de détail
  (artefacts autonomes, non inclus dans le livre) ;
- `manifest.json` : dimensions, paramètres publics et empreintes SHA-256.

Le schéma relationnel des parentés citées a été retiré définitivement du
livre et du pipeline : il n'est plus généré, validé ni publié.

Les PDF et PNG doivent toujours être régénérés depuis le SVG validé. Ne jamais
retoucher manuellement un SVG pour corriger un nom, une date, une filiation ou
un repère de citation.