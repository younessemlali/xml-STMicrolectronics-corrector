# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from xml_enricher import process_all, load_commandes

st.set_page_config(page_title="PIXID XML Corrector — 3 balises", layout="wide")
st.title("🔧 PIXID XML Corrector (Coefficient + Statut Code + Statut Description)")

st.markdown("""
Déposez un **XML multi-contrats** (même très gros) et un fichier **commandes** (JSON/CSV).  
L'app met à jour **exactement 3 balises** par contrat, puis vous permet de **télécharger** le XML corrigé et un **récap**.
""")

xml_file = st.file_uploader("📄 Fichier XML", type=["xml"])
cmd_file = st.file_uploader("🧾 Fichier commandes (JSON ou CSV)", type=["json", "csv"])

go = st.button("🚀 Corriger le XML", type="primary", disabled=not (xml_file and cmd_file))

if go:
    xml_bytes = xml_file.read()

    # Charger commandes depuis buffer (auto JSON/CSV)
    try:
        commandes = load_commandes(cmd_file)
    except Exception as e:
        st.error(f"Erreur chargement commandes: {e}")
        st.stop()

    # Traiter
    try:
        fixed_bytes, recaps, log = process_all(xml_bytes, commandes)
    except Exception as e:
        st.error(f"Erreur traitement: {e}")
    else:
        n = log.get("contracts_detected", 0)
        st.success(f"{n} contrats détectés.")
        st.write(f"MAJ Coefficient: {log.get('coef_updates',0)} | MAJ Statut Code: {log.get('status_code_updates',0)} | MAJ Statut Description: {log.get('status_desc_updates',0)}")
        sample = log.get("modified_ids_sample", [])
        if sample:
            st.write("OrderId modifiés (échantillon): ", sample)
        if log.get("unmatched_sample"):
            st.info(f"Non appariés (échantillon): {log['unmatched_sample']}")
        if log.get("warning"):
            st.warning(log["warning"])

        # Tableau récap
        if recaps:
            df = pd.DataFrame(recaps)
            st.dataframe(df, use_container_width=True)
            st.download_button("⬇️ CSV récapitulatif", data=df.to_csv(index=False).encode("utf-8"),
                               file_name="recap.csv", mime="text/csv")

        # XML corrigé
        st.download_button("⬇️ XML corrigé", data=fixed_bytes,
                           file_name=xml_file.name.replace(".xml","_fixed.xml"),
                           mime="application/xml")

st.caption("Modifie uniquement 3 balises / contrat. Encodage d'origine préservé. Détection namespace-agnostique. Upsert si balise absente.")
