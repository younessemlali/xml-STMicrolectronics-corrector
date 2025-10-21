#!/usr/bin/env python3
"""
Script d'enrichissement XML PIXID - STMicroelectronics
Enrichit TOUS les contrats XML avec les données extraites des emails
Version améliorée : traite plusieurs contrats par fichier
"""

import json
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, List


class XMLEnricher:
    """Classe pour enrichir les fichiers XML avec les données PIXID"""
    
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
        Recherche TOUS les numéros de commande dans le fichier XML
        
        Args:
            xml_path: Chemin vers le fichier XML
            
        Returns:
            Liste de dictionnaires {order_id, element} pour chaque Order trouvé
        """
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            orders_found = []
            
            # Chercher tous les éléments Order (avec ou sans namespace)
            for order_elem in root.iter():
                tag_lower = order_elem.tag.lower()
                if 'order' in tag_lower and tag_lower.endswith('order'):
                    # Chercher OrderId dans cet Order
                    order_id = self._extract_order_id_from_element(order_elem)
                    if order_id:
                        orders_found.append({
                            'order_id': order_id,
                            'element': order_elem
                        })
            
            print(f"🔍 {len(orders_found)} contrat(s) détecté(s) dans le XML")
            return orders_found
            
        except Exception as e:
            print(f"❌ Erreur lors de la lecture du XML: {e}")
            return []
    
    def _extract_order_id_from_element(self, order_elem: ET.Element) -> Optional[str]:
        """
        Extrait l'OrderId d'un élément Order
        
        Args:
            order_elem: Element XML représentant un Order
            
        Returns:
            OrderId trouvé ou None
        """
        # Patterns de recherche pour OrderId
        patterns = [r'(CR\d{6})', r'(CD\d{6})', r'(RT\d{6})']
        
        # Stratégie 1: Chercher dans OrderId/IdValue
        for child in order_elem.iter():
            tag_lower = child.tag.lower()
            if 'orderid' in tag_lower or 'idvalue' in tag_lower:
                if child.text:
                    for pattern in patterns:
                        match = re.search(pattern, child.text)
                        if match:
                            return match.group(1)
        
        # Stratégie 2: Chercher dans tout le texte de l'Order
        order_text = ET.tostring(order_elem, encoding='unicode')
        for pattern in patterns:
            matches = re.findall(pattern, order_text)
            if matches:
                return matches[0]
        
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
            
            # 1. Trouver tous les Orders
            orders = self.find_all_order_ids_in_xml(xml_path)
            
            if not orders:
                return False, "Aucun numéro de commande trouvé dans le XML", {
                    'total': 0,
                    'enrichis': 0,
                    'non_trouves': 0,
                    'details': []
                }
            
            # 2. Parser le XML
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Statistiques
            stats = {
                'total': len(orders),
                'enrichis': 0,
                'non_trouves': 0,
                'details': []
            }
            
            # 3. Enrichir chaque Order
            for idx, order_info in enumerate(orders):
                order_id = order_info['order_id']
                order_elem = order_info['element']
                
                # Callback progression
                if progress_callback:
                    progress_callback(idx + 1, len(orders))
                
                # Récupérer les données de la commande
                commande = self.commandes_data.get(order_id)
                
                if commande:
                    # Enrichir cet Order
                    modifications = self._enrich_order_element(order_elem, commande)
                    
                    stats['enrichis'] += 1
                    stats['details'].append({
                        'order_id': order_id,
                        'statut': 'enrichi',
                        'code_statut': commande.get('statut', 'N/A'),
                        'classification': commande.get('classification_interimaire', 'N/A'),
                        'modifications': len(modifications)
                    })
                else:
                    stats['non_trouves'] += 1
                    stats['details'].append({
                        'order_id': order_id,
                        'statut': 'non_trouve',
                        'code_statut': 'N/A',
                        'classification': 'N/A',
                        'modifications': 0
                    })
            
            # 4. Sauvegarder le XML enrichi SANS namespaces
            if stats['enrichis'] > 0:
                # Convertir en string et supprimer tous les ns0:
                xml_string = ET.tostring(root, encoding='unicode')
                xml_string = xml_string.replace('ns0:', '')
                xml_string = xml_string.replace(':ns0', '')
                
                # Ajouter la déclaration XML
                xml_declaration = f'<?xml version="1.0" encoding="{encoding}"?>\n'
                final_xml = xml_declaration + xml_string
                
                # Écrire le fichier
                with open(output_path, 'w', encoding=encoding) as f:
                    f.write(final_xml)
                
                message = f"✅ XML enrichi avec succès!\n\n"
                message += f"📊 Statistiques:\n"
                message += f"  • Total contrats: {stats['total']}\n"
                message += f"  • Enrichis: {stats['enrichis']}\n"
                message += f"  • Non trouvés: {stats['non_trouves']}"
                
                print(f"\n{message}")
                return True, message, stats
            else:
                return False, "Aucune commande trouvée dans la base de données", stats
                
        except ET.ParseError as e:
            return False, f"Erreur de parsing XML: {e}", {'total': 0, 'enrichis': 0, 'non_trouves': 0, 'details': []}
        except Exception as e:
            return False, f"Erreur inattendue: {e}", {'total': 0, 'enrichis': 0, 'non_trouves': 0, 'details': []}
    
    def _enrich_order_element(self, order_elem: ET.Element, commande: dict) -> List[str]:
        """
        Enrichit un élément Order spécifique avec les données
        
        Args:
            order_elem: Element XML de l'Order
            commande: Données de la commande
            
        Returns:
            Liste des modifications effectuées
        """
        modifications = []
        statut = commande.get('statut')
        classification = commande.get('classification_interimaire')
        
        # 1. Enrichir le statut (Code dans PositionStatus)
        if statut:
            code_statut = statut.split('-')[0].strip() if '-' in statut else statut.strip()
            
            for position_status in order_elem.iter():
                tag_lower = position_status.tag.lower()
                if 'positionstatus' in tag_lower:
                    # Chercher Code
                    for child in position_status:
                        child_tag_lower = child.tag.lower()
                        if 'code' in child_tag_lower and child_tag_lower.endswith('code'):
                            old_value = child.text or ""
                            child.text = code_statut
                            modifications.append(f"Code: '{old_value}' → '{code_statut}'")
                        elif 'description' in child_tag_lower:
                            child.text = statut
                            modifications.append(f"Description: → '{statut}'")
        
        # 2. Enrichir la classification (PositionCoefficient)
        if classification:
            for position_chars in order_elem.iter():
                tag_lower = position_chars.tag.lower()
                if 'positioncharacteristics' in tag_lower:
                    for child in position_chars:
                        child_tag_lower = child.tag.lower()
                        if 'positioncoefficient' in child_tag_lower:
                            old_value = child.text or ""
                            child.text = classification
                            modifications.append(f"PositionCoefficient: '{old_value}' → '{classification}'")
        
        return modifications
    
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
    else:
        print(f"\n❌ Échec: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
