"""Calcul local du RSA et de la prime d'activite avec openfisca-france.

Tout le calcul se fait en local avec la bibliotheque openfisca-france
(SimulationBuilder d'openfisca-core). Aucun appel reseau n'est effectue.
"""

from datetime import date

from openfisca_core.simulation_builder import SimulationBuilder
from openfisca_france import CountryTaxBenefitSystem

_TBS = CountryTaxBenefitSystem()


def _mois_precedents(mois: str, n: int) -> list[str]:
    annee, mois_num = (int(x) for x in mois.split("-"))
    resultat = []
    for _ in range(n):
        mois_num -= 1
        if mois_num == 0:
            mois_num = 12
            annee -= 1
        resultat.append(f"{annee:04d}-{mois_num:02d}")
    return resultat


def _date_naissance_pour_age(annee_ref: int, age_annees: int) -> str:
    return f"{annee_ref - age_annees:04d}-06-15"


def calculer_rsa_prime_activite(
    salaire_net_mensuel: float,
    loyer_mensuel: float,
    statut_occupation_logement: str,
    nombre_enfants: int,
    en_couple: bool,
    salaire_net_mensuel_conjoint: float | None = None,
) -> dict:
    """Calcule le RSA et la prime d'activite estimes pour un foyer, pour le mois en cours.

    Le calcul est fait entierement en local via openfisca-france (aucune
    requete reseau). C'est une ESTIMATION basee sur des hypotheses simplificatrices
    (age adulte suppose 30 ans, enfants supposes non etudiants et a charge,
    revenus supposes stables sur les 3 derniers mois pour la prime d'activite).
    """
    if nombre_enfants < 0:
        raise ValueError("nombre_enfants ne peut pas etre negatif")

    statuts_valides = {
        "primo_accedant", "proprietaire", "locataire_hlm", "locataire_vide",
        "locataire_meuble", "loge_gratuitement", "locataire_foyer", "sans_domicile",
    }
    if statut_occupation_logement not in statuts_valides:
        raise ValueError(
            f"statut_occupation_logement invalide: {statut_occupation_logement!r}. "
            f"Valeurs possibles: {sorted(statuts_valides)}"
        )

    aujourdhui = date.today()
    mois = f"{aujourdhui.year:04d}-{aujourdhui.month:02d}"
    trois_derniers_mois = [mois] + _mois_precedents(mois, 2)

    individus: dict = {
        "demandeur": {
            "date_naissance": {"ETERNITY": _date_naissance_pour_age(aujourdhui.year, 30)},
            "salaire_net": {m: salaire_net_mensuel for m in trois_derniers_mois},
        }
    }
    parents = ["demandeur"]

    if en_couple:
        individus["conjoint"] = {
            "date_naissance": {"ETERNITY": _date_naissance_pour_age(aujourdhui.year, 30)},
            "salaire_net": {m: (salaire_net_mensuel_conjoint or 0) for m in trois_derniers_mois},
        }
        parents.append("conjoint")

    enfants_ids = []
    for i in range(nombre_enfants):
        enfant_id = f"enfant{i + 1}"
        age_enfant = min(10 + i, 17)
        individus[enfant_id] = {
            "date_naissance": {"ETERNITY": _date_naissance_pour_age(aujourdhui.year, age_enfant)},
        }
        enfants_ids.append(enfant_id)

    menage = {
        "personne_de_reference": "demandeur",
        "enfants": enfants_ids,
        "loyer": {mois: loyer_mensuel},
        "statut_occupation_logement": {mois: statut_occupation_logement},
    }
    if en_couple:
        menage["conjoint"] = "conjoint"

    foyer_fiscal = {
        "declarants": list(parents),
        "personnes_a_charge": enfants_ids,
    }

    situation = {
        "individus": individus,
        "familles": {
            "famille1": {
                "parents": parents,
                "enfants": enfants_ids,
            }
        },
        "foyers_fiscaux": {"foyer1": foyer_fiscal},
        "menages": {"menage1": menage},
    }

    builder = SimulationBuilder()
    simulation = builder.build_from_entities(_TBS, situation)

    rsa = float(simulation.calculate("rsa", mois)[0])
    prime_activite = float(simulation.calculate("ppa", mois)[0])

    return {
        "mois_calcule": mois,
        "rsa_mensuel_estime": round(rsa, 2),
        "prime_activite_mensuelle_estimee": round(prime_activite, 2),
        "hypotheses": (
            "Calcul local (openfisca-france), estimation. Age des adultes suppose "
            "30 ans, enfants supposes a charge et non etudiants, revenus supposes "
            "stables sur les 3 derniers mois."
        ),
    }
