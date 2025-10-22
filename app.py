# -*- coding: utf-8 -*-
import io
import re
import requests
import pandas as pd
import streamlit as st
from urllib.parse import urlparse

# ⚙️ coeur métier (assurez-vous d'avoir le xml_enricher.py fourni)
from xml_enricher import process_all, load_commandes

# -------------------------- UI setup --------------------------
st.set_page_config(page_title="PIXID XML Corrector — 3 balises", layout="wide")
st.title("🔧 PIXID XML Corrector")
st.caption("Met à jour exactement 3 balises / contrat : PositionCoefficient, PositionStatus/Code, PositionStatus/Description")

st.markdown("""
**Mode d'emploi :**
1. Chargez votre **XML multi-contrats** (même >10 Mo).
2. Choisissez la **source des commandes** : Upload ou GitHub (public/privé).
3. Cliquez **Corriger le XML** → Téléchargez le XML corrigé et le CSV récap.
""")

# -------------------------- Helpers GitHub --------------------------
@st.cache_data(ttl=300)
def fetch_github_text(url_or_path: str, ref: str = "main", token: str | None = None) -> str:
    """
    Récupère un fichier texte (JSON/CSV) sur GitHub.
    - Forme 1: 'owner/repo:path/vers/fichier.ext'
    - Forme 2: URL 'https://github.com/.../blob/...'
    - Forme 3: URL 'https://raw.githubusercontent.com/...'
    Retourne le contenu texte.
    """
    s = (url_or_path or "").strip()
    if not s:
        raise ValueError("Chemin/URL GitHub manquant.")

    # 1) Forme "owner/repo:path"
    m = re.match(r"^([^/\s]+)/([^:\s]+):(.+)$", s)
    if m:
        owner, repo, path = m.group(1), m.group(2), m.group(3).lstrip("/")
        if token:
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
            headers = {"Accept": "application/vnd.github.v3.raw", "Authorization": f"Bearer {token}"}
            r = requests.get(api_url, headers=headers, timeout=30)
            r.raise_for_status()
            return r.text
        else:
            raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
            r = requests.get(raw, timeout=30)
            r.raise_for_status()
            return r.text

    # 2/3) URL complète
    u = urlparse(s)
    if "raw.githubusercontent.com" in u.netloc:
        r = requests.get(s, timeout=30)
        r.raise_for_status()
        return r.text

    if "github.com" in u.netloc and "/blob/" in u.path:
        # Convertir /blob/ -> /raw/ ou passer par l'API si token
        parts = u.path.strip("/").split("/")
        # /owner/repo/blob/ref/path/to/file
        if len(parts) < 5:
            raise ValueError("URL GitHub inattendue. Exemple: https://github.com/owner/repo/blob/main/path/file.json")
        owner, repo, _blob, ref_part, *rest = parts
        path = "/".join(rest)
        if token:
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref or ref_part}"
            headers = {"Accept": "application/vnd.github.v3.raw", "Authorization": f"Bearer {token}"}
            r = requests.get(api_url, headers=headers, timeout=30)
            r.raise_for_status()
            return r.text
        else:
            raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref or ref_part}/{path}"
            r = requests.get(raw, timeout=30)
            r.raise_for_status()
            return r.text

    raise ValueError(
        "Format GitHub non reconnu.\n"
        "- Ex: owner/repo:path/vers/fichier.json\n"
        "- ou URL https://github.com/.../blob/... \n"
        "- ou URL https://raw.githubusercontent.com/..."
    )

# -------------------------- Inputs --------------------------
xml_file = st.file_uploader("📄 Fichier XML", type=["xml"])

st.subheader("🧾 Commandes (JSON/CSV)")
source = st.radio("Source des commandes", ["Upload", "GitHub"], horizontal=True)

commandes_dict = None
cmd_error = None

if source == "Upload":
    cmd_file = st.file_uploader("Choisir un fichier commandes", type=["json", "csv"])
    if cmd_file is not None:
        try:
            # load_commandes accepte un buffer texte (UploadedFile)
            commandes_dict = load_commandes(cmd_file)
            st.success(f"{len(commandes_dict)} commandes chargées (upload).")
        except Exception as e:
            cmd_error = f"Erreur chargement commandes (upload) : {e}"
else:
    gh_input = st.text_input(
        "Chemin GitHub (ex: younessemlali/xml-STMicrolectronics-corrector:samples/commandes_stm.json "
        "ou URL https://github.com/.../blob/main/... )"
    )
    ref = st.text_input("Branche / tag (si applicable)", value="main")
    use_token = st.checkbox("Dépôt privé (utiliser st.secrets['GITHUB_TOKEN'])", value=False)

    if st.button("🔗 Charger depuis GitHub"):
        try:
            token = st.secrets.get("GITHUB_TOKEN") if use_token else None
            text = fetch_github_text(gh_input, ref=ref, token=token)
            commandes_dict = load_commandes(io.StringIO(text))  # parse JSON/CSV depuis texte
            st.success(f"{len(commandes_dict)} commandes chargées (GitHub).")
        except Exception as e:
            cmd_error = f"Erreur chargement depuis GitHub : {e}"

if cmd_error:
    st.error(cmd_error)

st.divider()

# -------------------------- Action --------------------------
go = st.button("🚀 Corriger le XML", type="primary", disabled=not xml_file)

if go:
    if not commandes_dict:
        st.warning("Aucune commande chargée (via Upload ou GitHub).")
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

    # Tableau récap
    if recaps:
        df = pd.DataFrame(recaps)
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "⬇️ CSV récapitulatif",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="recap.csv",
            mime="text/csv",
        )

    # XML corrigé
    st.download_button(
        "⬇️ XML corrigé",
        data=fixed_bytes,
        file_name=xml_file.name.replace(".xml", "_fixed.xml"),
        mime="application/xml",
    )

st.caption("Détection namespace-agnostique • Upsert si balise absente • Encodage d'origine préservé • 3 champs mis à jour par contrat.")
