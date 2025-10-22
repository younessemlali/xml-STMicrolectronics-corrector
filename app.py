# -*- coding: utf-8 -*-
import io
import requests
import pandas as pd
import streamlit as st

# Cœur métier (3 balises) — garde le xml_enricher.py fourni
from xml_enricher import process_all, load_commandes

# =========================
# 🔧 CONFIG (modifie ici)
# =========================
GITHUB_OWNER = "younessemlali"
GITHUB_REPO  = "xml-STMicrolectronics-corrector"
GITHUB_REF   = "main"
# Chemin du fichier commandes (JSON ou CSV) dans ton repo public :
GITHUB_PATH  = "samples/commandes_stm.json"
# Délai de rafraîchissement des commandes (cache) en secondes :
CACHE_TTL_S  = 120

# =========================
# UI
# =========================
st.set_page_config(page_title="PIXID XML Corrector — Sync GitHub", layout="wide")
st.title("🔧 PIXID XML Corrector — Sync GitHub → Commandes")
st.caption("Corrige 3 balises / contrat : PositionCoefficient • PositionStatus/Code • PositionStatus/Description")

st.markdown(
    "Les **commandes** sont chargées **automatiquement** depuis : "
    f"`{GITHUB_OWNER}/{GITHUB_REPO}@{GITHUB_REF}:{GITHUB_PATH}`\n\n"
    "Tu n'as qu'à déposer le **XML** ci-dessous."
)

# =========================
# GitHub helper
# =========================
def _raw_url(owner: str, repo: str, ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path.lstrip('/')}"

@st.cache_data(ttl=CACHE_TTL_S)
def fetch_commandes_text(owner: str, repo: str, ref: str, path: str) -> str:
    url = _raw_url(owner, repo, ref, path)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text

# Charger automatiquement les commandes depuis GitHub (public, sans token)
cmd_error = None
commandes_dict = None
try:
    text = fetch_commandes_text(GITHUB_OWNER, GITHUB_REPO, GITHUB_REF, GITHUB_PATH)
    commandes_dict = load_commandes(io.StringIO(text))  # auto JSON/CSV
    st.success(f"{len(commandes_dict)} commandes chargées depuis GitHub (auto-sync).")
except Exception as e:
    cmd_error = f"Erreur de synchronisation GitHub : {e}"
    st.error(cmd_error)

# Bouton pour forcer un rechargement (purge cache)
colA, colB = st.columns([1, 4])
if colA.button("🔄 Recharger depuis GitHub"):
    fetch_commandes_text.clear()  # purge cache
    st.experimental_rerun()

with colB:
    st.write(
        f"**Source** : `{GITHUB_OWNER}/{GITHUB_REPO}` — **Branche** : `{GITHUB_REF}` — **Fichier** : `{GITHUB_PATH}`"
        f" — **Cache TTL** : {CACHE_TTL_S}s"
    )

st.divider()

# =========================
# XML input
# =========================
xml_file = st.file_uploader("📄 Dépose ton fichier XML (multi-contrats, gros volumes OK)", type=["xml"])

# =========================
# Corriger
# =========================
go = st.button("🚀 Corriger le XML", type="primary", disabled=not xml_file or not commandes_dict)

if go:
    if not commandes_dict:
        st.warning("Aucune commande disponible (la synchro GitHub a échoué).")
        st.stop()

    xml_bytes = xml_file.read()
    try:
        fixed_bytes, recaps, log = process_all(xml_bytes, commandes_dict)
    except Exception as e:
        st.error(f"Erreur traitement: {e}")
        st.stop()

    # Résumé
    n = log.get("contracts_detected", 0)
    st.success(f"{n} contrats détectés.")
    st.write(
        f"**MAJ Coefficient**: {log.get('coef_updates',0)}  |  "
        f"**MAJ Statut Code**: {log.get('status_code_updates',0)}  |  "
        f"**MAJ Statut Description**: {log.get('status_desc_updates',0)}"
    )
    sample = log.get("modified_ids_sample", [])
    if sample:
        st.write("🔧 OrderId modifiés (échantillon) :", sample)
    if log.get("unmatched_sample"):
        st.info(f"🔎 Non appariés (échantillon) : {log['unmatched_sample']}")
    if log.get("warning"):
        st.warning(log["warning"])

    # Récap
    if recaps:
        df = pd.DataFrame(recaps)
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "⬇️ CSV récapitulatif",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="recap.csv",
            mime="text/csv",
        )

    # XML corrigé (encodage d'origine préservé par xml_enricher)
    st.download_button(
        "⬇️ XML corrigé",
        data=fixed_bytes,
        file_name=xml_file.name.replace(".xml", "_fixed.xml"),
        mime="application/xml",
    )

st.caption("Synchro GitHub publique → commandes (auto). Dépose juste le XML. Détection namespace-agnostique. 3 champs mis à jour par contrat.")
