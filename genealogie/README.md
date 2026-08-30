# Annexe généalogique

Cette arborescence contient le chapitre généalogique séparé du manuscrit
original. Le texte imprimé se trouve dans `chapitre.tex` et est inclus à la
fin de `Memoires de Benoit Coste.tex`.

## Source et périmètre

La régénération utilise le rapport Gramps `two_way_fan_chart` avec :

- la famille centrale `F0043` et la personne de référence `I0095` ;
- deux générations ascendantes et une génération descendante ;
- les portraits autorisés par `publication_safe` ;
- le tag exact `Cité dans les Mémoires de Benoît Coste` pour sélectionner les
  personnages de la galerie ;
- les marqueurs de tag désactivés dans l'éventail public ;
- les prénoms d'usage utilisés pour les descendants visibles.

Le tag est résolu par son nom dans Gramps et sert de source unique pour la
liste de la galerie. Aucun handle technique n'est codé dans le chapitre, le
fragment LaTeX ou les images publiques.

Pour chaque personne, la galerie lit uniquement les faits personnels dont la
référence d'événement est `Primary` : naissance, décès et professions. Un
baptême n'est jamais transformé en naissance ; une donnée absente est
indiquée comme non renseignée. Les relations sont résolues à partir des
familles, parents et conjoints présents dans Gramps. Si cette structure ne
suffit pas, le chapitre indique une relation non résolue plutôt que d'inventer
un rattachement.

## Galerie de portraits

`build_portrait_gallery.py` produit une page par personne taguée, dans l'ordre
de proximité avec Benoît Coste puis par nom. Chaque fiche contient :

- les prénoms complets, avec le prénom d'usage souligné, puis le NOM ;
- la relation avec Benoît Coste ;
- naissance et décès (date et lieu) ;
- profession(s) attestée(s) dans Gramps ;
- les portraits disponibles dans les médias Gramps.

Les médias sont retenus seulement lorsqu'ils sont explicitement décrits comme
portrait/photo et qu'ils sont réellement des images. Les actes, registres,
médailles, armoiries, annotations et documents sont exclus. Les rectangles de
recadrage Gramps sont appliqués avec une marge, puis les images sont converties
en JPEG sans métadonnées ; plusieurs portraits sont disposés en grille. Si une
personne référence le même média en version complète et avec un recadrage, la
version complète est conservée et le recadrage est ignoré. Une personne dont
la relation avec Benoît Coste reste non résolue est exclue lorsqu'elle n'a
aucun portrait. La mise en page est bornée à une page par personne.

## Régénération offline

Le test reproductible sans réseau ni données privées est :

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/update_genealogy.py \
  --config genealogie/report.toml \
  --fixture tests/fixtures/genealogy_fixture.json \
  --dry-run
```

Ce mode valide la configuration, le filtrage public, l'éventail, la galerie,
les recadrages, le fragment LaTeX et les conversions sans écrire dans
`genealogie/assets/`.

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
  dans le livre via `\\includepdf[fitpaper]` ;
- `arbre-benoit-coste-a4-1.*` à `a4-4.*` : vues vectorielles de détail,
  autonomes et non incluses dans le livre ;
- `galerie/galerie.tex` : fragment LaTeX généré ;
- `galerie/portraits/*.jpg` : portraits nettoyés et recadrés ;
- `manifest.json` : paramètres publics, statistiques galerie et empreintes
  SHA-256.

Le schéma relationnel des parentés citées a été retiré définitivement du
livre et du pipeline : il n'est plus généré, validé ni publié.

Les PDF et PNG doivent toujours être régénérés depuis les SVG validés. Ne
jamais retoucher manuellement un SVG, un portrait ou `galerie.tex` pour
corriger un nom, une date, une filiation ou une relation. Pour mettre la
galerie à jour, compléter Gramps avec le tag ou le média voulu, puis relancer
la commande live ci-dessus.
