#!/usr/bin/env python3
"""
Script d'enrichissement XML PIXID - STMicroelectronics
Enrichit TOUS les contrats XML avec les données extraites des emails
Version conforme HR-XML/SIDES : détection via ReferenceInformation
"""

import json
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, List


class XMLEnricher:
    """Classe pour enrichir les fichiers XML avec les données PIXID"""
    
    # Namespace HR-XML obligatoire
    NS = {'hr': 'http://ns.hr-xml.org/2004-08-02'}
    
    # Patterns pour numéros de commande
    ORDER_PATTERNS = [r'(CR\d{6})', r'(CD\d{6})', r'(RT\d{6})']
    
    # Regex pour classification (fallback)
    CLASSIFICATION_REGEX = r'^[A-E]\d{1,2}$'
    
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
    
    def find_all_order_ids_in_xml(self, xml_path: str) -> List[Dict]:
        """
        Recherche TOUS les contrats dans le fichier XML via ReferenceInformation
        
        Détecte les contextes de contrat selon le standard HR-XML/SIDES :
        - Cherche tous les ReferenceInformation
        - Vérifie présence de OrderId/IdValue ET AssignmentId/IdValue
        - Retourne le contexte parent complet de chaque contrat
        
        Args:
            xml_path: Chemin vers le fichier XML
            
        Returns:
            Liste de dictionnaires avec :
            - 'order_id': Numéro de commande
            - 'assignment_id': Numéro d'affectation
            - 'context': Element XML du contexte parent
        """
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            contracts_found = []
            
            # Stratégie 1 : Avec namespace HR-XML
            ref_infos_with_ns = root.findall('.//hr:ReferenceInformation', self.NS)
            
            if ref_infos_with_ns:
                print(f"🔍 Détection avec namespace HR-XML...")
                for ref_info in ref_infos_with_ns:
                    contract = self._extract_contract_from_ref_info(ref_info, use_namespace=True)
                    if contract:
                        contracts_found.append(contract)
            
            # Stratégie 2 : Sans namespace (fallback)
            if not contracts_found:
                print(f"🔍 Détection sans namespace (fallback)...")
                for ref_info in root.iter():
                    tag_lower = ref_info.tag.lower()
                    if 'referenceinformation' in tag_lower:
                        contract = self._extract_contract_from_ref_info(ref_info, use_namespace=False)
                        if contract:
                            contracts_found.append(contract)
            
            print(f"✅ {len(contracts_found)} contrat(s) détecté(s) dans le XML")
            
            # Afficher les OrderId détectés
            if contracts_found:
                order_ids = [c['order_id'] for c in contracts_found]
                print(f"   OrderIds: {', '.join(order_ids)}")
            
            return contracts_found
            
        except Exception as e:
            print(f"❌ Erreur lors de la lecture du XML: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_contract_from_ref_info(self, ref_info: ET.Element, use_namespace: bool) -> Optional[Dict]:
        """
        Extrait les informations d'un contrat depuis un ReferenceInformation
        
        Args:
            ref_info: Element ReferenceInformation
            use_namespace: Utiliser le namespace HR-XML ou non
            
        Returns:
            Dictionnaire avec order_id, assignment_id, context ou None
        """
        try:
            if use_namespace:
                # Avec namespace
                order_id_elem = ref_info.find('hr:OrderId/hr:IdValue', self.NS)
                assign_id_elem = ref_info.find('hr:AssignmentId/hr:IdValue', self.NS)
            else:
                # Sans namespace (chercher par nom de tag)
                order_id_elem = None
                assign_id_elem = None
                
                for child in ref_info.iter():
                    tag_lower = child.tag.lower()
                    if 'idvalue' in tag_lower:
                        # Vérifier le parent
                        parent_tag = child.getparent().tag.lower() if hasattr(child, 'getparent') else ''
                        if 'orderid' in parent_tag:
                            order_id_elem = child
                        elif 'assignmentid' in parent_tag:
                            assign_id_elem = child
            
            # Vérifier que les deux éléments existent
            if order_id_elem is not None and assign_id_elem is not None:
                order_id_text = order_id_elem.text
                assign_id_text = assign_id_elem.text
                
                if order_id_text and assign_id_text:
                    # Extraire le numéro de commande avec regex
                    order_id = self._extract_order_id_from_text(order_id_text)
                    
                    if order_id:
                        # Remonter au contexte parent du contrat
                        context = ref_info.getparent() if hasattr(ref_info, 'getparent') else ref_info
                        
                        return {
                            'order_id': order_id,
                            'assignment_id': assign_id_text.strip(),
                            'context': context
                        }
        
        except Exception as e:
            # Silent fail pour continuer l'extraction des autres contrats
            pass
        
        return None
    
    def _extract_order_id_from_text(self, text: str) -> Optional[str]:
        """
        Extrait le numéro de commande d'un texte avec les patterns définis
        
        Args:
            text: Texte contenant potentiellement un numéro de commande
            
        Returns:
            Numéro de commande ou None
        """
        for pattern in self.ORDER_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None
    
    def enrich_xml(self, xml_path: str, output_path: str, progress_callback=None) -> Tuple[bool, str, Dict]:
        """
        Enrichit TOUS les contrats du fichier XML avec les données PIXID
        
        Args:
            xml_path: Chemin vers le fichier XML source
            output_path: Chemin vers le fichier XML enrichi
            progress_callback: Fonction callback(current, total) pour progression
            
        Returns:
            (succès: bool, message: str, stats: dict)
        """
        try:
            # Lire l'encoding original
            encoding = 'iso-8859-1'
            with open(xml_path, 'rb') as f:
                first_line = f.readline().decode('iso-8859-1', errors='ignore')
                if 'encoding=' in first_line:
                    match = re.search(r'encoding=["\']([^"\']+)["\']', first_line)
                    if match:
                        encoding = match.group(1)
            
            # 1. Trouver tous les contrats via ReferenceInformation
            contracts = self.find_all_order_ids_in_xml(xml_path)
            
            if not contracts:
                return False, "Aucun contrat détecté dans le XML", {
                    'total': 0,
                    'enrichis': 0,
                    'non_trouves': 0,
                    'details': []
                }
            
            # 2. Parser le XML pour modification
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Enregistrer le namespace pour sauvegarde propre
            ET.register_namespace('hr', 'http://ns.hr-xml.org/2004-08-02')
            
            # Statistiques
            stats = {
                'total': len(contracts),
                'enrichis': 0,
                'non_trouves': 0,
                'fallback_used': 0,
                'details': []
            }
            
            # 3. Enrichir chaque contrat
            for idx, contract_info in enumerate(contracts):
                order_id = contract_info['order_id']
                assignment_id = contract_info['assignment_id']
                context = contract_info['context']
                
                # Callback progression
                if progress_callback:
                    progress_callback(idx + 1, len(contracts))
                
                # Récupérer les données de la commande
                commande = self.commandes_data.get(order_id)
                
                detail = {
                    'OrderId': order_id,
                    'AssignmentId': assignment_id,
                    'PositionCoefficient': 'N/A',
                    'PositionStatusCode': 'N/A',
                    'matched': False,
                    'note': ''
                }
                
                if commande:
                    # Enrichir ce contrat
                    modifications = self._enrich_contract(context, commande, order_id)
                    
                    stats['enrichis'] += 1
                    detail['matched'] = True
                    detail['PositionCoefficient'] = modifications.get('classification', 'N/A')
                    detail['PositionStatusCode'] = modifications.get('statut_code', 'N/A')
                    detail['note'] = modifications.get('note', '')
                    
                    if modifications.get('fallback_used', False):
                        stats['fallback_used'] += 1
                else:
                    # Pas de correspondance : appliquer fallback seulement
                    fallback_result = self._apply_classification_fallback(context, order_id)
                    
                    stats['non_trouves'] += 1
                    detail['matched'] = False
                    
                    if fallback_result:
                        detail['PositionCoefficient'] = fallback_result['classification']
                        detail['note'] = fallback_result['note']
                        stats['fallback_used'] += 1
                    else:
                        detail['note'] = 'Aucune donnée disponible'
                
                stats['details'].append(detail)
            
            # 4. Sauvegarder le XML enrichi
            if stats['enrichis'] > 0 or stats['fallback_used'] > 0:
                # Sauvegarde avec préservation des namespaces
                tree.write(output_path, encoding=encoding, xml_declaration=True, method='xml')
                
                message = f"✅ XML enrichi avec succès!\n\n"
                message += f"📊 Statistiques:\n"
                message += f"  • Total contrats: {stats['total']}\n"
                message += f"  • Enrichis (avec données): {stats['enrichis']}\n"
                message += f"  • Non trouvés: {stats['non_trouves']}\n"
                message += f"  • Fallback classification utilisé: {stats['fallback_used']}"
                
                print(f"\n{message}")
                return True, message, stats
            else:
                return False, "Aucune modification effectuée", stats
                
        except ET.ParseError as e:
            return False, f"Erreur de parsing XML: {e}", {'total': 0, 'enrichis': 0, 'non_trouves': 0, 'details': []}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Erreur inattendue: {e}", {'total': 0, 'enrichis': 0, 'non_trouves': 0, 'details': []}
    
    def _enrich_contract(self, context: ET.Element, commande: dict, order_id: str) -> Dict:
        """
        Enrichit un contrat avec les données de la commande
        
        Modifie UNIQUEMENT les 2 balises autorisées :
        1. PositionCharacteristics/PositionCoefficient (classification)
        2. PositionCharacteristics/PositionStatus/Code (statut)
        
        Args:
            context: Element XML du contexte du contrat
            commande: Données de la commande depuis JSON
            order_id: Numéro de commande (pour debug)
            
        Returns:
            Dictionnaire avec les modifications effectuées
        """
        result = {
            'classification': 'N/A',
            'statut_code': 'N/A',
            'note': '',
            'fallback_used': False
        }
        
        # 1. CLASSIFICATION → PositionCoefficient
        classification, classif_note, fallback_used = self._get_classification(context, commande)
        
        if classification:
            # Chercher PositionCoefficient avec namespace
            pos_coeff = context.find('.//hr:PositionCharacteristics/hr:PositionCoefficient', self.NS)
            
            if pos_coeff is None:
                # Fallback sans namespace
                for elem in context.iter():
                    if 'positioncoefficient' in elem.tag.lower():
                        pos_coeff = elem
                        break
            
            if pos_coeff is not None:
                old_value = pos_coeff.text or ""
                pos_coeff.text = classification
                result['classification'] = classification
                result['fallback_used'] = fallback_used
                result['note'] = classif_note
                print(f"   ✓ {order_id} - PositionCoefficient: '{old_value}' → '{classification}' ({classif_note})")
        
        # 2. STATUT → PositionStatus/Code
        statut = commande.get('statut')
        if statut:
            # Extraire le code (avant le tiret)
            code_statut = statut.split('-')[0].strip() if '-' in statut else statut.strip()
            
            # Chercher PositionStatus/Code avec namespace
            pos_status_code = context.find('.//hr:PositionCharacteristics/hr:PositionStatus/hr:Code', self.NS)
            
            if pos_status_code is None:
                # Fallback sans namespace
                for elem in context.iter():
                    tag_lower = elem.tag.lower()
                    if 'positionstatus' in tag_lower:
                        for child in elem:
                            if child.tag.lower().endswith('code'):
                                pos_status_code = child
                                break
            
            if pos_status_code is not None:
                old_value = pos_status_code.text or ""
                pos_status_code.text = code_statut
                result['statut_code'] = code_statut
                print(f"   ✓ {order_id} - PositionStatus/Code: '{old_value}' → '{code_statut}'")
        
        return result
    
    def _get_classification(self, context: ET.Element, commande: dict) -> Tuple[Optional[str], str, bool]:
        """
        Détermine la classification avec logique de fallback
        
        Règles :
        1. Priorité : classification_interimaire du JSON
        2. Fallback : Copier PositionLevel si regex [A-E]\d{1,2} match
        
        Args:
            context: Contexte XML du contrat
            commande: Données de la commande
            
        Returns:
            (classification, note, fallback_used)
        """
        # Priorité 1 : classification_interimaire du JSON
        classif = commande.get('classification_interimaire')
        if classif and classif.strip():
            return classif.strip(), "depuis JSON", False
        
        # Priorité 2 : Fallback PositionLevel
        return self._apply_classification_fallback_internal(context)
    
    def _apply_classification_fallback(self, context: ET.Element, order_id: str) -> Optional[Dict]:
        """
        Applique le fallback classification pour un contrat sans correspondance JSON
        
        Args:
            context: Contexte XML du contrat
            order_id: Numéro de commande (pour debug)
            
        Returns:
            Dictionnaire avec classification et note ou None
        """
        classification, note, fallback_used = self._apply_classification_fallback_internal(context)
        
        if classification and fallback_used:
            # Appliquer la modification
            pos_coeff = context.find('.//hr:PositionCharacteristics/hr:PositionCoefficient', self.NS)
            
            if pos_coeff is None:
                for elem in context.iter():
                    if 'positioncoefficient' in elem.tag.lower():
                        pos_coeff = elem
                        break
            
            if pos_coeff is not None:
                old_value = pos_coeff.text or ""
                if not old_value.strip():  # Seulement si vide
                    pos_coeff.text = classification
                    print(f"   ✓ {order_id} - PositionCoefficient: '{old_value}' → '{classification}' ({note})")
                    return {'classification': classification, 'note': note}
        
        return None
    
    def _apply_classification_fallback_internal(self, context: ET.Element) -> Tuple[Optional[str], str, bool]:
        """
        Logique interne du fallback classification
        
        Args:
            context: Contexte XML du contrat
            
        Returns:
            (classification, note, fallback_used)
        """
        # Chercher PositionLevel avec namespace
        position_level = context.find('.//hr:PositionLevel', self.NS)
        
        if position_level is None:
            # Fallback sans namespace
            for elem in context.iter():
                if 'positionlevel' in elem.tag.lower():
                    position_level = elem
                    break
        
        if position_level is not None and position_level.text:
            level_text = position_level.text.strip()
            
            # Vérifier si correspond à la regex [A-E]\d{1,2}
            if re.match(self.CLASSIFICATION_REGEX, level_text):
                return level_text, "copié depuis PositionLevel", True
        
        return None, "", False
    
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
        print(f"📊 {stats['enrichis']} contrat(s) enrichi(s) sur {stats['total']}")
        
        # Afficher le récapitulatif détaillé
        if stats['details']:
            print(f"\n📋 Récapitulatif par contrat:")
            print(f"{'OrderId':<12} {'AssignmentId':<15} {'Coefficient':<15} {'StatusCode':<12} {'Note'}")
            print("-" * 90)
            for detail in stats['details']:
                print(f"{detail['OrderId']:<12} {detail['AssignmentId']:<15} "
                      f"{detail['PositionCoefficient']:<15} {detail['PositionStatusCode']:<12} "
                      f"{detail['note']}")
    else:
        print(f"\n❌ Échec: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
