"""Calcul local du RSA, de la prime d'activite et de l'APL avec openfisca-france.

Tout le calcul se fait en local avec la bibliotheque openfisca-france
(SimulationBuilder d'openfisca-core). Aucun appel reseau n'est effectue.
"""

import math
from datetime import date

from openfisca_core.simulation_builder import SimulationBuilder
from openfisca_france import CountryTaxBenefitSystem
from openfisca_france.model.prestations import aides_logement as _openfisca_aides_logement

_TBS = CountryTaxBenefitSystem()

# Bornes de validation. Elles n'ont pas de sens "metier" precis : elles
# servent uniquement a rejeter les entrees absurdes ou malveillantes (ex:
# nombre_enfants=1000000) qui feraient construire une simulation openfisca
# demesuree et pourraient ralentir ou faire planter le serveur.
_NOMBRE_ENFANTS_MAX = 15
_MONTANT_MAX = 200_000.0


def _valider_montant(nom: str, valeur, obligatoire: bool = True) -> float:
    if valeur is None:
        if obligatoire:
            raise ValueError(f"{nom} est obligatoire")
        return 0.0
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise ValueError(f"{nom} doit etre un nombre")
    if not math.isfinite(valeur):
        raise ValueError(f"{nom} doit etre un nombre fini")
    if valeur < 0:
        raise ValueError(f"{nom} ne peut pas etre negatif")
    if valeur > _MONTANT_MAX:
        raise ValueError(f"{nom} depasse la limite autorisee ({_MONTANT_MAX})")
    return float(valeur)


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
    code_insee_commune: str | None = None,
) -> dict:
    """Calcule le RSA et la prime d'activite estimes pour un foyer, pour le mois en cours.

    Le calcul est fait entierement en local via openfisca-france (aucune
    requete reseau). C'est une ESTIMATION basee sur des hypotheses simplificatrices
    (age adulte suppose 30 ans, enfants supposes non etudiants et a charge,
    revenus supposes stables sur les 3 derniers mois pour la prime d'activite).

    Le RSA integre un forfait logement (deduction forfaitaire fixe prevue par
    la loi, ~12% du montant de base du RSA pour une personne seule - CE N'EST
    PAS une estimation du montant reel d'aide au logement). Ce forfait declenche
    en interne un calcul d'aide au logement pour verifier s'il s'applique
    (proprietaire/loge gratuitement) ou le plafonner (cas rare ou l'aide au
    logement reelle serait plus faible que le forfait). Ce calcul interne
    depend de la zone APL, deduite du code INSEE de la commune. Sans code
    INSEE fourni, la zone par defaut (zone 2) est utilisee pour cette
    verification interne uniquement - cela ne modifie generalement pas le RSA
    renvoye (le forfait lui-meme est un montant fixe, independant de la zone),
    sauf dans de rares cas limites.
    """
    salaire_net_mensuel = _valider_montant("salaire_net_mensuel", salaire_net_mensuel)
    loyer_mensuel = _valider_montant("loyer_mensuel", loyer_mensuel)
    salaire_net_mensuel_conjoint = _valider_montant(
        "salaire_net_mensuel_conjoint", salaire_net_mensuel_conjoint, obligatoire=False
    )

    if isinstance(nombre_enfants, bool) or not isinstance(nombre_enfants, int):
        raise ValueError("nombre_enfants doit etre un entier")
    if nombre_enfants < 0:
        raise ValueError("nombre_enfants ne peut pas etre negatif")
    if nombre_enfants > _NOMBRE_ENFANTS_MAX:
        raise ValueError(f"nombre_enfants depasse la limite autorisee ({_NOMBRE_ENFANTS_MAX})")

    if not isinstance(en_couple, bool):
        raise ValueError("en_couple doit etre vrai ou faux")

    statuts_valides = {
        "primo_accedant", "proprietaire", "locataire_hlm", "locataire_vide",
        "locataire_meuble", "loge_gratuitement", "locataire_foyer", "sans_domicile",
    }
    if not isinstance(statut_occupation_logement, str) or statut_occupation_logement not in statuts_valides:
        raise ValueError(
            f"statut_occupation_logement invalide: {statut_occupation_logement!r}. "
            f"Valeurs possibles: {sorted(statuts_valides)}"
        )

    if code_insee_commune is not None:
        if not isinstance(code_insee_commune, str):
            raise ValueError("code_insee_commune doit etre une chaine de caracteres")
        code_insee_commune = code_insee_commune.strip().upper()
        if len(code_insee_commune) != 5:
            raise ValueError(
                "code_insee_commune doit faire exactement 5 caracteres (code INSEE/depcom "
                "de la commune, ex: '75056' pour Paris) - pas le code postal."
            )
        if code_insee_commune not in _codes_insee_valides():
            raise ValueError(
                f"code_insee_commune {code_insee_commune!r} inconnu du zonage APL local "
                "d'openfisca-france. Verifiez le code INSEE de la commune."
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
    if code_insee_commune is not None:
        menage["depcom"] = {mois: code_insee_commune}
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

    if code_insee_commune is not None:
        note_zone = f"Zone APL deduite du code INSEE fourni ({code_insee_commune})."
    else:
        note_zone = (
            "code_insee_commune non fourni: le forfait logement a ete estime avec "
            "la zone APL par defaut (zone 2), utilisee uniquement pour une "
            "verification interne au calcul du forfait (voir ci-dessus); cela ne "
            "change generalement pas le RSA/la prime d'activite renvoyes."
        )

    return {
        "mois_calcule": mois,
        "rsa_mensuel_estime": round(rsa, 2),
        "prime_activite_mensuelle_estimee": round(prime_activite, 2),
        "hypotheses": (
            "Calcul local (openfisca-france), estimation. Age des adultes suppose "
            "30 ans, enfants supposes a charge et non etudiants, revenus supposes "
            "stables sur les 3 derniers mois. " + note_zone
        ),
    }


# --- APL / aide au logement -------------------------------------------------

_PREFIXES_RESIDENCE_OUTRE_MER = {
    "971": "residence_guadeloupe",
    "972": "residence_martinique",
    "973": "residence_guyane",
    "974": "residence_reunion",
    "975": "residence_saint_pierre_et_miquelon",
    "976": "residence_mayotte",
    "977": "residence_saint_bartelemy",
    "978": "residence_saint_martin",
}

# Statuts d'occupation pour lesquels le calcul standard d'openfisca-france
# s'applique (y compris les cas ou le montant est legitimement 0, ex:
# proprietaire sans pret ou logement gratuit: ce n'est pas une non-couverture,
# c'est une absence reelle de droit).
_STATUTS_APL_CALCULABLES = {
    "proprietaire", "locataire_hlm", "locataire_vide", "locataire_meuble",
    "loge_gratuitement", "sans_domicile",
}

# Statuts explicitement exclus: le calcul standard d'openfisca-france ne peut
# pas les estimer de facon fiable avec les seules donnees collectees ici.
_STATUTS_APL_NON_COUVERTS = {
    "primo_accedant": (
        "Non calculable: l'aide au logement pour un accedant a la propriete "
        "(primo_accedant) depend de la date exacte de signature du pret "
        "conventionne, et n'est quasiment plus ouverte aux nouveaux prets "
        "depuis le 1er janvier 2018 (sauf cas tres particuliers en zone 3). "
        "Cette date n'est pas collectee par cet outil: le resultat serait soit "
        "faux, soit trompeur. Ce cas n'est donc pas estime ici."
    ),
    "locataire_foyer": (
        "Non calculable: le logement en foyer (residence universitaire, foyer "
        "de jeunes travailleurs, foyer CROUS, residence pour personnes agees ou "
        "handicapees...) suit un bareme specifique. openfisca-france marque "
        "lui-meme explicitement ce statut comme 'non calculable' par la formule "
        "standard de l'aide au logement. Ce cas n'est donc pas estime ici."
    ),
}


def _codes_insee_valides() -> frozenset[str]:
    """Codes INSEE (depcom) reconnus par le zonage APL embarque dans
    openfisca-france (fichier local, aucun appel reseau).

    Sert a rejeter explicitement un code inconnu, plutot que de laisser
    openfisca-france retomber silencieusement sur la zone 2 par defaut
    (comportement de sa formule zone_apl en cas de code absent du zonage).
    """
    _openfisca_aides_logement.preload_zone_apl()
    return frozenset(_openfisca_aides_logement.zone_apl_by_depcom.keys())


def calculer_apl(
    salaire_brut_mensuel: float,
    loyer_mensuel: float,
    code_insee_commune: str,
    statut_occupation_logement: str,
    nombre_enfants: int,
    en_couple: bool,
    en_colocation: bool = False,
    salaire_brut_mensuel_conjoint: float | None = None,
) -> dict:
    """Estime l'aide au logement (APL/ALS/ALF, selon eligibilite) pour un foyer francais.

    Calcul 100% local via openfisca-france (aucun appel reseau externe). La
    zone APL est deduite automatiquement du code INSEE de la commune (fichier
    de zonage embarque dans openfisca-france), pas demandee directement.

    IMPORTANT: contrairement au RSA/prime d'activite (salaire NET), cet outil
    demande le salaire BRUT ("salaire de base"). C'est le montant que
    openfisca-france doit recevoir pour recalculer correctement, via son
    propre moteur de paie, le revenu imposable utilisé dans la base ressources
    "temps reel" de l'aide au logement (reforme 2021) - reutiliser le salaire
    net donnerait un resultat incorrect.
    """
    salaire_brut_mensuel = _valider_montant("salaire_brut_mensuel", salaire_brut_mensuel)
    loyer_mensuel = _valider_montant("loyer_mensuel", loyer_mensuel)
    salaire_brut_mensuel_conjoint = _valider_montant(
        "salaire_brut_mensuel_conjoint", salaire_brut_mensuel_conjoint, obligatoire=False
    )

    if isinstance(nombre_enfants, bool) or not isinstance(nombre_enfants, int):
        raise ValueError("nombre_enfants doit etre un entier")
    if nombre_enfants < 0:
        raise ValueError("nombre_enfants ne peut pas etre negatif")
    if nombre_enfants > _NOMBRE_ENFANTS_MAX:
        raise ValueError(f"nombre_enfants depasse la limite autorisee ({_NOMBRE_ENFANTS_MAX})")

    if not isinstance(en_couple, bool):
        raise ValueError("en_couple doit etre vrai ou faux")
    if not isinstance(en_colocation, bool):
        raise ValueError("en_colocation doit etre vrai ou faux")

    statuts_valides = _STATUTS_APL_CALCULABLES | set(_STATUTS_APL_NON_COUVERTS)
    if not isinstance(statut_occupation_logement, str) or statut_occupation_logement not in statuts_valides:
        raise ValueError(
            f"statut_occupation_logement invalide: {statut_occupation_logement!r}. "
            f"Valeurs possibles: {sorted(statuts_valides)}"
        )
    if statut_occupation_logement in _STATUTS_APL_NON_COUVERTS:
        raise ValueError(_STATUTS_APL_NON_COUVERTS[statut_occupation_logement])

    if not isinstance(code_insee_commune, str):
        raise ValueError("code_insee_commune doit etre une chaine de caracteres")
    code_insee_commune = code_insee_commune.strip().upper()
    if len(code_insee_commune) != 5:
        raise ValueError(
            "code_insee_commune doit faire exactement 5 caracteres (code INSEE/depcom "
            "de la commune, ex: '75056' pour Paris, '69123' pour Lyon) - pas le code postal."
        )
    if code_insee_commune not in _codes_insee_valides():
        raise ValueError(
            f"code_insee_commune {code_insee_commune!r} inconnu du zonage APL local "
            "d'openfisca-france. Verifiez le code INSEE de la commune."
        )

    aujourdhui = date.today()
    mois = f"{aujourdhui.year:04d}-{aujourdhui.month:02d}"
    # Depuis la reforme "en temps reel" (2021), la base ressources de l'aide au
    # logement s'appuie sur environ 12 mois glissants se terminant ~2 mois
    # avant le mois calcule. On fournit une marge large (15 mois, mois calcule
    # inclus) pour couvrir cette fenetre quelle que soit la position exacte de
    # ses bornes, avec l'hypothese simplificatrice d'un salaire brut stable sur
    # toute la periode (meme principe que pour le RSA/la prime d'activite).
    mois_ressources = [mois] + _mois_precedents(mois, 14)

    individus: dict = {
        "demandeur": {
            "date_naissance": {"ETERNITY": _date_naissance_pour_age(aujourdhui.year, 30)},
            "salaire_de_base": {m: salaire_brut_mensuel for m in mois_ressources},
        }
    }
    parents = ["demandeur"]

    if en_couple:
        individus["conjoint"] = {
            "date_naissance": {"ETERNITY": _date_naissance_pour_age(aujourdhui.year, 30)},
            "salaire_de_base": {m: (salaire_brut_mensuel_conjoint or 0) for m in mois_ressources},
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

    menage: dict = {
        "personne_de_reference": "demandeur",
        "enfants": enfants_ids,
        "loyer": {mois: loyer_mensuel},
        "statut_occupation_logement": {mois: statut_occupation_logement},
        "depcom": {mois: code_insee_commune},
        "coloc": {mois: en_colocation},
    }
    prefixe_departement = code_insee_commune[:3]
    variable_residence = _PREFIXES_RESIDENCE_OUTRE_MER.get(prefixe_departement)
    if variable_residence:
        menage[variable_residence] = {mois: True}
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

    montant_total = float(simulation.calculate("aide_logement", mois)[0])
    montant_apl = float(simulation.calculate("apl", mois)[0])
    montant_als = float(simulation.calculate("als", mois)[0])
    montant_alf = float(simulation.calculate("alf", mois)[0])

    if montant_apl > 0:
        dispositif = "APL (aide personnalisee au logement - logement conventionne/HLM)"
    elif montant_alf > 0:
        dispositif = "ALF (allocation de logement familiale)"
    elif montant_als > 0:
        dispositif = "ALS (allocation de logement sociale)"
    else:
        dispositif = None

    return {
        "mois_calcule": mois,
        "aide_logement_mensuelle_estimee": round(montant_total, 2),
        "dispositif_applicable": dispositif,
        "hypotheses": (
            "Calcul local (openfisca-france), estimation. Age des adultes suppose 30 "
            "ans, enfants supposes a charge et non etudiants, salaire BRUT suppose "
            "stable sur environ les 15 derniers mois (base ressources 'temps reel' de "
            "l'aide au logement). Zone APL deduite automatiquement du code INSEE fourni."
        ),
        "perimetre_couvert": (
            "Couvre: location classique (vide, meuble, HLM), y compris en colocation "
            "(indiquez alors votre part personnelle de loyer, et en_colocation=true - "
            "le calcul estime votre allocation individuelle sur cette base, sans "
            "modeliser le partage entre colocataires), proprietaire sans pret en cours, "
            "logement gratuit, et situation sans domicile (0 EUR estime dans ces 3 "
            "derniers cas: absence reelle de droit, pas une limite du calcul). Les "
            "DOM et Saint-Pierre-et-Miquelon/Saint-Barthelemy/Saint-Martin sont pris en "
            "compte automatiquement d'apres le code INSEE."
        ),
        "perimetre_non_couvert": (
            "Ne couvre PAS: accession a la propriete avec pret en cours "
            "(statut primo_accedant), logement-foyer/residence collective, "
            "universitaire ou CROUS (statut locataire_foyer) - ces deux statuts "
            "renvoient une erreur explicite plutot qu'un montant approximatif. Ne "
            "modelise pas non plus: personnes agees/handicapees hebergees a titre "
            "onereux, chambres meublees specifiquement, ni les revenus non salaries "
            "(travailleurs independants, chomage indemnise, retraite, pension "
            "d'invalidite, revenus du patrimoine) - ce calcul suppose un revenu "
            "salarie stable uniquement et les ignore s'ils existent par ailleurs."
        ),
    }
