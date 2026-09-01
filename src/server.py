"""Serveur MCP exposant le calcul du RSA et de la prime d'activite.

Le calcul est fait entierement en local avec openfisca-france (voir calcul.py),
sans aucun appel a l'API publique api.fr.openfisca.org ni a un autre service
externe.

Lancement:
    python src/server.py
Le serveur ecoute en HTTP (transport "streamable-http") sur le port defini
par la variable d'environnement PORT (8000 par defaut), accessible sur /mcp.
"""

import os

from mcp.server.mcpserver import MCPServer

from calcul import calculer_rsa_prime_activite

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


def main() -> None:
    import uvicorn
    from starlette.routing import Route

    port = int(os.environ.get("PORT", "8000"))
    host = "0.0.0.0"

    app = server.streamable_http_app(host=host)
    app.add_route("/", _accueil, methods=["GET"])

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
