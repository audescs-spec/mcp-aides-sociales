# Serveur MCP - Aides sociales françaises

[![audescs-spec/mcp-aides-sociales MCP server](https://glama.ai/mcp/servers/audescs-spec/mcp-aides-sociales/badges/score.svg)](https://glama.ai/mcp/servers/audescs-spec/mcp-aides-sociales)
[![AllMCPs Verified](https://allmcps.com/api/badge/aides-sociales-francaises)](https://allmcps.com/mcp/aides-sociales-francaises?verify=1a9248c2-44e0-4bb7-9063-c725047e0c0a)
[![smithery badge](https://smithery.ai/badge/aude-scs/mcp-aides-sociales)](https://smithery.ai/servers/aude-scs/mcp-aides-sociales)
[![MCP Badge](https://lobehub.com/badge/mcp/audescs-spec-mcp-aides-sociales)](https://lobehub.com/mcp/audescs-spec-mcp-aides-sociales)

Ce service est une **API/MCP pensée pour les développeurs et les agents
IA qui l'intègrent** dans leurs propres logiciels — pas un simulateur
grand public à usage isolé. Elle calcule le **RSA**, la **prime
d'activité** et l'**aide au logement (APL/ALS/ALF)** pour un foyer
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

## Adresse du serveur et accès

```
https://mcp-aides-sociales.onrender.com/mcp
```

Ce service est protégé par une **clé d'accès (API key)** : chaque appel
doit la fournir, sinon le serveur refuse de répondre. L'accès est un
abonnement à **29 €/mois**, souscrit ici :
**[https://buy.stripe.com/9B628q5Pb7t9a0QdurgEg01](https://buy.stripe.com/9B628q5Pb7t9a0QdurgEg01)**.
Après paiement, une clé d'accès personnelle est envoyée automatiquement
par email (et renouvelée à chaque paiement mensuel réussi).

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

> « J'habite seul(e) à Paris, je gagne 900 euros nets par mois (environ
> 1150 euros bruts), je paie 500 euros de loyer et je n'ai pas d'enfant.
> Est-ce que j'ai droit au RSA, à la prime d'activité, et à l'APL, et
> pour quel montant ? »

L'assistant utilisera automatiquement les outils `calculer_aides_sociales`
et `calculer_apl` et répondra avec les montants mensuels estimés.

## Note technique : premier appel parfois lent

Le serveur est hébergé sur un plan gratuit. S'il n'a pas été utilisé
depuis un moment, il peut mettre 30 à 60 secondes à répondre à la toute
première question (le temps de "se réveiller"). Les questions suivantes
sont ensuite rapides.

## Les outils exposés

### `calculer_aides_sociales` (RSA + prime d'activité)

Paramètres :

- `salaire_net_mensuel` (nombre) : salaire net mensuel du demandeur, en euros.
- `loyer_mensuel` (nombre) : loyer mensuel du foyer, en euros.
- `statut_occupation_logement` (texte) : un parmi `proprietaire`,
  `primo_accedant`, `locataire_hlm`, `locataire_vide`, `locataire_meuble`,
  `loge_gratuitement`, `locataire_foyer`, `sans_domicile`.
- `nombre_enfants` (entier) : nombre d'enfants à charge.
- `en_couple` (vrai/faux).
- `salaire_net_mensuel_conjoint` (nombre, optionnel) : à fournir si `en_couple` est vrai.
- `code_insee_commune` (texte, optionnel) : code INSEE (depcom) de la
  commune, 5 caractères (ex: `75056` pour Paris). Affine une vérification
  interne au calcul du forfait logement du RSA (zone APL). En son
  absence, la zone 2 est utilisée par défaut pour cette vérification
  uniquement — cela ne change généralement pas le RSA/la prime
  d'activité renvoyés (voir *Le forfait logement du RSA* ci-dessous).

Retourne le mois de calcul, le RSA mensuel estimé, la prime d'activité
mensuelle estimée, et les hypothèses retenues pour le calcul.

### `calculer_apl` (aide au logement : APL, ALS ou ALF selon éligibilité)

Paramètres :

- `salaire_brut_mensuel` (nombre) : salaire **brut** mensuel du demandeur
  (avant cotisations, en haut du bulletin de paie) — **pas** le salaire
  net utilisé par `calculer_aides_sociales`. Nécessaire pour qu'openfisca-france
  recalcule correctement, via son propre moteur de paie, le revenu
  imposable utilisé dans la base ressources "temps réel" de l'aide au
  logement (réforme 2021).
- `loyer_mensuel` (nombre) : loyer réellement payé, hors charges. En cas
  de colocation, indiquer uniquement la part personnelle.
- `code_insee_commune` (texte, **obligatoire pour cet outil**) : code
  INSEE de la commune, 5 caractères — pas le code postal. La zone APL en
  est déduite automatiquement (fichier de zonage embarqué dans
  openfisca-france, 37 000+ communes, aucun appel réseau). Un code
  inconnu est rejeté explicitement plutôt que de retomber sur une zone
  par défaut.
- `statut_occupation_logement` (texte) : `proprietaire`, `locataire_hlm`,
  `locataire_vide`, `locataire_meuble`, `loge_gratuitement`,
  `sans_domicile` sont calculés (les 3 derniers donnent légitimement
  0 €, non-éligibilité réelle). `primo_accedant` et `locataire_foyer`
  sont **hors périmètre** : l'outil renvoie une erreur explicite plutôt
  qu'un montant approximatif (voir *Ce que `calculer_apl` ne couvre
  pas*).
- `nombre_enfants`, `en_couple`, `salaire_brut_mensuel_conjoint` :
  identiques en principe à `calculer_aides_sociales` (mais en brut).
- `en_colocation` (vrai/faux, optionnel, défaut faux) : applique le
  plafond de loyer réduit prévu pour les colocataires.

Retourne le mois de calcul, l'aide au logement mensuelle estimée, le
dispositif applicable (APL, ALS ou ALF), les hypothèses de calcul, et un
descriptif explicite de ce que le calcul couvre ou non.

#### Ce que `calculer_apl` ne couvre pas

- **Accession à la propriété avec prêt en cours** (`primo_accedant`) :
  dépend de la date exacte du prêt, non collectée ici, et n'est presque
  plus ouvert aux nouveaux prêts depuis 2018.
- **Logement-foyer / résidence universitaire ou CROUS**
  (`locataire_foyer`) : openfisca-france marque lui-même ce statut
  "non calculable" par la formule standard.
- **Revenus non salariés** : indépendants, chômage indemnisé, retraite,
  pension d'invalidité, revenus du patrimoine ne sont pas modélisés —
  seul un revenu salarié stable est pris en compte.
- Personnes âgées/handicapées hébergées à titre onéreux, chambres
  meublées spécifiquement.

### Le forfait logement du RSA (pourquoi RSA et APL s'additionnent)

Le RSA renvoyé par `calculer_aides_sociales` intègre déjà un **forfait
logement** : une déduction forfaitaire **fixe**, prévue par la loi
(environ 12 % du montant de base du RSA pour une personne seule),
appliquée dès que le foyer est logé (loyer payé, logé gratuitement, ou
propriétaire). **Ce n'est pas une estimation du montant réel d'aide au
logement** — c'est un taux légal indépendant, donc le RSA renvoyé ici et
le montant renvoyé par `calculer_apl` peuvent bien être additionnés :
un allocataire perçoit réellement le RSA (déjà minoré de ce forfait
fixe) **plus** son APL/ALS/ALF entière.

## Faire tourner ce serveur soi-même (en local)

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
API_KEY=une-cle-secrete-a-vous python src/server.py
```

Le serveur écoute en HTTP sur le port défini par la variable
d'environnement `PORT` (8000 par défaut), sur le chemin `/mcp`.

## Comment fonctionne la clé d'accès

Le serveur ne stocke jamais la clé en clair : le code contient uniquement
son **empreinte SHA-256** (un hachage à sens unique, impossible à inverser).
Une clé fournie par un client n'est acceptée que si son empreinte
correspond. Cela permet au service de fonctionner "prêt à l'emploi" sans
configurer de variable d'environnement chez l'hébergeur (utile quand,
comme sur Render en mode "Blueprint managed", il n'est pas toujours
possible d'ajouter une variable depuis le tableau de bord).

Pour remplacer la clé sans changer le code (par exemple en local, ou chez
un hébergeur qui permet les variables d'environnement) :

- `API_KEY=votre-cle python src/server.py` (la clé en clair est hachée au démarrage), ou
- `API_KEY_SHA256=votre-empreinte python src/server.py` (empreinte déjà calculée).

Pour changer définitivement la clé par défaut : calculez l'empreinte
SHA-256 de la nouvelle clé et remplacez la constante
`_EMPREINTE_CLE_API_PAR_DEFAUT` dans `src/server.py`.

## Protections en place

- **Clé d'accès obligatoire** (voir ci-dessus) sur tous les appels de calcul.
- **Validation stricte des données reçues** (montants, nombre d'enfants,
  types) : toute requête malformée ou avec des valeurs absurdes est
  rejetée proprement, sans jamais faire planter le serveur.
- **Limitation du nombre de requêtes par adresse IP** (au-delà d'un
  certain nombre d'appels par minute, le serveur répond "trop de
  requêtes" au lieu de traiter la demande), pour éviter qu'un usage
  répété abusif ne surcharge ce service hébergé sur un plan gratuit.

## Déploiement

- `render.yaml` : configuration prête pour un déploiement sur
  [Render.com](https://render.com) (type "Blueprint").
- `nixpacks.toml` / `Procfile` : configuration prête pour
  [Railway.app](https://railway.app).

## Paiement Stripe et envoi automatique de la clé (pour les mainteneurs)

Le service peut être vendu via un Stripe Payment Link. Un webhook
(`POST /webhook/stripe`, non protégé par la clé d'accès) écoute
deux événements :

- `checkout.session.completed` (mode paiement unique uniquement) : cas
  historique de l'ancien Payment Link one_time, aujourd'hui désactivé.
  Génère une clé d'accès **à vie**, dérivée par HMAC-SHA256 de
  l'identifiant de session Stripe et d'un secret serveur.
- `invoice.paid` (abonnement mensuel, cas actuel) : à chaque paiement
  d'abonnement réussi (initial ou renouvellement), génère une clé
  dérivée de l'identifiant d'abonnement Stripe et **expirant à la fin de
  la période facturée** (+ 3 jours de marge). Si l'abonnement est annulé
  ou qu'un paiement échoue, la dernière clé envoyée cesse simplement de
  fonctionner à son expiration — pas besoin de liste de révocation.

Dans les deux cas, aucune base de données : la clé se vérifie par
recalcul de sa signature HMAC, pas par recherche dans un stockage (le
disque gratuit de Render n'est pas persistant entre redémarrages).
L'envoi se fait par email via [Resend](https://resend.com).

Variables d'environnement à définir côté hébergeur (en plus de
`API_KEY` / `API_KEY_SHA256`, voir plus haut) :

- `STRIPE_WEBHOOK_SECRET` : secret de signature du endpoint webhook
  (`whsec_...`), fourni par Stripe à la création du webhook.
- `API_KEY_PEPPER` : secret aléatoire propre au serveur, utilisé pour
  dériver et vérifier les clés générées par client. À générer une seule
  fois et ne jamais changer (sinon les clés déjà envoyées deviennent
  invalides).
- `RESEND_API_KEY` : clé API [Resend](https://resend.com) utilisée pour
  l'envoi des emails.
- `RESEND_FROM_EMAIL` (optionnel) : adresse d'expédition. Par défaut
  `onboarding@resend.dev`, qui **ne peut envoyer qu'à l'adresse du
  compte Resend lui-même** tant qu'aucun domaine n'est vérifié. En
  production, utilise une adresse sur un domaine vérifié (ex:
  `hello@kapsik.com`, vérifié DKIM/SPF/MX sur Resend).

Filet de sécurité : chaque clé générée est aussi journalisée dans les
logs du serveur (`[paiement] nouvelle cle generee ...`), pour pouvoir la
retrouver et la renvoyer manuellement si l'email échoue.
