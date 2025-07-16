"""pixid_sync package initializer

Expose les constantes communes pour l'ensemble des modules, afin que les
imports relatifs de xml_processor.py (et autres) fonctionnent sans erreur.
"""

# --- Constantes -----------------------------------------------------------

XML_FIELD_MAPPING = {
    # "Nom de colonne Google Sheet" : "Balise XML à créer / mettre à jour"
    "Numéro de commande": "OrderId",
    "Code agence": "AgencyCode",
    "Code unité": "UnitCode",
    "Statut": "TempStatus",
    "Niveau convention collective": "CollectiveLevel",
    "Classification de l’intérimaire": "TempClassification",
    "Personne absente": "AbsenteeName",
}

# Liste simple utilisée par d'autres modules pour boucler sur les champs
FIELDS_TO_EXTRACT = list(XML_FIELD_MAPPING.keys())

# Rendre les symboles importables via `from pixid_sync import ...`
__all__ = [
    "XML_FIELD_MAPPING",
    "FIELDS_TO_EXTRACT",
]
