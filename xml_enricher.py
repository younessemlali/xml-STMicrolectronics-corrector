#!/usr/bin/env python3
"""
Script d'enrichissement XML PIXID - STMicroelectronics
Enrichit TOUS les contrats XML avec les données extraites des emails
Version lxml avec upsert effectif : ÉCRIT réellement les modifications
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
    
    # Patterns pour numéros de commande (RT prioritaire pour PIXID)
    ORDER_PATTERNS = [r'(RT\d{6})', r'(CR\d{6})', r'(CD\d{6})']
    
    # Regex pour classification (fallback)
    CLASS_RE = re.compile(r'^[A-E]\d{1,2}$')
    
    # XPath namespace-agnostiques
    XP_CTX = "//*[local-name()='ReferenceInformation'][*[local-name()='OrderId']/*[local-name()='IdValue']]/.."
    XP_ORDER = ".//*[local-name()='ReferenceInformation']/*[local-name()='OrderId']/*[local-name()='IdValue']"
    XP_COEFF = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionCoefficient']"
    XP_LEVEL = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionLevel']"
    XP_STATUS = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionStatus']/*[local-name()='Code']"
    
    def __init__(self, json_path: str):
        """
        Initialise l'enrichisseur avec le fichier JSON des commandes
        
        Args:
            json_path: Chemin vers le fichier commandes_stm.json
        """
        self.commandes_data = self._load_commandes(json_path)
        print(f"✅ {len(self.commandes_data)} commandes chargées depuis {json_path}")
    
    def _load_commandes(self, json_path: str) -> Dict[str, dict]:
        """
        Charge les commandes depuis le fichier JSON
        
        Returns:
            Dictionnaire {numero_commande: {data}}
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Créer un dictionnaire indexé par numéro de commande
        commandes = {}
        for cmd in data.get('commandes', []):
            num = cmd.get('numero_commande')
            if num:
                commandes[num] = cmd
        
        return commandes
    
    def _parse_tree(self, xml_bytes: bytes) -> etree._ElementTree:
        """
        Parse le XML avec parser robuste
        
        Args:
            xml_bytes: Contenu XML en bytes
            
        Returns:
            arbre lxml
        """
        parser = etree.XMLParser(remove_blank_text=True, recover=True, huge_tree=True)
        return etree.parse(BytesIO(xml_bytes), parser)
    
    def _xget(self, ctx: etree.Element, xpath: str) -> str:
        """
        Extrait le texte d'un élément via XPath
        
        Args:
            ctx: Contexte lxml
            xpath: XPath avec local-name()
            
        Returns:
            Texte de l'élément ou chaîne vide
        """
        nodes = ctx.xpath(xpath)
        return (nodes[0].text or '').strip() if nodes and nodes[0].text else ''
    
    def _xupsert(self, ctx: etree.Element, ln_path: str, value: str) -> bool:
        """
        Upsert : crée ou met à jour un élément via XPath local-name()
        
        CRITIQUE : Cette fonction ÉCRIT réellement dans l'arbre XML.
        Si la balise n'existe pas, elle la crée dans la bonne hiérarchie
        en préservant le namespace du parent.
        
        Args:
            ctx: Contexte lxml parent
            ln_path: XPath avec local-name(), ex: ".//*[local-name()='PositionCoefficient']"
            value: Valeur à écrire
            
        Returns:
            True si succès
        """
        try:
            # Extraire les noms de tags depuis le XPath local-name()
            # Ex: ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionCoefficient']"
            # → ['PositionCharacteristics', 'PositionCoefficient']
            parts = [seg.split("'")[1] for seg in ln_path.split("local-name()='")[1:]]
            
            if not parts:
                return False
            
            # Naviguer/créer la hiérarchie
            current = ctx
            for name in parts:
                # Chercher si l'élément existe déjà
                found = current.xpath(f"./*[local-name()='{name}']")
                
                if found:
                    current = found[0]
                else:
                    # Créer l'élément dans le namespace du parent
                    ns = current.nsmap.get(None)
                    tag = f"{{{ns}}}{name}" if ns else name
                    current = etree.SubElement(current, tag)
            
            # Écrire la valeur
            current.text = value
            return True
            
        except Exception as e:
            print(f"   ⚠️  Erreur xupsert: {e}")
            return False
    
    def _extract_order_id_from_text(self, text: str) -> Optional[str]:
        """
        Extrait le numéro de commande d'un texte avec les patterns définis
        
        Args:
            text: Texte contenant potentiellement un numéro de commande
            
        Returns:
            Numéro de commande (RT/CR/CD + 6 chiffres) ou None
        """
        for pattern in self.ORDER_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None
    
    def find_all_order_ids_in_xml(self, xml_path: str) -> List[Dict]:
        """
        Recherche TOUS les contrats dans le fichier XML via ReferenceInformation
        
        Args:
            xml_path: Chemin vers le fichier XML
            
        Returns:
            Liste de dictionnaires avec order_id, assignment_id, context
        """
        try:
            # Lire le fichier en bytes
            with open(xml_path, 'rb') as f:
                xml_bytes = f.read()
            
            tree = self._parse_tree(xml_bytes)
            contexts = tree.xpath(self.XP_CTX)
            
            contracts_found = []
            
            for context in contexts:
                order_id_text = self._xget(context, self.XP_ORDER)
                order_id = self._extract_order_id_from_text(order_id_text)
                
                if order_id:
                    # Extraire AssignmentId (optionnel)
                    assign_xpath = ".//*[local-name()='ReferenceInformation']/*[local-name()='AssignmentId']/*[local-name()='IdValue']"
                    assign_id = self._xget(context, assign_xpath) or "N/A"
                    
                    contracts_found.append({
                        'order_id': order_id,
                        'assignment_id': assign_id,
                        'context': context
                    })
            
            # Logs détaillés
            print(f"✅ {len(contracts_found)} contrat(s) détecté(s) dans le XML")
            
            if contracts_found:
                # Afficher échantillon des OrderIds
                sample_size = min(10, len(contracts_found))
                sample_ids = [c['order_id'] for c in contracts_found[:sample_size]]
                print(f"   Exemple OrderIds: {', '.join(sample_ids)}")
                if len(contracts_found) > sample_size:
                    print(f"   ... et {len(contracts_found) - sample_size} autres contrats")
            else:
                print("   ⚠️  Aucun contrat détecté. Vérifiez que le XML contient:")
                print("       - Des éléments ReferenceInformation")
                print("       - Avec OrderId/IdValue contenant RT/CR/CD + 6 chiffres")
            
            return contracts_found
            
        except Exception as e:
            print(f"❌ Erreur lors de la lecture du XML: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def enrich_xml(self, xml_path: str, output_path: str, progress_callback=None) -> Tuple[bool, str, Dict]:
        """
        Enrichit TOUS les contrats du fichier XML avec les données PIXID
        
        ÉCRIT EFFECTIVEMENT les modifications dans le fichier XML de sortie.
        
        Args:
            xml_path: Chemin vers le fichier XML source
            output_path: Chemin vers le fichier XML enrichi
            progress_callback: Fonction callback(current, total) pour progression
            
        Returns:
            (succès: bool, message: str, stats: dict)
        """
        try:
            # Lire le fichier en bytes
            with open(xml_path, 'rb') as f:
                xml_bytes = f.read()
            
            # Parser
            tree = self._parse_tree(xml_bytes)
            
            # Récupérer l'encodage original
            encoding = tree.docinfo.encoding or 'iso-8859-1'
            print(f"📄 Encodage détecté: {encoding}")
            
            # Trouver tous les contextes de contrats
            contexts = tree.xpath(self.XP_CTX)
            
            if not contexts:
                return False, "Aucun contrat détecté dans le XML", {
                    'total': 0,
                    'enrichis': 0,
                    'non_trouves': 0,
                    'upd_coeff': 0,
                    'upd_status': 0,
                    'details': []
                }
            
            print(f"✅ {len(contexts)} contrat(s) détecté(s)")
            
            # Compteurs de modifications RÉELLES
            upd_coeff = 0
            upd_status = 0
            order_ids_modified = []
            
            # Statistiques
            stats = {
                'total': len(contexts),
                'enrichis': 0,
                'non_trouves': 0,
                'upd_coeff': 0,
                'upd_status': 0,
                'details': []
            }
            
            # Enrichir chaque contrat
            for idx, ctx in enumerate(contexts):
                # Callback progression
                if progress_callback:
                    progress_callback(idx + 1, len(contexts))
                
                # Extraire OrderId
                order_id_text = self._xget(ctx, self.XP_ORDER)
                order_id = self._extract_order_id_from_text(order_id_text)
                
                if not order_id:
                    continue
                
                # Récupérer la commande
                cmd = self.commandes_data.get(order_id)
                
                detail = {
                    'OrderId': order_id,
                    'PositionCoefficient': 'N/A',
                    'PositionStatusCode': 'N/A',
                    'matched': False,
                    'note': ''
                }
                
                modified = False
                
                # 1) CLASSIFICATION → PositionCoefficient
                coeff = self._xget(ctx, self.XP_COEFF)
                level = self._xget(ctx, self.XP_LEVEL)
                
                if cmd and (cmd.get('classification_interimaire') or '').strip():
                    # Commande trouvée avec classification
                    classif_value = cmd['classification_interimaire'].strip()
                    success = self._xupsert(ctx, self.XP_COEFF, classif_value)
                    
                    if success:
                        upd_coeff += 1
                        modified = True
                        detail['PositionCoefficient'] = classif_value
                        detail['note'] = 'depuis JSON'
                        print(f"   ✓ {order_id} - PositionCoefficient → '{classif_value}' (depuis JSON)")
                
                elif not cmd and not coeff and self.CLASS_RE.match(level or ''):
                    # Pas de commande mais fallback possible
                    success = self._xupsert(ctx, self.XP_COEFF, level)
                    
                    if success:
                        upd_coeff += 1
                        modified = True
                        detail['PositionCoefficient'] = level
                        detail['note'] = 'copié depuis PositionLevel'
                        print(f"   ✓ {order_id} - PositionCoefficient → '{level}' (depuis PositionLevel)")
                
                # 2) STATUT → PositionStatus/Code
                if cmd and (cmd.get('statut') or '').strip():
                    statut_value = cmd['statut'].strip()
                    # Extraire le code (avant le tiret si présent)
                    code_statut = statut_value.split('-')[0].strip() if '-' in statut_value else statut_value
                    
                    success = self._xupsert(ctx, self.XP_STATUS, code_statut)
                    
                    if success:
                        upd_status += 1
                        modified = True
                        detail['PositionStatusCode'] = code_statut
                        print(f"   ✓ {order_id} - PositionStatus/Code → '{code_statut}'")
                
                # Mettre à jour stats
                if cmd:
                    stats['enrichis'] += 1
                    detail['matched'] = True
                else:
                    stats['non_trouves'] += 1
                
                if modified:
                    order_ids_modified.append(order_id)
                
                stats['details'].append(detail)
            
            # Mettre à jour les compteurs
            stats['upd_coeff'] = upd_coeff
            stats['upd_status'] = upd_status
            
            # CRITIQUE : Sauvegarder le XML avec les modifications
            print(f"\n💾 Sauvegarde du XML enrichi...")
            
            tree.write(
                output_path,
                encoding=encoding,
                pretty_print=True,
                xml_declaration=True
            )
            
            print(f"✅ Fichier sauvegardé: {output_path}")
            
            # Logs finaux
            print(f"\n📊 MODIFICATIONS EFFECTIVES:")
            print(f"   • Contrats détectés: {stats['total']}")
            print(f"   • PositionCoefficient MAJ: {upd_coeff}")
            print(f"   • PositionStatus/Code MAJ: {upd_status}")
            
            if order_ids_modified:
                sample = order_ids_modified[:10]
                print(f"   • OrderIds modifiés: {', '.join(sample)}")
                if len(order_ids_modified) > 10:
                    print(f"     ... et {len(order_ids_modified) - 10} autres")
            
            if upd_coeff == 0 and upd_status == 0:
                print(f"\n⚠️  WARNING: Aucune modification écrite alors que {stats['enrichis']} commandes existent!")
                print(f"   Vérifiez que les données 'classification_interimaire' et 'statut' ne sont pas vides.")
            
            # Message final
            message = f"✅ XML enrichi avec succès!\n\n"
            message += f"📊 Statistiques:\n"
            message += f"  • Total contrats: {stats['total']}\n"
            message += f"  • Enrichis (avec données JSON): {stats['enrichis']}\n"
            message += f"  • Non trouvés dans JSON: {stats['non_trouves']}\n"
            message += f"  • PositionCoefficient MAJ: {upd_coeff}\n"
            message += f"  • PositionStatus/Code MAJ: {upd_status}"
            
            return True, message, stats
                
        except etree.ParseError as e:
            return False, f"Erreur de parsing XML: {e}", {
                'total': 0, 'enrichis': 0, 'non_trouves': 0, 'upd_coeff': 0, 'upd_status': 0, 'details': []
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Erreur inattendue: {e}", {
                'total': 0, 'enrichis': 0, 'non_trouves': 0, 'upd_coeff': 0, 'upd_status': 0, 'details': []
            }
    
    def get_commande_info(self, order_id: str) -> Optional[dict]:
        """
        Récupère les informations d'une commande
        
        Args:
            order_id: Numéro de commande
            
        Returns:
            Dictionnaire avec les infos ou None
        """
        return self.commandes_data.get(order_id)
    
    def search_commandes(self, query: str) -> list:
        """
        Recherche des commandes par numéro, agence ou unité
        
        Args:
            query: Terme de recherche
            
        Returns:
            Liste des commandes correspondantes
        """
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
    """Fonction principale pour test en ligne de commande"""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python xml_enricher.py <commandes.json> <fichier.xml> [output.xml]")
        print("\nExemple:")
        print("  python xml_enricher.py commandes_stm.json input.xml output_enrichi.xml")
        sys.exit(1)
    
    json_path = sys.argv[1]
    xml_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else "output_enrichi.xml"
    
    # Créer l'enrichisseur
    enricher = XMLEnricher(json_path)
    
    # Enrichir le XML
    success, message, stats = enricher.enrich_xml(xml_path, output_path)
    
    if success:
        print(f"\n✅ Fichier enrichi sauvegardé: {output_path}")
        print(f"\n📋 Récapitulatif:")
        print(f"   • Total contrats: {stats['total']}")
        print(f"   • PositionCoefficient MAJ: {stats['upd_coeff']}")
        print(f"   • PositionStatus/Code MAJ: {stats['upd_status']}")
        
        # Afficher détails (limité)
        if stats['details']:
            print(f"\n📄 Détails par contrat (premiers 20):")
            print(f"{'OrderId':<12} {'Coefficient':<15} {'StatusCode':<12} {'Note'}")
            print("-" * 70)
            for detail in stats['details'][:20]:
                print(f"{detail['OrderId']:<12} "
                      f"{detail['PositionCoefficient']:<15} "
                      f"{detail['PositionStatusCode']:<12} "
                      f"{detail['note']}")
            if len(stats['details']) > 20:
                print(f"... et {len(stats['details']) - 20} autres contrats")
    else:
        print(f"\n❌ Échec: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
