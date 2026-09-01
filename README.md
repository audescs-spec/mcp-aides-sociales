# Serveur MCP - Aides sociales françaises

Serveur MCP (Model Context Protocol) qui estime le RSA et la prime
d'activité pour un foyer français.

Le calcul est fait **entièrement en local** avec la bibliothèque open source
[openfisca-france](https://github.com/openfisca/openfisca-france) (moteur
officiel des barèmes sociaux français). Aucun appel n'est fait à l'API
publique `api.fr.openfisca.org` ni à un autre service externe.

## Outil exposé

`calculer_aides_sociales` :

- `salaire_net_mensuel` (nombre) : salaire net mensuel du demandeur, en euros.
- `loyer_mensuel` (nombre) : loyer mensuel du foyer, en euros.
- `statut_occupation_logement` (texte) : un parmi `proprietaire`,
  `primo_accedant`, `locataire_hlm`, `locataire_vide`, `locataire_meuble`,
  `loge_gratuitement`, `locataire_foyer`, `sans_domicile`.
- `nombre_enfants` (entier) : nombre d'enfants à charge.
- `en_couple` (vrai/faux).
- `salaire_net_mensuel_conjoint` (nombre, optionnel).

Retourne une estimation du RSA et de la prime d'activité mensuels.

⚠️ Ceci est une **estimation**, pas une décision officielle. Seule la
CAF/MSA peut donner un montant définitif.

## Lancer en local

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/server.py
```

Le serveur écoute en HTTP sur le port défini par la variable
d'environnement `PORT` (8000 par défaut), sur le chemin `/mcp`.

## Déploiement

- `render.yaml` : configuration prête pour un déploiement sur
  [Render.com](https://render.com) (type "Blueprint").
- `nixpacks.toml` / `Procfile` : configuration prête pour
  [Railway.app](https://railway.app).
