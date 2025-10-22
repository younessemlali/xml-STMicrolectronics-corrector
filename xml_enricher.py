#!/usr/bin/env python3
"""
Script d'enrichissement XML PIXID - STMicroelectronics
Enrichit TOUS les contrats XML avec les données extraites des emails
Version lxml : namespace-agnostique, parser robuste pour gros fichiers
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
    CLASSIFICATION_REGEX = re.compile(r'^[A-E]\d{1,2}$')
    
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
        
        Utilise XPath namespace-agnostique avec local-name() pour détecter :
        - Tous les ReferenceInformation contenant OrderId/IdValue
        - Ne requiert PAS AssignmentId (optionnel)
        
        Args:
            xml_path: Chemin vers le fichier XML
            
        Returns:
            Liste de dictionnaires avec :
            - 'order_id': Numéro de commande (RT/CR/CD + 6 chiffres)
            - 'assignment_id': Numéro d'affectation (si présent)
            - 'context': Element lxml du contexte parent
        """
        try:
            # Parser robuste pour gros fichiers
            parser = etree.XMLParser(
                remove_blank_text=True,
                recover=True,
                huge_tree=True
            )
            
            tree = etree.parse(xml_path, parser)
            
            # XPath namespace-agnostique : trouve tous les contextes de contrat
            # Un contrat = parent de ReferenceInformation ayant OrderId/IdValue
            xpath_query = (
                "//*[local-name()='ReferenceInformation']"
                "[*[local-name()='OrderId']/*[local-name()='IdValue']]/.."
            )
            
            contexts = tree.xpath(xpath_query)
            
            contracts_found = []
            
            for context in contexts:
                contract = self._extract_contract_info(context)
                if contract:
                    contracts_found.append(contract)
            
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
    
    def _extract_contract_info(self, context: etree.Element) -> Optional[Dict]:
        """
        Extrait les informations d'un contrat depuis son contexte
        
        Args:
            context: Element lxml du contexte (parent de ReferenceInformation)
            
        Returns:
            Dictionnaire avec order_id, assignment_id, context ou None
        """
        try:
            # Chercher ReferenceInformation dans le contexte
            ref_info = context.xpath(".//*[local-name()='ReferenceInformation']")
            
            if not ref_info:
                return None
            
            ref_info = ref_info[0]
            
            # Extraire OrderId/IdValue
            order_id_nodes = ref_info.xpath("*[local-name()='OrderId']/*[local-name()='IdValue']")
            
            if not order_id_nodes or not order_id_nodes[0].text:
                return None
            
            order_id_text = order_id_nodes[0].text.strip()
            
            # Extraire le numéro de commande avec patterns
            order_id = self._extract_order_id_from_text(order_id_text)
            
            if not order_id:
                return None
            
            # Extraire AssignmentId/IdValue (optionnel)
            assign_id = "N/A"
            assign_id_nodes = ref_info.xpath("*[local-name()='AssignmentId']/*[local-name()='IdValue']")
            if assign_id_nodes and assign_id_nodes[0].text:
                assign_id = assign_id_nodes[0].text.strip()
            
            return {
                'order_id': order_id,
                'assignment_id': assign_id,
                'context': context
            }
        
        except Exception as e:
            # Silent fail pour continuer l'extraction
            return None
    
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
            # Parser robuste
            parser = etree.XMLParser(
                remove_blank_text=True,
                recover=True,
                huge_tree=True
            )
            
            tree = etree.parse(xml_path, parser)
            
            # Récupérer l'encodage original
            encoding = tree.docinfo.encoding or 'iso-8859-1'
            
            # 1. Trouver tous les contrats
            contracts = self.find_all_order_ids_in_xml(xml_path)
            
            if not contracts:
                return False, "Aucun contrat détecté dans le XML", {
                    'total': 0,
                    'enrichis': 0,
                    'non_trouves': 0,
                    'fallback_used': 0,
                    'details': []
                }
            
            # Statistiques
            stats = {
                'total': len(contracts),
                'enrichis': 0,
                'non_trouves': 0,
                'fallback_used': 0,
                'details': []
            }
            
            # 2. Enrichir chaque contrat
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
                    # Enrichir ce contrat avec données JSON
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
            
            # 3. Sauvegarder le XML enrichi
            if stats['enrichis'] > 0 or stats['fallback_used'] > 0:
                # Écriture avec lxml : préserve encodage et namespaces
                tree.write(
                    output_path,
                    encoding=encoding,
                    pretty_print=True,
                    xml_declaration=True
                )
                
                message = f"✅ XML enrichi avec succès!\n\n"
                message += f"📊 Statistiques:\n"
                message += f"  • Total contrats: {stats['total']}\n"
                message += f"  • Enrichis (avec données JSON): {stats['enrichis']}\n"
                message += f"  • Non trouvés dans JSON: {stats['non_trouves']}\n"
                message += f"  • Fallback classification utilisé: {stats['fallback_used']}"
                
                print(f"\n{message}")
                return True, message, stats
            else:
                return False, "Aucune modification effectuée", stats
                
        except etree.ParseError as e:
            return False, f"Erreur de parsing XML: {e}", {
                'total': 0, 'enrichis': 0, 'non_trouves': 0, 'fallback_used': 0, 'details': []
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Erreur inattendue: {e}", {
                'total': 0, 'enrichis': 0, 'non_trouves': 0, 'fallback_used': 0, 'details': []
            }
    
    def _enrich_contract(self, context: etree.Element, commande: dict, order_id: str) -> Dict:
        """
        Enrichit un contrat avec les données de la commande
        
        Modifie UNIQUEMENT les 2 balises autorisées :
        1. PositionCharacteristics/PositionCoefficient (classification)
        2. PositionCharacteristics/PositionStatus/Code (statut)
        
        Args:
            context: Element lxml du contexte du contrat
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
            xpath_coeff = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionCoefficient']"
            success = self._upsert_text(context, xpath_coeff, classification, 'PositionCoefficient')
            
            if success:
                result['classification'] = classification
                result['fallback_used'] = fallback_used
                result['note'] = classif_note
                print(f"   ✓ {order_id} - PositionCoefficient → '{classification}' ({classif_note})")
        
        # 2. STATUT → PositionStatus/Code
        statut = commande.get('statut')
        if statut:
            # Extraire le code (avant le tiret si présent)
            code_statut = statut.split('-')[0].strip() if '-' in statut else statut.strip()
            
            xpath_status = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionStatus']/*[local-name()='Code']"
            success = self._upsert_text(context, xpath_status, code_statut, 'Code')
            
            if success:
                result['statut_code'] = code_statut
                print(f"   ✓ {order_id} - PositionStatus/Code → '{code_statut}'")
        
        return result
    
    def _get_classification(self, context: etree.Element, commande: dict) -> Tuple[Optional[str], str, bool]:
        """
        Détermine la classification avec logique de fallback
        
        Règles :
        1. Priorité : classification_interimaire du JSON
        2. Fallback : Copier PositionLevel si regex [A-E]\d{1,2} match
        
        Args:
            context: Contexte lxml du contrat
            commande: Données de la commande
            
        Returns:
            (classification, note, fallback_used)
        """
        # Priorité 1 : classification_interimaire du JSON
        classif = commande.get('classification_interimaire')
        if classif and classif.strip():
            return classif.strip(), "depuis JSON", False
        
        # Priorité 2 : Fallback PositionLevel
        return self._get_classification_from_level(context)
    
    def _get_classification_from_level(self, context: etree.Element) -> Tuple[Optional[str], str, bool]:
        """
        Extrait la classification depuis PositionLevel (fallback)
        
        Args:
            context: Contexte lxml du contrat
            
        Returns:
            (classification, note, fallback_used)
        """
        xpath_level = ".//*[local-name()='PositionLevel']"
        level_nodes = context.xpath(xpath_level)
        
        if level_nodes and level_nodes[0].text:
            level_text = level_nodes[0].text.strip()
            
            # Vérifier si correspond à la regex [A-E]\d{1,2}
            if self.CLASSIFICATION_REGEX.match(level_text):
                return level_text, "copié depuis PositionLevel", True
        
        return None, "", False
    
    def _apply_classification_fallback(self, context: etree.Element, order_id: str) -> Optional[Dict]:
        """
        Applique le fallback classification pour un contrat sans correspondance JSON
        
        Args:
            context: Contexte lxml du contrat
            order_id: Numéro de commande (pour debug)
            
        Returns:
            Dictionnaire avec classification et note ou None
        """
        classification, note, fallback_used = self._get_classification_from_level(context)
        
        if classification and fallback_used:
            xpath_coeff = ".//*[local-name()='PositionCharacteristics']/*[local-name()='PositionCoefficient']"
            
            # Vérifier si PositionCoefficient existe et est vide
            coeff_nodes = context.xpath(xpath_coeff)
            if not coeff_nodes or not (coeff_nodes[0].text or '').strip():
                # Appliquer le fallback
                success = self._upsert_text(context, xpath_coeff, classification, 'PositionCoefficient')
                
                if success:
                    print(f"   ✓ {order_id} - PositionCoefficient → '{classification}' ({note})")
                    return {'classification': classification, 'note': note}
        
        return None
    
    def _upsert_text(self, context: etree.Element, xpath: str, value: str, tag_name: str) -> bool:
        """
        Insère ou met à jour le texte d'un élément via XPath namespace-agnostique
        
        Si l'élément n'existe pas, le crée dans la hiérarchie appropriée
        en préservant le namespace du parent.
        
        Args:
            context: Element lxml parent
            xpath: XPath avec local-name() pour trouver l'élément
            value: Valeur à insérer
            tag_name: Nom du tag pour création (sans namespace)
            
        Returns:
            True si succès, False sinon
        """
        try:
            nodes = context.xpath(xpath)
            
            if nodes:
                # Élément existe : mise à jour
                nodes[0].text = value
                return True
            else:
                # Élément n'existe pas : création
                # Décomposer le XPath pour créer la hiérarchie
                # Format attendu : .//*[local-name()='Parent']/*[local-name()='Child']
                
                # Extraire les noms de tags depuis le XPath
                parts = re.findall(r"local-name\(\)='([^']+)'", xpath)
                
                if not parts:
                    return False
                
                # Naviguer/créer la hiérarchie
                current = context
                for i, part_name in enumerate(parts):
                    # Chercher si l'élément existe déjà
                    child_xpath = f".//*[local-name()='{part_name}']"
                    existing = current.xpath(child_xpath)
                    
                    if existing:
                        current = existing[0]
                    else:
                        # Créer l'élément dans le namespace du parent
                        ns = current.nsmap.get(None)
                        if ns:
                            new_tag = f"{{{ns}}}{part_name}"
                        else:
                            new_tag = part_name
                        
                        new_elem = etree.SubElement(current, new_tag)
                        current = new_elem
                
                # Insérer la valeur dans le dernier élément créé
                current.text = value
                return True
        
        except Exception as e:
            print(f"   ⚠️  Erreur upsert {tag_name}: {e}")
            return False
    
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
            print(f"{'OrderId':<12} {'AssignmentId':<20} {'Coefficient':<15} {'StatusCode':<12} {'Note'}")
            print("-" * 100)
            for detail in stats['details'][:20]:  # Limiter à 20 pour lisibilité
                print(f"{detail['OrderId']:<12} {detail['AssignmentId']:<20} "
                      f"{detail['PositionCoefficient']:<15} {detail['PositionStatusCode']:<12} "
                      f"{detail['note']}")
            if len(stats['details']) > 20:
                print(f"... et {len(stats['details']) - 20} autres contrats")
    else:
        print(f"\n❌ Échec: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
