# -*- coding: utf-8 -*-
"""
xml_enricher.py — Enrichisseur PIXID HR-XML/SIDES (multi-contrats)
Met à jour exactement 3 balises par contrat:
  1) PositionCharacteristics/PositionCoefficient
  2) PositionCharacteristics/PositionStatus/Code
  3) PositionCharacteristics/PositionStatus/Description

- Détection namespace-agnostique (XPath local-name())
- Parser robuste lxml (recover=True, huge_tree=True)
- Upsert: crée la balise si absente (dans le bon namespace)
- Fallback: si pas de commande & Coefficient vide & Level ~ ^[A-E]\\d{1,2}$ => Level -> Coefficient
- Encodage préservé (réécrit avec tree.docinfo.encoding)
- Normalisation des clés de jointure (strip + upper, supprime espaces)
- Mise à jour de TOUS les <Code>/<Description> sous PositionStatus; création si aucun nœud présent.
"""

from lxml import etree
from io import BytesIO
import re, json, csv
from typing import Dict, Any, List, Tuple, Optional

# --------- XPaths (namespace-agnostiques) ---------
XP_CTX    = "//*[local-name()='ReferenceInformation'][*[local-name()='OrderId']/*[local-name()='IdValue']]/.."
XP_ORDER  = ".//*[local-name()='ReferenceInformation']/*[local-name()='OrderId']/*[local-name()='IdValue']"
XP_ASSIGN = ".//*[local-name()='ReferenceInformation']/*[local-name()='AssignmentId']/*[local-name()='IdValue']"

XP_LEVEL  = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionLevel']"
XP_COEFF  = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionCoefficient']"

XP_STATUS          = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionStatus']"
XP_STATUS_CODE     = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionStatus']/*[local-name()='Code']"
XP_STATUS_DESC     = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionStatus']/*[local-name()='Description']"
XP_STATUS_CODE_ALL = XP_STATUS_CODE
XP_STATUS_DESC_ALL = XP_STATUS_DESC

CLASS_RE = re.compile(r"^[A-E]\\d{1,2}$")

# --------- Mapping code -> libellé (complétez si besoin) ---------
STATUS_LABEL_MAP = {
    "OP": "Opérateur",
    "6A": "Ouvriers",
    # Ajoutez ici d'autres couples si vous en avez (ex: "EM": "Employés")
}

# --------- Parsing / Writing ---------
def _parse(xml_bytes: bytes) -> etree._ElementTree:
    parser = etree.XMLParser(remove_blank_text=True, recover=True, huge_tree=True)
    return etree.parse(BytesIO(xml_bytes), parser)

def _tobytes(tree: etree._ElementTree) -> bytes:
    enc = tree.docinfo.encoding or "UTF-8"
    return etree.tostring(tree, encoding=enc, pretty_print=True, xml_declaration=True)

# --------- Helpers XPath / Upsert ---------
def _xget(ctx: etree._Element, xp: str) -> str:
    try:
        n = ctx.xpath(xp)
    except Exception:
        return ""
    return (n[0].text or "").strip() if n and n[0].text is not None else ""

def _find_default_ns(el: etree._Element) -> Optional[str]:
    cur = el
    while cur is not None:
        ns = cur.nsmap.get(None)
        if ns:
            return ns
        cur = cur.getparent()
    return None

def _xupsert(ctx: etree._Element, ln_path: str, value: str) -> None:
    """
    ln_path = XPath avec local-name(), ex: XP_COEFF ou XP_STATUS_DESC
    Crée proprement la hiérarchie si manquante (dans le bon namespace), puis pose le texte.
    """
    parts: List[str] = []
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

# --------- Commandes (chargement + normalisation) ---------
def _norm_key(k: Any) -> str:
    if k is None: return ""
    return "".join(str(k).strip().upper().split())

def load_commandes(path_or_buf, key_field: str = "numero_commande") -> Dict[str, Dict[str, Any]]:
    """
    Accepte : chemin str vers .json/.csv, ou buffer texte déjà lu.
    Retourne : dict normalisé { ORDERID -> row }
    """
    def dict_from_json_obj(data):
        if isinstance(data, dict):
            return { _norm_key(k): v for k, v in data.items() }
        elif isinstance(data, list):
            out = {}
            for row in data:
                key = _norm_key(row.get(key_field))
                if key: out[key] = row
            return out
        else:
            raise ValueError("JSON inattendu (dict ou list attendu).")

    if isinstance(path_or_buf, str):
        p = path_or_buf.lower()
        if p.endswith(".json"):
            with open(path_or_buf, "r", encoding="utf-8") as f:
                return dict_from_json_obj(json.load(f))
        elif p.endswith(".csv"):
            out = {}
            with open(path_or_buf, "r", encoding="utf-8", newline="") as f:
                sample = f.read(2048); f.seek(0)
                try: dialect = csv.Sniffer().sniff(sample)
                except Exception: dialect = csv.excel
                reader = csv.DictReader(f, dialect=dialect)
                if key_field not in reader.fieldnames:
                    raise ValueError(f"Colonne '{key_field}' absente du CSV.")
                for row in reader:
                    key = _norm_key(row.get(key_field))
                    if key: out[key] = {k:(v.strip() if isinstance(v,str) else v) for k,v in row.items()}
            return out
        else:
            raise ValueError("Extension non supportée (utilisez .json ou .csv).")
    else:
        # buffer texte JSON ou CSV (détecter)
        text = path_or_buf.read()
        if not isinstance(text, str):
            text = text.decode("utf-8", errors="ignore")
        stripped = text.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            return dict_from_json_obj(json.loads(text))
        else:
            out = {}
            reader = csv.DictReader(text.splitlines())
            if key_field not in reader.fieldnames:
                raise ValueError(f"Colonne '{key_field}' absente du CSV.")
            for row in reader:
                key = _norm_key(row.get(key_field))
                if key: out[key] = {k:(v.strip() if isinstance(v,str) else v) for k,v in row.items()}
            return out

# --------- Cœur : 3 champs uniquement ---------
def process_all(xml_bytes: bytes,
                commandes: Dict[str, Dict[str, Any]],
                classification_regex: str = r"^[A-E]\\d{1,2}$"
               ) -> Tuple[bytes, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Retourne: (xml_corrige_bytes, recaps_par_contrat, log_global)
    """
    tree = _parse(xml_bytes)
    contexts = tree.xpath(XP_CTX)
    recaps: List[Dict[str, Any]] = []
    upd_coeff = upd_code = upd_desc = 0
    modified_ids: List[str] = []
    unmatched_sample: List[str] = []

    class_re = re.compile(classification_regex)

    for ctx in contexts:
        order  = _xget(ctx, XP_ORDER)
        assign = _xget(ctx, XP_ASSIGN)
        key    = _norm_key(order)
        row    = commandes.get(key)

        before_c   = _xget(ctx, XP_COEFF)
        before_code= _xget(ctx, XP_STATUS_CODE)
        before_desc= _xget(ctx, XP_STATUS_DESC)
        level      = _xget(ctx, XP_LEVEL)

        # 1) Coefficient
        if row and (row.get("classification_interimaire") or "").strip():
            _xupsert(ctx, XP_COEFF, row["classification_interimaire"].strip())
        elif (not row) and (not before_c) and class_re.match(level or ""):
            _xupsert(ctx, XP_COEFF, level)

        # 2) Statut Code + 3) Description
        code = (row.get("statut") or "").strip() if row else ""
        desc = (row.get("statut_description") or "").strip() if row else ""
        final_desc = ""
        if code:
            # mettre à jour tous les <Code> existants; sinon en créer un
            nodes_code = ctx.xpath(XP_STATUS_CODE_ALL)
            if nodes_code:
                for n in nodes_code: n.text = code
            else:
                _xupsert(ctx, XP_STATUS_CODE, code)
            # description
            final_desc = desc or STATUS_LABEL_MAP.get(code, desc)
            if final_desc:
                nodes_desc = ctx.xpath(XP_STATUS_DESC_ALL)
                if nodes_desc:
                    for n in nodes_desc: n.text = final_desc
                else:
                    _xupsert(ctx, XP_STATUS_DESC, final_desc)

        after_c    = _xget(ctx, XP_COEFF)
        after_code = _xget(ctx, XP_STATUS_CODE)
        after_desc = _xget(ctx, XP_STATUS_DESC)

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
        if (not row) and (not before_c) and (after_c == level) and class_re.match(level or ""):
            note = "coefficient copié depuis PositionLevel"

        recaps.append({
            "OrderId": order, "AssignmentId": assign,
            "PositionCoefficient": after_c,
            "PositionStatusCode": after_code,
            "PositionStatusDescription": after_desc,
            "matched": bool(row), "note": note
        })

    out_bytes = _tobytes(tree)
    log = {
        "contracts_detected": len(contexts),
        "coef_updates": upd_coeff,
        "status_code_updates": upd_code,
        "status_desc_updates": upd_desc,
        "modified_ids_sample": modified_ids[:10],
        "unmatched_sample": unmatched_sample
    }
    if commandes and upd_coeff == 0 and upd_code == 0 and upd_desc == 0:
        log["warning"] = "Commandes chargées mais 0 mise à jour — vérifier la normalisation des clés et le mapping."

    return out_bytes, recaps, log
