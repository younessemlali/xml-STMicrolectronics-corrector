# -*- coding: utf-8 -*-
"""
Single-file Streamlit app — PIXID XML Corrector (GitHub auto-sync) ⛭
- Déposez UNIQUEMENT le XML.
- Les "commandes" (JSON/CSV) sont chargées AUTOMATIQUEMENT depuis GitHub (repo public).
- Met à jour EXACTEMENT 3 balises par contrat :
  1) PositionCharacteristics/PositionCoefficient
  2) PositionCharacteristics/PositionStatus/Code
  3) PositionCharacteristics/PositionStatus/Description
- Encodage d'origine du XML préservé.
"""

import io
import re
import csv
import json
import time
import requests
import pandas as pd
import streamlit as st
from io import BytesIO
from urllib.parse import urlparse
from lxml import etree

# =========================
# 🔧 CONFIG GITHUB (modifiez ici si besoin)
# =========================
GITHUB_OWNER = "younessemlali"
GITHUB_REPO  = "xml-STMicrolectronics-corrector"
GITHUB_REF   = "main"
# Fichier commandes dans le repo public (JSON ou CSV) :
GITHUB_PATH  = "data/commandes_stm.json"
# Durée du cache des commandes (en secondes)
CACHE_TTL_S  = 120

# =========================
# Mapping code -> libellé (complétez si besoin)
# =========================
STATUS_LABEL_MAP = {
    "OP": "Opérateur",
    "6A": "Ouvriers",
    # "EM": "Employés",
    # ajoutez vos codes ici...
}

# =========================
# UI
# =========================
st.set_page_config(page_title="PIXID XML Corrector — GitHub auto-sync", layout="wide")
st.title("🔧 PIXID XML Corrector — GitHub → Commandes (auto)")
st.caption("Met à jour 3 balises / contrat : PositionCoefficient • PositionStatus/Code • PositionStatus/Description")

st.markdown(
    "Les **commandes** sont chargées **automatiquement** depuis : "
    f"`{GITHUB_OWNER}/{GITHUB_REPO}@{GITHUB_REF}:{GITHUB_PATH}` — *cache {CACHE_TTL_S}s*.\n\n"
    "Déposez simplement votre **XML** ci-dessous."
)

# =========================
# Helpers "commandes"
# =========================
def _raw_url(owner: str, repo: str, ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path.lstrip('/')}"

@st.cache_data(ttl=CACHE_TTL_S)
def fetch_commandes_text(owner: str, repo: str, ref: str, path: str) -> str:
    url = _raw_url(owner, repo, ref, path)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def _norm_key(k) -> str:
    if k is None: return ""
    return "".join(str(k).strip().upper().split())

def load_commandes(text: str, key_field: str = "numero_commande") -> dict:
    """
    Accepte texte JSON/CSV. Retourne dict { ORDERID -> row } avec clé normalisée.
    """
    stripped = (text or "").lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        data = json.loads(text)
        if isinstance(data, dict):
            return { _norm_key(k): v for k, v in data.items() }
        elif isinstance(data, list):
            out = {}
            for row in data:
                key = _norm_key(row.get(key_field))
                if key: out[key] = row
            return out
        else:
            raise ValueError("JSON inattendu (dict ou liste attendu).")
    # CSV fallback
    out = {}
    reader = csv.DictReader(text.splitlines())
    if key_field not in (reader.fieldnames or []):
        raise ValueError(f"Colonne '{key_field}' absente du CSV.")
    for row in reader:
        key = _norm_key(row.get(key_field))
        if key: out[key] = {k:(v.strip() if isinstance(v,str) else v) for k,v in row.items()}
    return out

# =========================
# Helpers XML (enricher 3 champs)
# =========================
XP_CTX    = "//*[local-name()='ReferenceInformation'][*[local-name()='OrderId']/*[local-name()='IdValue']]/.."
XP_ORDER  = ".//*[local-name()='ReferenceInformation']/*[local-name()='OrderId']/*[local-name()='IdValue']"
XP_ASSIGN = ".//*[local-name()='ReferenceInformation']/*[local-name()='AssignmentId']/*[local-name()='IdValue']"
XP_LEVEL  = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionLevel']"
XP_COEFF  = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionCoefficient']"
XP_STATUS_CODE = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionStatus']/*[local-name()='Code']"
XP_STATUS_DESC = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionStatus']/*[local-name()='Description']"

CLASS_RE = re.compile(r"^[A-E]\d{1,2}$")

def parse_tree(xml_bytes: bytes) -> etree._ElementTree:
    parser = etree.XMLParser(remove_blank_text=True, recover=True, huge_tree=True)
    return etree.parse(BytesIO(xml_bytes), parser)

def to_bytes(tree: etree._ElementTree) -> bytes:
    enc = tree.docinfo.encoding or "UTF-8"
    return etree.tostring(tree, encoding=enc, pretty_print=True, xml_declaration=True)

def xget(ctx: etree._Element, xp: str) -> str:
    try:
        n = ctx.xpath(xp)
    except Exception:
        return ""
    return (n[0].text or "").strip() if n and n[0].text is not None else ""

def _find_default_ns(el: etree._Element):
    cur = el
    while cur is not None:
        ns = cur.nsmap.get(None)
        if ns: return ns
        cur = cur.getparent()
    return None

def xupsert(ctx: etree._Element, ln_path: str, value: str) -> None:
    """
    Crée si absent (dans le bon namespace) puis pose la valeur.
    ln_path doit utiliser local-name(), ex: XP_COEFF / XP_STATUS_CODE / XP_STATUS_DESC
    """
    parts = []
    tmp = ln_path
    while True:
        i = tmp.find("local-name()='")
        if i == -1: break
        j = i + len("local-name()='")
        k = tmp.find("'", j)
        if k == -1: break
        parts.append(tmp[j:k])
        tmp = tmp[k+1:]
    if not parts:
        nodes = ctx.xpath(ln_path)
        if nodes:
            nodes[0].text = value
        return
    cur = ctx
    for name in parts:
        found = cur.xpath(f"./*[local-name()='{name}']")
        if found:
            cur = found[0]
        else:
            ns = _find_default_ns(cur)
            tag = f"{{{ns}}}{name}" if ns else name
            cur = etree.SubElement(cur, tag)
    cur.text = value

def process_all(xml_bytes: bytes, commandes: dict) -> tuple[bytes, list[dict], dict]:
    """
    Retourne: (xml_corrige_bytes, recaps_par_contrat, log_global)
    """
    tree = parse_tree(xml_bytes)
    contexts = tree.xpath(XP_CTX)
    recaps = []
    upd_coeff = upd_code = upd_desc = 0
    modified_ids = []
    unmatched_sample = []

    for ctx in contexts:
        order  = xget(ctx, XP_ORDER)
        assign = xget(ctx, XP_ASSIGN)
        key    = _norm_key(order)
        row    = commandes.get(key)

        before_c   = xget(ctx, XP_COEFF)
        before_code= xget(ctx, XP_STATUS_CODE)
        before_desc= xget(ctx, XP_STATUS_DESC)
        level      = xget(ctx, XP_LEVEL)

        # 1) PositionCoefficient
        if row and (row.get("classification_interimaire") or "").strip():
            xupsert(ctx, XP_COEFF, row["classification_interimaire"].strip())
        elif (not row) and (not before_c) and CLASS_RE.match(level or ""):
            xupsert(ctx, XP_COEFF, level)

        # 2) Status Code + 3) Description
        code = (row.get("statut") or "").strip() if row else ""
        desc = (row.get("statut_description") or "").strip() if row else ""
        if code:
            # Code : MAJ tous les noeuds existants; sinon en créer un
            nodes_code = ctx.xpath(XP_STATUS_CODE)
            if nodes_code:
                for n in nodes_code: n.text = code
            else:
                xupsert(ctx, XP_STATUS_CODE, code)
            # Description (depuis commandes ou mapping)
            final_desc = desc or STATUS_LABEL_MAP.get(code, desc)
            if final_desc:
                nodes_desc = ctx.xpath(XP_STATUS_DESC)
                if nodes_desc:
                    for n in nodes_desc: n.text = final_desc
                else:
                    xupsert(ctx, XP_STATUS_DESC, final_desc)

        after_c    = xget(ctx, XP_COEFF)
        after_code = xget(ctx, XP_STATUS_CODE)
        after_desc = xget(ctx, XP_STATUS_DESC)

        changed = False
        if after_c != before_c:
            upd_coeff += 1; changed = True
        if after_code != before_code:
            upd_code  += 1; changed = True
        if after_desc != before_desc:
            upd_desc  += 1; changed = True
        if changed:
            modified_ids.append(order)
        elif not row and len(unmatched_sample) < 10:
            unmatched_sample.append(order)

        note = ""
        if (not row) and (not before_c) and (after_c == level) and CLASS_RE.match(level or ""):
            note = "coefficient copié depuis PositionLevel"

        recaps.append({
            "OrderId": order, "AssignmentId": assign,
            "PositionCoefficient": after_c,
            "PositionStatusCode": after_code,
            "PositionStatusDescription": after_desc,
            "matched": bool(row), "note": note
        })

    out_bytes = to_bytes(tree)
    log = {
        "contracts_detected": len(contexts),
        "coef_updates": upd_coeff,
        "status_code_updates": upd_code,
        "status_desc_updates": upd_desc,
        "modified_ids_sample": modified_ids[:10],
        "unmatched_sample": unmatched_sample
    }
    if commandes and upd_coeff == 0 and upd_code == 0 and upd_desc == 0:
        log["warning"] = "Commandes chargées mais 0 mise à jour — vérifiez la clé 'numero_commande' et le mapping."

    return out_bytes, recaps, log

# =========================
# Charger commandes depuis GitHub (auto)
# =========================
commandes_dict = None
cmd_error = None
try:
    text = fetch_commandes_text(GITHUB_OWNER, GITHUB_REPO, GITHUB_REF, GITHUB_PATH)
    commandes_dict = load_commandes(text)
    st.success(f"✅ {len(commandes_dict)} commandes chargées depuis GitHub (auto-sync).")
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 404:
        cmd_error = (
            f"⚠️ Fichier non trouvé : `{GITHUB_PATH}`\n\n"
            f"Vérifiez que le fichier existe bien dans votre repo à cet emplacement.\n"
            f"URL testée : {_raw_url(GITHUB_OWNER, GITHUB_REPO, GITHUB_REF, GITHUB_PATH)}"
        )
    else:
        cmd_error = f"Erreur HTTP {e.response.status_code} : {e}"
    st.error(cmd_error)
except Exception as e:
    cmd_error = f"Erreur de synchronisation GitHub : {e}"
    st.error(cmd_error)

# Bouton pour forcer rechargement
colA, colB = st.columns([1, 4])
if colA.button("🔄 Recharger les commandes (GitHub)"):
    fetch_commandes_text.clear()
    st.rerun()
with colB:
    st.write(
        f"**Source** : `{GITHUB_OWNER}/{GITHUB_REPO}` — **Branche** : `{GITHUB_REF}` — **Fichier** : `{GITHUB_PATH}`"
    )

# Afficher les commandes chargées
if commandes_dict:
    st.subheader(f"📋 Commandes disponibles ({len(commandes_dict)})")
    
    # Convertir en DataFrame pour affichage
    commandes_list = []
    for order_id, data in commandes_dict.items():
        row = {"numero_commande": order_id}
        row.update(data)
        commandes_list.append(row)
    
    if commandes_list:
        df_commandes = pd.DataFrame(commandes_list)
        
        # Afficher avec possibilité de recherche
        search = st.text_input("🔍 Rechercher une commande", "")
        if search:
            mask = df_commandes.astype(str).apply(lambda x: x.str.contains(search, case=False, na=False)).any(axis=1)
            df_filtered = df_commandes[mask]
            st.write(f"**{len(df_filtered)}** commande(s) trouvée(s)")
            st.dataframe(df_filtered, use_container_width=True, height=300)
        else:
            st.dataframe(df_commandes, use_container_width=True, height=300)
        
        # Bouton pour télécharger les commandes en CSV
        csv = df_commandes.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Télécharger les commandes (CSV)",
            data=csv,
            file_name="commandes_chargees.csv",
            mime="text/csv",
        )
else:
    st.warning("⚠️ Aucune commande chargée. Vérifiez la synchronisation GitHub.")

st.divider()

# =========================
# XML input & traitement
# =========================
xml_file = st.file_uploader("📄 Déposez votre XML (multi-contrats, gros volumes OK)", type=["xml"])
go = st.button("🚀 Corriger le XML", type="primary", disabled=not xml_file or not commandes_dict)

if go:
    if not commandes_dict:
        st.warning("Aucune commande disponible (la synchro GitHub a échoué).")
        st.stop()

    st.info(f"🔄 Traitement en cours avec {len(commandes_dict)} commandes disponibles...")
    
    xml_bytes = xml_file.read()
    try:
        fixed_bytes, recaps, log = process_all(xml_bytes, commandes_dict)
    except Exception as e:
        st.error(f"Erreur traitement: {e}")
        st.stop()

    # Résumé
    n = log.get("contracts_detected", 0)
    matched = sum(1 for r in recaps if r.get("matched"))
    st.success(f"✅ {n} contrats détectés | {matched} appariés avec les commandes | {n - matched} non appariés")
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

    # XML corrigé (encodage d'origine préservé)
    st.download_button(
        "⬇️ XML corrigé",
        data=fixed_bytes,
        file_name=xml_file.name.replace(".xml", "_fixed.xml"),
        mime="application/xml",
    )

st.caption("Synchro GitHub publique → commandes (auto). Déposez seulement le XML. Détection namespace-agnostique. Upsert si balise absente. Encodage préservé.")
