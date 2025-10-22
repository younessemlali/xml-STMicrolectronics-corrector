#!/usr/bin/env python3
"""
Script d'enrichissement XML PIXID - STMicroelectronics
Version CORRIGÉE : parse une seule fois et garde le même tree
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from io import BytesIO

try:
    from lxml import etree
except ImportError:
    raise ImportError("Le module lxml est requis. Installez-le avec: pip install lxml")


class XMLEnricher:
    """Classe pour enrichir les fichiers XML avec les données PIXID"""
    
    ORDER_PATTERNS = [r'(RT\d{6})', r'(CR\d{6})', r'(CD\d{6})']
    CLASS_RE = re.compile(r'^[A-E]\d{1,2}$')
    
    # XPath namespace-agnostiques
    XP_CTX = "//*[local-name()='ReferenceInformation'][*[local-name()='OrderId']/*[local-name()='IdValue']]/.."
    XP_ORDER = ".//*[local-name()='ReferenceInformation']/*[local-name()='OrderId']/*[local-name()='IdValue']"
    XP_COEFF = ".//*[local-name()='PositionCoefficient']"
    XP_LEVEL = ".//*[local-name()='PositionLevel']"
    XP_STATUS = ".//*[local-name()='PositionStatus']/*[local-name()='Code']"
    
    def __init__(self, json_path: str):
        self.commandes_data = self._load_commandes(json_path)
        print(f"✅ {len(self.commandes_data)} commandes chargées")
    
    def _load_commandes(self, json_path: str) -> Dict[str, dict]:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        commandes = {}
        for cmd in data.get('commandes', []):
            num = cmd.get('numero_commande')
            if num:
                commandes[num] = cmd
        return commandes
    
    def _parse_tree(self, xml_bytes: bytes) -> etree._ElementTree:
        parser = etree.XMLParser(remove_blank_text=True, recover=True, huge_tree=True)
        return etree.parse(BytesIO(xml_bytes), parser)
    
    def _xget(self, ctx: etree.Element, xpath: str) -> str:
        nodes = ctx.xpath(xpath)
        return (nodes[0].text or '').strip() if nodes and nodes[0].text else ''
    
    def _xupsert(self, ctx: etree.Element, ln_path: str, value: str) -> bool:
        """Upsert avec logs"""
        try:
            parts = [seg.split("'")[1] for seg in ln_path.split("local-name()='")[1:]]
            
            if not parts:
                return False
            
            current = ctx
            for name in parts:
                found = current.xpath(f"./*[local-name()='{name}']")
                
                if found:
                    current = found[0]
                else:
                    ns = current.nsmap.get(None)
                    tag = f"{{{ns}}}{name}" if ns else name
                    current = etree.SubElement(current, tag)
            
            current.text = value
            return True
            
        except Exception as e:
            print(f"      ❌ Erreur xupsert: {e}")
            return False
    
    def _extract_order_id_from_text(self, text: str) -> Optional[str]:
        for pattern in self.ORDER_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None
    
    def find_all_order_ids_in_xml(self, xml_path: str) -> List[Dict]:
        """NE PLUS UTILISER - Obsolète"""
        # Cette méthode est gardée pour compatibilité mais ne doit plus être utilisée
        # Utiliser enrich_xml() directement
        return []
    
    def enrich_xml(self, xml_path: str, output_path: str, progress_callback=None) -> Tuple[bool, str, Dict]:
        """
        PARSE UNE SEULE FOIS et enrichit directement
        """
        try:
            # 1. LIRE LE FICHIER UNE SEULE FOIS
            print(f"📄 Lecture du fichier XML...")
            with open(xml_path, 'rb') as f:
                xml_bytes = f.read()
            
            # 2. PARSER UNE SEULE FOIS
            print(f"🔍 Parsing XML...")
            tree = self._parse_tree(xml_bytes)
            encoding = tree.docinfo.encoding or 'iso-8859-1'
            print(f"   Encodage: {encoding}")
            
            # 3. TROUVER TOUS LES CONTEXTES (sur CE tree)
            print(f"🔍 Recherche des contrats...")
            contexts = tree.xpath(self.XP_CTX)
            
            if not contexts:
                return False, "Aucun contrat détecté", {
                    'total': 0, 'enrichis': 0, 'upd_coeff': 0, 'upd_status': 0, 'details': []
                }
            
            print(f"✅ {len(contexts)} contrat(s) détecté(s)")
            
            # 4. COMPTEURS
            upd_coeff = 0
            upd_status = 0
            order_ids_modified = []
            
            stats = {
                'total': len(contexts),
                'enrichis': 0,
                'non_trouves': 0,
                'upd_coeff': 0,
                'upd_status': 0,
                'details': []
            }
            
            # 5. ENRICHIR CHAQUE CONTEXTE (sur CE tree)
            print(f"\n🔧 Enrichissement en cours...")
            
            for idx, ctx in enumerate(contexts):
                if progress_callback:
                    progress_callback(idx + 1, len(contexts))
                
                # Extraire OrderId
                order_id_text = self._xget(ctx, self.XP_ORDER)
                order_id = self._extract_order_id_from_text(order_id_text)
                
                if not order_id:
                    continue
                
                # Récupérer commande
                cmd = self.commandes_data.get(order_id)
                
                # Logs détaillés pour les 3 premiers
                verbose = (idx < 3)
                
                if verbose:
                    print(f"\n🔍 {order_id}")
                    print(f"   Commande: {'✅' if cmd else '❌'}")
                    if cmd:
                        print(f"   classification: '{cmd.get('classification_interimaire')}'")
                        print(f"   statut: '{cmd.get('statut')}'")
                
                detail = {
                    'OrderId': order_id,
                    'PositionCoefficient': 'N/A',
                    'PositionStatusCode': 'N/A',
                    'matched': False,
                    'note': ''
                }
                
                modified = False
                
                # A) CLASSIFICATION → PositionCoefficient
                if cmd and (cmd.get('classification_interimaire') or '').strip():
                    classif_value = cmd['classification_interimaire'].strip()
                    
                    if verbose:
                        print(f"   🔧 Écriture PositionCoefficient: '{classif_value}'")
                    
                    success = self._xupsert(ctx, self.XP_COEFF, classif_value)
                    
                    if success:
                        upd_coeff += 1
                        modified = True
                        detail['PositionCoefficient'] = classif_value
                        detail['note'] = 'depuis JSON'
                        
                        if verbose:
                            print(f"      ✅ ÉCRIT")
                        else:
                            if idx < 10:  # 10 premiers
                                print(f"   ✓ {order_id} - PositionCoefficient → '{classif_value}'")
                
                else:
                    # Fallback PositionLevel
                    coeff = self._xget(ctx, self.XP_COEFF)
                    level = self._xget(ctx, self.XP_LEVEL)
                    
                    if not cmd and not coeff and self.CLASS_RE.match(level or ''):
                        if verbose:
                            print(f"   🔧 Fallback PositionLevel: '{level}'")
                        
                        success = self._xupsert(ctx, self.XP_COEFF, level)
                        
                        if success:
                            upd_coeff += 1
                            modified = True
                            detail['PositionCoefficient'] = level
                            detail['note'] = 'copié depuis PositionLevel'
                            
                            if verbose:
                                print(f"      ✅ ÉCRIT")
                
                # B) STATUT → PositionStatus/Code
                if cmd and (cmd.get('statut') or '').strip():
                    statut_value = cmd['statut'].strip()
                    code_statut = statut_value.split('-')[0].strip() if '-' in statut_value else statut_value
                    
                    if verbose:
                        print(f"   🔧 Écriture PositionStatus/Code: '{code_statut}'")
                    
                    success = self._xupsert(ctx, self.XP_STATUS, code_statut)
                    
                    if success:
                        upd_status += 1
                        modified = True
                        detail['PositionStatusCode'] = code_statut
                        
                        if verbose:
                            print(f"      ✅ ÉCRIT")
                        else:
                            if idx < 10:
                                print(f"   ✓ {order_id} - PositionStatus/Code → '{code_statut}'")
                
                # Stats
                if cmd:
                    stats['enrichis'] += 1
                    detail['matched'] = True
                else:
                    stats['non_trouves'] += 1
                
                if modified:
                    order_ids_modified.append(order_id)
                
                stats['details'].append(detail)
            
            stats['upd_coeff'] = upd_coeff
            stats['upd_status'] = upd_status
            
            # 6. SAUVEGARDER LE TREE MODIFIÉ
            print(f"\n💾 Sauvegarde XML...")
            
            tree.write(
                output_path,
                encoding=encoding,
                pretty_print=True,
                xml_declaration=True
            )
            
            print(f"✅ Sauvegardé: {output_path}")
            
            # 7. RÉSULTAT
            print(f"\n📊 RÉSULTAT:")
            print(f"   • Total contrats: {stats['total']}")
            print(f"   • Avec données JSON: {stats['enrichis']}")
            print(f"   • PositionCoefficient MAJ: {upd_coeff}")
            print(f"   • PositionStatus/Code MAJ: {upd_status}")
            
            if order_ids_modified:
                sample = order_ids_modified[:10]
                print(f"   • Modifiés: {', '.join(sample)}")
                if len(order_ids_modified) > 10:
                    print(f"     +{len(order_ids_modified) - 10} autres")
            
            if upd_coeff == 0 and upd_status == 0:
                print(f"\n⚠️  AUCUNE MODIFICATION ÉCRITE!")
                print(f"   Regardez les logs détaillés ci-dessus")
            
            message = f"✅ XML enrichi!\n\n"
            message += f"📊 Statistiques:\n"
            message += f"  • Total: {stats['total']}\n"
            message += f"  • Enrichis: {stats['enrichis']}\n"
            message += f"  • PositionCoefficient MAJ: {upd_coeff}\n"
            message += f"  • PositionStatus/Code MAJ: {upd_status}"
            
            return True, message, stats
                
        except Exception as e:
            print(f"❌ ERREUR: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Erreur: {e}", {
                'total': 0, 'enrichis': 0, 'upd_coeff': 0, 'upd_status': 0, 'details': []
            }
    
    def get_commande_info(self, order_id: str) -> Optional[dict]:
        return self.commandes_data.get(order_id)
    
    def search_commandes(self, query: str) -> list:
        query_lower = query.lower()
        results = []
        for num, data in self.commandes_data.items():
            if (query_lower in num.lower() or
                query_lower in str(data.get('code_agence', '')).lower() or
                query_lower in str(data.get('code_unite', '')).lower()):
                results.append({
                    'numero_commande': num,
                    **data
                })
        return results


def main():
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python xml_enricher.py <commandes.json> <fichier.xml> [output.xml]")
        sys.exit(1)
    
    json_path = sys.argv[1]
    xml_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else "output_enrichi.xml"
    
    enricher = XMLEnricher(json_path)
    success, message, stats = enricher.enrich_xml(xml_path, output_path)
    
    if success:
        print(f"\n✅ Fichier: {output_path}")
        print(f"📊 Modif: {stats['upd_coeff']} coeff | {stats['upd_status']} statut")
    else:
        print(f"\n❌ {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
