#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xml_enricher.py — Enrichisseur PIXID HR-XML/SIDES (multi-contrats)
Modifie exactement 2 balises par contrat, avec jointure sur les "commandes":
  1) PositionCharacteristics/PositionCoefficient
  2) PositionCharacteristics/PositionStatus/Code

✅ Points clés
- Détection namespace-agnostique (XPath avec local-name())
- Parser robuste lxml (recover=True, huge_tree=True)
- Upsert : crée la balise si absente (dans le bon namespace)
- Fallback: si aucune commande et PositionCoefficient vide & PositionLevel ~ ^[A-E]\d{1,2}$ → copie Level → Coefficient
- Encodage préservé (réécriture avec tree.docinfo.encoding)
- CSV récapitulatif par contrat

Usage:
  python xml_enricher.py --xml in.xml --cmd commandes.json --out out.xml --csv recap.csv
  python xml_enricher.py --xml in.xml --cmd commandes.csv  --out out.xml --csv recap.csv

Commandes JSON: liste d'objets ou dict {numero_commande: {...}} ; CSV: colonne "numero_commande" requise.
Champs utilisés par contrat: classification_interimaire, statut
"""

from lxml import etree
from io import BytesIO
import argparse, sys, json, csv, re
from typing import Dict, Any, List, Tuple, Optional

# ------------------ Constantes & XPaths (namespace-agnostiques) ------------------

CLASS_RE = re.compile(r'^[A-E]\d{1,2}$')

XP_CTX    = "//*[local-name()='ReferenceInformation'][*[local-name()='OrderId']/*[local-name()='IdValue']]/.."
XP_ORDER  = ".//*[local-name()='ReferenceInformation']/*[local-name()='OrderId']/*[local-name()='IdValue']"
XP_ASSIGN = ".//*[local-name()='ReferenceInformation']/*[local-name()='AssignmentId']/*[local-name()='IdValue']"
XP_LEVEL  = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionLevel']"
XP_COEFF  = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionCoefficient']"
XP_STATUS = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionStatus']/*[local-name()='Code']"

# ------------------ Helpers parsing / writing ------------------

def parse_tree(xml_bytes: bytes) -> etree._ElementTree:
    parser = etree.XMLParser(remove_blank_text=True, recover=True, huge_tree=True)
    return etree.parse(BytesIO(xml_bytes), parser)

def write_tree(tree: etree._ElementTree) -> bytes:
    enc = tree.docinfo.encoding or "UTF-8"
    return etree.tostring(tree, encoding=enc, pretty_print=True, xml_declaration=True)

# ------------------ Helpers XPath (lecture / upsert) ------------------

def xget(ctx: etree._Element, xp: str) -> str:
    try:
        n = ctx.xpath(xp)
    except Exception:
        return ""
    return (n[0].text or "").strip() if n and n[0].text is not None else ""

def _find_default_ns(el: etree._Element) -> Optional[str]:
    cur = el
    # remonte jusqu'à trouver un namespace par défaut
    while cur is not None:
        ns = cur.nsmap.get(None)
        if ns:
            return ns
        cur = cur.getparent()
    return None

def xupsert(ctx: etree._Element, ln_path: str, value: str) -> None:
    """
    ln_path est une chaîne XPath utilisant local-name(), par ex. XP_COEFF / XP_STATUS.
    Crée récursivement la hiérarchie si absente, en respectant le namespace par défaut de l'ancêtre.
    """
    # Extraire la liste des noms locaux ("PositionCharacteristics", "PositionCoefficient", ...)
    parts: List[str] = []
    tmp = ln_path
    while True:
        i = tmp.find("local-name()='")
        if i == -1:
            break
        j = i + len("local-name()='")
        k = tmp.find("'", j)
        if k == -1:
            break
        name = tmp[j:k]
        parts.append(name)
        tmp = tmp[k+1:]
    if not parts:
        # si ln_path ne contenait pas local-name(), on tente un xpath direct
        nodes = ctx.xpath(ln_path)
        if nodes:
            nodes[0].text = value
        else:
            # sans info, on ne sait pas créer correctement -> on ne fait rien
            return
        return

    current = ctx
    for name in parts:
        found = current.xpath(f"./*[local-name()='{name}']")
        if found:
            current = found[0]
            continue
        # créer élément dans le namespace par défaut disponible
        ns = _find_default_ns(current)
        tag = f"{{{ns}}}{name}" if ns else name
        current = etree.SubElement(current, tag)
    current.text = value

# ------------------ Commandes (chargement & normalisation) ------------------

def norm_key(k: Any) -> str:
    if k is None:
        return ""
    return "".join(str(k).strip().upper().split())

def load_commandes(path: str, key_field: str = "numero_commande") -> Dict[str, Dict[str, Any]]:
    path = str(path)
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            # { "RT001400": {...}, ... }
            return { norm_key(k): v for k, v in data.items() }
        elif isinstance(data, list):
            out = {}
            for row in data:
                key = norm_key(row.get(key_field))
                if key:
                    out[key] = row
            return out
        else:
            raise ValueError("JSON inattendu: liste d'objets ou dict attendu.")
    elif path.lower().endswith(".csv"):
        out = {}
        # Sniff le séparateur (auto)
        with open(path, "r", encoding="utf-8", newline="") as f:
            sample = f.read(2048)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            if key_field not in reader.fieldnames:
                raise ValueError(f"Colonne '{key_field}' absente du CSV.")
            for row in reader:
                key = norm_key(row.get(key_field))
                if key:
                    out[key] = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        return out
    else:
        raise ValueError("Fichier commandes non supporté (extensions .json ou .csv attendues).")

# ------------------ Enrichissement (2 balises uniquement) ------------------

def process_all(xml_bytes: bytes,
                commandes: Dict[str, Dict[str, Any]],
                classification_regex: str = r"^[A-E]\d{1,2}$",
                ) -> Tuple[bytes, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Retourne: (xml_corrige_bytes, recaps_par_contrat, log_global)
    """
    tree = parse_tree(xml_bytes)
    contexts = tree.xpath(XP_CTX)
    recaps: List[Dict[str, Any]] = []
    upd_coeff = 0
    upd_status = 0
    modified_ids: List[str] = []
    unmatched_sample: List[str] = []

    CLASS_RE = re.compile(classification_regex)

    for ctx in contexts:
        order_id = xget(ctx, XP_ORDER)
        assign_id = xget(ctx, XP_ASSIGN)
        key = norm_key(order_id)
        row = commandes.get(key)

        before_coeff  = xget(ctx, XP_COEFF)
        before_status = xget(ctx, XP_STATUS)
        level         = xget(ctx, XP_LEVEL)

        # 1) PositionCoefficient
        if row and (row.get("classification_interimaire") or "").strip():
            xupsert(ctx, XP_COEFF, row["classification_interimaire"].strip())
        elif not row and not before_coeff and CLASS_RE.match(level or ""):
            # fallback Level -> Coefficient
            xupsert(ctx, XP_COEFF, level)

        # 2) PositionStatus/Code
        if row and (row.get("statut") or "").strip():
            xupsert(ctx, XP_STATUS, row["statut"].strip())

        after_coeff  = xget(ctx, XP_COEFF)
        after_status = xget(ctx, XP_STATUS)

        changed = (after_coeff != before_coeff) or (after_status != before_status)
        if changed:
            modified_ids.append(order_id)
            if after_coeff != before_coeff:  upd_coeff  += 1
            if after_status != before_status: upd_status += 1
        elif not row and len(unmatched_sample) < 10:
            unmatched_sample.append(order_id)

        note = ""
        if not row and not before_coeff and after_coeff == level and CLASS_RE.match(level or ""):
            note = "coefficient copié depuis PositionLevel"

        recaps.append({
            "OrderId": order_id,
            "AssignmentId": assign_id,
            "PositionCoefficient_before": before_coeff,
            "PositionCoefficient_after":  after_coeff,
            "PositionStatusCode_before":  before_status,
            "PositionStatusCode_after":   after_status,
            "matched": bool(row),
            "note": note
        })

    out_bytes = write_tree(tree)
    log = {
        "contracts_detected": len(contexts),
        "coeff_updates": upd_coeff,
        "status_updates": upd_status,
        "modified_ids_sample": modified_ids[:10],
        "unmatched_sample": unmatched_sample
    }
    if commandes and upd_coeff == 0 and upd_status == 0:
        log["warning"] = "Commandes chargées mais 0 mise à jour — vérifiez la normalisation des clés (espaces, casse, zéros)."

    return out_bytes, recaps, log

# ------------------ CLI ------------------

def main():
    ap = argparse.ArgumentParser(description="Enrichisseur PIXID HR-XML/SIDES (2 balises uniquement).")
    ap.add_argument("--xml", required=True, help="Chemin du fichier XML d'entrée")
    ap.add_argument("--cmd", required=True, help="Fichier commandes (.json ou .csv) avec 'numero_commande'")
    ap.add_argument("--out", required=True, help="Chemin du XML corrigé de sortie")
    ap.add_argument("--csv", required=False, help="Chemin CSV récapitulatif (facultatif)")
    ap.add_argument("--class-re", default=r"^[A-E]\d{1,2}$", help="Regex de classification pour fallback Level->Coefficient")
    args = ap.parse_args()

    # Lire XML bytes (respecter encodage déclaré, pas d'ouverture en texte)
    with open(args.xml, "rb") as f:
        xml_bytes = f.read()

    # Charger commandes
    commandes = load_commandes(args.cmd, key_field="numero_commande")

    # Traiter
    out_bytes, recaps, log = process_all(xml_bytes, commandes, classification_regex=args.class-re if hasattr(args, "class-re") else args.class_re)

    # Écrire sortie XML (encodage préservé)
    with open(args.out, "wb") as f:
        f.write(out_bytes)

    # CSV recap optionnel
    if args.csv:
        import csv as _csv
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            writer = _csv.DictWriter(f, fieldnames=[
                "OrderId","AssignmentId",
                "PositionCoefficient_before","PositionCoefficient_after",
                "PositionStatusCode_before","PositionStatusCode_after",
                "matched","note"
            ])
            writer.writeheader()
            writer.writerows(recaps)

    # Logs console
    print(f"Contrats détectés: {log['contracts_detected']} | Coefficient MAJ: {log['coeff_updates']} | Statut MAJ: {log['status_updates']}")
    if log.get("modified_ids_sample"):
        print("OrderId modifiés (échantillon):", ", ".join([str(x) for x in log["modified_ids_sample"]]))
    if log.get("unmatched_sample"):
        print("Non appariés (échantillon):", ", ".join([str(x) for x in log["unmatched_sample"]]))
    if log.get("warning"):
        print("⚠️", log["warning"], file=sys.stderr)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
