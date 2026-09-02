"""Serveur MCP exposant le calcul du RSA et de la prime d'activite.

Le calcul est fait entierement en local avec openfisca-france (voir calcul.py),
sans aucun appel a l'API publique api.fr.openfisca.org ni a un autre service
externe.

Lancement:
    python src/server.py
Le serveur ecoute en HTTP (transport "streamable-http") sur le port defini
par la variable d'environnement PORT (8000 par defaut), accessible sur /mcp.
"""

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from collections import deque

from mcp.server.mcpserver import MCPServer

from calcul import calculer_rsa_prime_activite

# Empreinte SHA-256 de la cle d'acces par defaut du service (pas la cle en
# clair : impossible de retrouver la cle a partir de cette empreinte).
# Sert de secours si aucune variable d'environnement n'est fournie par
# l'hebergeur (utile sur Render en mode "Blueprint managed", ou l'onglet
# Environment n'est pas toujours disponible pour ajouter une variable).
_EMPREINTE_CLE_API_PAR_DEFAUT = (
    "5a4271cb5924d0a7de20eefed2979c4a5994c810de0faeab291576ca5af39d08"
)

server = MCPServer(
    name="aides-sociales-france",
    instructions=(
        "Calcule une ESTIMATION du RSA et de la prime d'activite pour un foyer "
        "francais, avec le moteur de calcul local openfisca-france (pas d'appel "
        "reseau externe). Ceci n'est pas une decision officielle: seule la CAF/MSA "
        "peut donner un montant definitif."
    ),
)


@server.tool()
def calculer_aides_sociales(
    salaire_net_mensuel: float,
    loyer_mensuel: float,
    statut_occupation_logement: str,
    nombre_enfants: int,
    en_couple: bool,
    salaire_net_mensuel_conjoint: float | None = None,
) -> dict:
    """Estime le RSA et la prime d'activite mensuels pour un foyer francais.

    Calcul 100% local via openfisca-france (aucun appel reseau externe).

    Args:
        salaire_net_mensuel: Salaire net mensuel du demandeur, en euros (0 si sans emploi).
        loyer_mensuel: Loyer mensuel paye par le foyer, en euros (0 si proprietaire sans loyer).
        statut_occupation_logement: Statut du logement. Valeurs possibles: "proprietaire",
            "primo_accedant", "locataire_hlm", "locataire_vide", "locataire_meuble",
            "loge_gratuitement", "locataire_foyer", "sans_domicile".
        nombre_enfants: Nombre d'enfants a charge dans le foyer.
        en_couple: True si le demandeur vit en couple (marie, pacse ou concubin), False sinon.
        salaire_net_mensuel_conjoint: Salaire net mensuel du conjoint, en euros. A fournir
            uniquement si en_couple est True (0 ou absent si le conjoint n'a pas de revenu).

    Returns:
        Un dictionnaire avec le mois de calcul, le RSA mensuel estime, la prime d'activite
        mensuelle estimee, et les hypotheses de calcul retenues.
    """
    try:
        return calculer_rsa_prime_activite(
            salaire_net_mensuel=salaire_net_mensuel,
            loyer_mensuel=loyer_mensuel,
            statut_occupation_logement=statut_occupation_logement,
            nombre_enfants=nombre_enfants,
            en_couple=en_couple,
            salaire_net_mensuel_conjoint=salaire_net_mensuel_conjoint,
        )
    except ValueError as erreur:
        return {"erreur": str(erreur)}
    except Exception:
        # Filet de securite: une erreur inattendue (bug, cas limite non
        # prevu dans openfisca-france...) ne doit jamais faire planter le
        # serveur ni exposer de details internes au client.
        return {"erreur": "Une erreur inattendue est survenue lors du calcul."}


async def _accueil(request):
    from starlette.responses import PlainTextResponse

    return PlainTextResponse(
        "Serveur MCP 'aides-sociales-france' en ligne. Point d'entree MCP: /mcp"
    )


def _generer_cle_client(session_id: str, pepper: str) -> str:
    """Derive une cle d'acces propre a un paiement Stripe, sans base de donnees.

    La cle encode l'identifiant de session Stripe et une signature HMAC-SHA256
    calculee avec un secret (pepper) connu seulement du serveur. La verification
    se fait par recalcul de la signature (voir _verifier_cle_client), pas par
    recherche dans un stockage: le disque gratuit de Render n'est pas persistant
    entre redemarrages.
    """
    signature = hmac.new(pepper.encode(), session_id.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{session_id}.{signature}"


def _verifier_cle_client(cle: str, pepper: str) -> bool:
    session_id, separateur, signature = cle.rpartition(".")
    if not separateur or not session_id or not signature:
        return False
    signature_attendue = hmac.new(pepper.encode(), session_id.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(signature, signature_attendue)


# Marge accordee apres la fin de periode facturee par Stripe (invoice.period_end),
# pour absorber un leger retard de traitement du webhook ou de nouvelle facture.
_MARGE_EXPIRATION_ABONNEMENT_SECONDES = 3 * 24 * 3600


def _generer_cle_abonnement(subscription_id: str, expiration_unix: int, pepper: str) -> str:
    """Derive une cle d'acces pour un abonnement, avec expiration integree.

    Contrairement a _generer_cle_client (acces a vie, pour un paiement unique),
    cette cle expire naturellement a la date encodee: pas besoin de liste de
    revocation si l'abonnement est annule ou qu'un paiement echoue, le serveur
    reste sans base de donnees.
    """
    message = f"{subscription_id}.{expiration_unix}"
    signature = hmac.new(pepper.encode(), message.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{message}.{signature}"


def _verifier_cle_abonnement(cle: str, pepper: str) -> bool:
    parties = cle.split(".")
    if len(parties) != 3:
        return False
    subscription_id, expiration_str, signature = parties
    if not subscription_id or not expiration_str or not signature:
        return False
    message = f"{subscription_id}.{expiration_str}"
    signature_attendue = hmac.new(pepper.encode(), message.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(signature, signature_attendue):
        return False
    try:
        return time.time() <= int(expiration_str)
    except ValueError:
        return False


def _verifier_signature_stripe(
    payload: bytes, en_tete_signature: str, secret: str, tolerance_secondes: int = 300
) -> bool:
    """Verifie une signature de webhook Stripe (algorithme documente par Stripe),
    sans dependre du SDK officiel `stripe`."""
    if not en_tete_signature:
        return False
    elements = dict(p.split("=", 1) for p in en_tete_signature.split(",") if "=" in p)
    timestamp = elements.get("t")
    signature_v1 = elements.get("v1")
    if not timestamp or not signature_v1:
        return False
    payload_signe = f"{timestamp}.".encode() + payload
    signature_attendue = hmac.new(secret.encode(), payload_signe, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature_attendue, signature_v1):
        return False
    try:
        return abs(time.time() - int(timestamp)) <= tolerance_secondes
    except ValueError:
        return False


def _envoyer_email_cle(destinataire: str, cle_api: str, expiration_unix: int | None = None) -> bool:
    """Envoie la cle d'acces generee au client par email via Resend.

    Retourne True si Resend a accepte l'envoi. Ne leve jamais d'exception:
    un email non envoye ne doit pas faire echouer le traitement du webhook
    (Stripe reessaierait indefiniment). La cle est aussi journalisee (voir
    l'appelant) comme filet de securite manuel en cas d'echec d'envoi.

    Si expiration_unix est fourni (abonnement), la date de validite est
    mentionnee dans l'email.
    """
    cle_resend = os.environ.get("RESEND_API_KEY")
    if not cle_resend:
        return False
    expediteur = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if expiration_unix is not None:
        import datetime

        date_expiration = datetime.datetime.fromtimestamp(
            expiration_unix, tz=datetime.timezone.utc
        ).strftime("%d/%m/%Y")
        ligne_expiration = (
            f"<p>Cette cle est valable jusqu'au <strong>{date_expiration}</strong> et sera "
            "automatiquement renouvelee (nouvelle cle envoyee par email) a chaque paiement "
            "mensuel reussi de votre abonnement.</p>"
        )
    else:
        ligne_expiration = ""

    corps_html = (
        "<p>Merci pour votre achat.</p>"
        "<p>Voici votre cle d'acces personnelle au serveur MCP "
        "<strong>aides-sociales-france</strong> :</p>"
        f"<p><code>{cle_api}</code></p>"
        f"{ligne_expiration}"
        "<p>Ajoutez-la comme en-tete <code>X-API-Key</code> (ou "
        "<code>Authorization: Bearer &lt;cle&gt;</code>) dans la configuration "
        "de votre client MCP (Claude Desktop, Cursor...). Voir le README du depot "
        "pour un exemple complet.</p>"
    )
    donnees = json.dumps(
        {
            "from": expediteur,
            "to": [destinataire],
            "subject": "Votre cle d'acces - aides-sociales-france",
            "html": corps_html,
        }
    ).encode()

    requete = urllib.request.Request(
        "https://api.resend.com/emails",
        data=donnees,
        headers={
            "Authorization": f"Bearer {cle_resend}",
            "Content-Type": "application/json",
            # Sans ceci, urllib envoie "Python-urllib/x.y" par defaut, que le
            # WAF Cloudflare devant l'API Resend bloque (403, "error code:
            # 1010") en le prenant pour un signal de bot.
            "User-Agent": "DroitSocial-API/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return 200 <= reponse.status < 300
    except urllib.error.HTTPError as erreur:
        print(f"[paiement] echec envoi email Resend ({erreur.code}): {erreur.read().decode(errors='ignore')}")
        return False
    except Exception as erreur:  # reseau indisponible, timeout...
        print(f"[paiement] echec envoi email Resend: {erreur}")
        return False


async def _webhook_stripe(request):
    """Recoit les evenements Stripe.

    - checkout.session.completed en mode paiement unique: genere une cle
      d'acces a vie (cas historique, ancien Payment Link one_time).
    - checkout.session.completed en mode abonnement: ignore, gere par
      invoice.paid ci-dessous (evite d'envoyer deux emails differents pour
      le meme premier paiement).
    - invoice.paid: a chaque paiement d'abonnement reussi (initial ou
      renouvellement), genere une cle expirant a la fin de la periode
      facturee (+ marge) et l'envoie par email.
    """
    from starlette.responses import JSONResponse

    secret_webhook = os.environ.get("STRIPE_WEBHOOK_SECRET")
    pepper = os.environ.get("API_KEY_PEPPER")
    if not secret_webhook or not pepper:
        return JSONResponse({"erreur": "Webhook non configure"}, status_code=500)

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    if not _verifier_signature_stripe(payload, signature, secret_webhook):
        return JSONResponse({"erreur": "Signature invalide"}, status_code=400)

    evenement = json.loads(payload)
    type_evenement = evenement.get("type")

    if type_evenement == "checkout.session.completed":
        session = evenement.get("data", {}).get("object", {})
        if session.get("mode") == "subscription":
            return JSONResponse({"recu": True})

        session_id = session.get("id")
        email_client = (session.get("customer_details") or {}).get("email")

        if session_id and email_client:
            cle_client = _generer_cle_client(session_id, pepper)
            # Filet de securite: toujours visible dans les logs Render, meme
            # si l'envoi d'email echoue (ex: domaine non verifie sur Resend).
            print(f"[paiement] nouvelle cle generee (a vie) - session={session_id} email={email_client} cle={cle_client}")
            _envoyer_email_cle(email_client, cle_client)

    elif type_evenement == "invoice.paid":
        invoice = evenement.get("data", {}).get("object", {})
        subscription_id = invoice.get("subscription")
        email_client = invoice.get("customer_email")
        periode_fin = invoice.get("period_end")

        if subscription_id and email_client and periode_fin:
            expiration = int(periode_fin) + _MARGE_EXPIRATION_ABONNEMENT_SECONDES
            cle_client = _generer_cle_abonnement(subscription_id, expiration, pepper)
            print(
                f"[paiement] nouvelle cle generee (abonnement) - subscription={subscription_id} "
                f"email={email_client} expiration={expiration} cle={cle_client}"
            )
            _envoyer_email_cle(email_client, cle_client, expiration_unix=expiration)

    return JSONResponse({"recu": True})


class _AuthentificationParCle:
    """Exige une cle d'acces (API key) sur toutes les routes sauf la page d'accueil "/".

    La cle fournie par le client (en-tete "X-API-Key", ou "Authorization:
    Bearer <cle>") est hachee en SHA-256 puis comparee a l'empreinte
    attendue. La cle en clair n'est jamais stockee ni comparee directement,
    ce qui permet de garder l'empreinte dans le code source sans risque.
    """

    _CHEMINS_PUBLICS = ("/", "/webhook/stripe")

    def __init__(self, app, empreinte_attendue: str, pepper: str | None = None) -> None:
        self._app = app
        self._empreinte_attendue = empreinte_attendue
        self._pepper = pepper

    async def __call__(self, scope, receive, send):
        from starlette.responses import PlainTextResponse

        if scope["type"] != "http" or scope["path"] in self._CHEMINS_PUBLICS:
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        cle_fournie = headers.get(b"x-api-key", b"").decode()
        if not cle_fournie:
            auth = headers.get(b"authorization", b"").decode()
            if auth.lower().startswith("bearer "):
                cle_fournie = auth[7:].strip()

        empreinte_fournie = hashlib.sha256(cle_fournie.encode()).hexdigest()
        cle_valide = bool(cle_fournie) and hmac.compare_digest(empreinte_fournie, self._empreinte_attendue)
        if not cle_valide and cle_fournie and self._pepper:
            # Cle d'abonnement (3 parties: subscription_id.expiration.signature)
            # ou cle a vie issue d'un paiement unique (2 parties).
            if cle_fournie.count(".") == 2:
                cle_valide = _verifier_cle_abonnement(cle_fournie, self._pepper)
            else:
                cle_valide = _verifier_cle_client(cle_fournie, self._pepper)

        if not cle_valide:
            response = PlainTextResponse(
                "Cle d'acces manquante ou invalide. Fournissez l'en-tete "
                "'X-API-Key' ou 'Authorization: Bearer <cle>'.",
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)


class _LimitationDebit:
    """Limite le nombre de requetes par adresse IP.

    Protection simple contre un usage repete abusif (volontaire ou par
    erreur, par exemple un client qui boucle) sur ce service heberge sur un
    plan gratuit avec des ressources limitees. L'historique est garde en
    memoire du processus: suffisant tant qu'une seule instance du serveur
    tourne (cas du plan gratuit Render), mais ne serait pas partage entre
    plusieurs instances si on passait a un plan avec plusieurs machines.
    """

    def __init__(self, app, max_requetes: int = 30, fenetre_secondes: float = 60.0) -> None:
        self._app = app
        self._max_requetes = max_requetes
        self._fenetre = fenetre_secondes
        self._historique: dict[str, deque] = {}

    def _ip_client(self, scope) -> str:
        headers = dict(scope.get("headers") or [])
        cf_ip = headers.get(b"cf-connecting-ip")
        if cf_ip:
            return cf_ip.decode()
        xff = headers.get(b"x-forwarded-for")
        if xff:
            return xff.decode().split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "inconnu"

    async def __call__(self, scope, receive, send):
        import time

        from starlette.responses import PlainTextResponse

        if scope["type"] != "http" or scope["path"] in ("/", "/webhook/stripe"):
            await self._app(scope, receive, send)
            return

        ip = self._ip_client(scope)
        maintenant = time.monotonic()
        historique = self._historique.setdefault(ip, deque())
        while historique and maintenant - historique[0] > self._fenetre:
            historique.popleft()

        if len(historique) >= self._max_requetes:
            response = PlainTextResponse(
                "Trop de requetes recues de votre part. Merci de reessayer dans une minute.",
                status_code=429,
            )
            await response(scope, receive, send)
            return

        historique.append(maintenant)
        await self._app(scope, receive, send)


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    host = "0.0.0.0"

    # Priorite: API_KEY_SHA256 (empreinte deja calculee) > API_KEY (cle en
    # clair, hachee ici) > empreinte par defaut codee en dur ci-dessus.
    empreinte_env = os.environ.get("API_KEY_SHA256")
    cle_en_clair_env = os.environ.get("API_KEY")
    if empreinte_env:
        empreinte_attendue = empreinte_env.strip().lower()
    elif cle_en_clair_env:
        empreinte_attendue = hashlib.sha256(cle_en_clair_env.encode()).hexdigest()
    else:
        empreinte_attendue = _EMPREINTE_CLE_API_PAR_DEFAUT

    pepper = os.environ.get("API_KEY_PEPPER")

    app = server.streamable_http_app(host=host)
    app.add_route("/", _accueil, methods=["GET"])
    app.add_route("/webhook/stripe", _webhook_stripe, methods=["POST"])
    app = _AuthentificationParCle(app, empreinte_attendue, pepper)
    app = _LimitationDebit(app)

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
