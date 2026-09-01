# Serveur MCP - Aides sociales françaises

Ce service estime le **RSA** et la **prime d'activité** pour un foyer
français, à partir de quelques informations simples : salaire, loyer,
statut du logement, nombre d'enfants, situation de couple.

Le calcul est fait **entièrement en local**, avec la bibliothèque open
source [openfisca-france](https://github.com/openfisca/openfisca-france)
(le moteur officiel des barèmes sociaux français). Aucun appel n'est fait
à l'API publique `api.fr.openfisca.org` ni à un autre service externe.

⚠️ **Important : ce sont des estimations, pas des décisions officielles.**
Le calcul repose sur des hypothèses simplificatrices (âge des adultes
supposé, situation stable sur les derniers mois, etc.). Seule la CAF ou
la MSA peut donner un montant définitif et exact.

## Adresse du serveur

```
https://mcp-aides-sociales.onrender.com/mcp
```

Ce service est protégé par une **clé d'accès (API key)**. Chaque appel
doit fournir cette clé, sinon le serveur refuse de répondre. La clé vous
a été communiquée séparément (elle ne figure pas dans ce dépôt, pour des
raisons de sécurité).

## Installer dans Claude Desktop

1. Ouvrez le fichier de configuration de Claude Desktop :
   - Sur Mac : `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Sur Windows : `%APPDATA%\Claude\claude_desktop_config.json`
2. Ajoutez (ou complétez) la section `mcpServers` ainsi :

```json
{
  "mcpServers": {
    "aides-sociales-france": {
      "url": "https://mcp-aides-sociales.onrender.com/mcp",
      "headers": {
        "X-API-Key": "VOTRE_CLE_API"
      }
    }
  }
}
```

3. Remplacez `VOTRE_CLE_API` par la clé qui vous a été transmise.
4. Redémarrez Claude Desktop.

## Installer dans Cursor

1. Ouvrez les réglages MCP de Cursor (Settings → MCP → Add new MCP server,
   ou le fichier `~/.cursor/mcp.json`).
2. Ajoutez la même configuration que ci-dessus :

```json
{
  "mcpServers": {
    "aides-sociales-france": {
      "url": "https://mcp-aides-sociales.onrender.com/mcp",
      "headers": {
        "X-API-Key": "VOTRE_CLE_API"
      }
    }
  }
}
```

3. Remplacez `VOTRE_CLE_API` par votre clé, puis rechargez Cursor.

## Exemple de question à poser une fois connecté

> « J'habite seul(e), je gagne 900 euros nets par mois, je paie 500 euros
> de loyer et je n'ai pas d'enfant. Est-ce que j'ai droit au RSA ou à la
> prime d'activité, et pour quel montant ? »

L'assistant utilisera automatiquement l'outil `calculer_aides_sociales`
et répondra avec les montants mensuels estimés.

## Note technique : premier appel parfois lent

Le serveur est hébergé sur un plan gratuit. S'il n'a pas été utilisé
depuis un moment, il peut mettre 30 à 60 secondes à répondre à la toute
première question (le temps de "se réveiller"). Les questions suivantes
sont ensuite rapides.

## L'outil exposé : `calculer_aides_sociales`

Paramètres :

- `salaire_net_mensuel` (nombre) : salaire net mensuel du demandeur, en euros.
- `loyer_mensuel` (nombre) : loyer mensuel du foyer, en euros.
- `statut_occupation_logement` (texte) : un parmi `proprietaire`,
  `primo_accedant`, `locataire_hlm`, `locataire_vide`, `locataire_meuble`,
  `loge_gratuitement`, `locataire_foyer`, `sans_domicile`.
- `nombre_enfants` (entier) : nombre d'enfants à charge.
- `en_couple` (vrai/faux).
- `salaire_net_mensuel_conjoint` (nombre, optionnel) : à fournir si `en_couple` est vrai.

Retourne le mois de calcul, le RSA mensuel estimé, la prime d'activité
mensuelle estimée, et les hypothèses retenues pour le calcul.

## Faire tourner ce serveur soi-même (en local)

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
API_KEY=une-cle-secrete-a-vous python src/server.py
```

Le serveur écoute en HTTP sur le port défini par la variable
d'environnement `PORT` (8000 par défaut), sur le chemin `/mcp`. La
variable d'environnement `API_KEY` est obligatoire : le serveur refuse de
démarrer si elle n'est pas définie.

## Déploiement

- `render.yaml` : configuration prête pour un déploiement sur
  [Render.com](https://render.com) (type "Blueprint"). La variable
  `API_KEY` y est déclarée avec `sync: false` : sa valeur n'est pas
  incluse dans ce fichier (raisons de sécurité) et doit être saisie une
  fois manuellement dans le tableau de bord Render, sur la page du
  service (elle reste éditable même si le service est "Blueprint
  managed").
- `nixpacks.toml` / `Procfile` : configuration prête pour
  [Railway.app](https://railway.app) (même remarque pour `API_KEY`).
