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
import os

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


async def _accueil(request):
    from starlette.responses import PlainTextResponse

    return PlainTextResponse(
        "Serveur MCP 'aides-sociales-france' en ligne. Point d'entree MCP: /mcp"
    )


class _AuthentificationParCle:
    """Exige une cle d'acces (API key) sur toutes les routes sauf la page d'accueil "/".

    La cle fournie par le client (en-tete "X-API-Key", ou "Authorization:
    Bearer <cle>") est hachee en SHA-256 puis comparee a l'empreinte
    attendue. La cle en clair n'est jamais stockee ni comparee directement,
    ce qui permet de garder l'empreinte dans le code source sans risque.
    """

    def __init__(self, app, empreinte_attendue: str) -> None:
        self._app = app
        self._empreinte_attendue = empreinte_attendue

    async def __call__(self, scope, receive, send):
        import hmac

        from starlette.responses import PlainTextResponse

        if scope["type"] != "http" or scope["path"] == "/":
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        cle_fournie = headers.get(b"x-api-key", b"").decode()
        if not cle_fournie:
            auth = headers.get(b"authorization", b"").decode()
            if auth.lower().startswith("bearer "):
                cle_fournie = auth[7:].strip()

        empreinte_fournie = hashlib.sha256(cle_fournie.encode()).hexdigest()

        if not cle_fournie or not hmac.compare_digest(empreinte_fournie, self._empreinte_attendue):
            response = PlainTextResponse(
                "Cle d'acces manquante ou invalide. Fournissez l'en-tete "
                "'X-API-Key' ou 'Authorization: Bearer <cle>'.",
                status_code=401,
            )
            await response(scope, receive, send)
            return

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

    app = server.streamable_http_app(host=host)
    app.add_route("/", _accueil, methods=["GET"])
    app = _AuthentificationParCle(app, empreinte_attendue)

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
