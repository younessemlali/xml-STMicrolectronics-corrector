#!/usr/bin/env python3
"""
Script d'enrichissement XML PIXID - STMicroelectronics
Enrichit les fichiers XML avec les données extraites des emails (statut et classification)
"""

import json
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from typing import Dict, Optional, Tuple


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
    
    def find_order_id_in_xml(self, xml_path: str) -> Optional[str]:
        """
        Recherche le numéro de commande dans le fichier XML
        
        Args:
            xml_path: Chemin vers le fichier XML
            
        Returns:
            Numéro de commande trouvé ou None
        """
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # D'abord chercher directement dans tout le texte XML (plus fiable)
            xml_string = ET.tostring(root, encoding='unicode')
            matches = re.findall(r'(CR\d{6}|CD\d{6}|RT\d{6})', xml_string)
            if matches:
                order_id = matches[0]
                print(f"🔍 Numéro de commande trouvé: {order_id}")
                return order_id
            
            # Si pas trouvé, essayer avec les patterns
            patterns = [
                './/OrderId',
                './/CustomerOrderNumber', 
                './/OrderNumber',
                './/{*}OrderId',
                './/{*}CustomerOrderNumber'
            ]
            
            for pattern in patterns:
                element = root.find(pattern)
                if element is not None and element.text:
                    order_id = element.text.strip()
                    print(f"🔍 Numéro de commande trouvé (pattern): {order_id}")
                    return order_id
                
            print("⚠️ Aucun numéro de commande trouvé dans le XML")
            return None
            
        except Exception as e:
            print(f"❌ Erreur lors de la lecture du XML: {e}")
            return None
    
    def enrich_xml(self, xml_path: str, output_path: str) -> Tuple[bool, str]:
        """
        Enrichit le fichier XML avec les données PIXID
        
        Args:
            xml_path: Chemin vers le fichier XML source
            output_path: Chemin vers le fichier XML enrichi
            
        Returns:
            (succès: bool, message: str)
        """
        try:
            # 1. Trouver le numéro de commande
            order_id = self.find_order_id_in_xml(xml_path)
            if not order_id:
                return False, "Aucun numéro de commande trouvé dans le XML"
            
            # 2. Récupérer les données de la commande
            if order_id not in self.commandes_data:
                return False, f"Commande {order_id} non trouvée dans la base de données"
            
            commande = self.commandes_data[order_id]
            statut = commande.get('statut')
            classification = commande.get('classification_interimaire')
            
            print(f"\n📋 Données de la commande {order_id}:")
            print(f"   Statut: {statut}")
            print(f"   Classification: {classification}")
            
            # 3. Parser le XML
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            modifications = []
            
            # 4. Enrichir le statut (Code dans PositionStatus)
            if statut:
                # Extraire juste le code (ex: "OP" de "OP - Opérateur")
                code_statut = statut.split('-')[0].strip() if '-' in statut else statut.strip()
                
                # Chercher sans namespace d'abord
                for position_status in root.findall('.//PositionStatus'):
                    code_element = position_status.find('Code')
                    if code_element is not None:
                        old_value = code_element.text or ""
                        code_element.text = code_statut
                        modifications.append(f"Code: '{old_value}' → '{code_statut}'")
                    
                    desc_element = position_status.find('Description')
                    if desc_element is not None:
                        desc_element.text = statut
                        modifications.append(f"Description: → '{statut}'")
                
                # Puis avec namespace si besoin
                for position_status in root.findall('.//{*}PositionStatus'):
                    code_element = position_status.find('{*}Code')
                    if code_element is not None:
                        old_value = code_element.text or ""
                        code_element.text = code_statut
                        modifications.append(f"Code: '{old_value}' → '{code_statut}'")
                    
                    desc_element = position_status.find('{*}Description')
                    if desc_element is not None:
                        desc_element.text = statut
                        modifications.append(f"Description: → '{statut}'")
            
            # 5. Enrichir la classification (PositionCoefficient)
            if classification:
                # Sans namespace
                for position_chars in root.findall('.//PositionCharacteristics'):
                    coeff_element = position_chars.find('PositionCoefficient')
                    if coeff_element is not None:
                        old_value = coeff_element.text or ""
                        coeff_element.text = classification
                        modifications.append(f"PositionCoefficient: '{old_value}' → '{classification}'")
                
                # Avec namespace
                for position_chars in root.findall('.//{*}PositionCharacteristics'):
                    coeff_element = position_chars.find('{*}PositionCoefficient')
                    if coeff_element is not None:
                        old_value = coeff_element.text or ""
                        coeff_element.text = classification
                        modifications.append(f"PositionCoefficient: '{old_value}' → '{classification}'")
            
            # 6. Sauvegarder le XML enrichi SANS namespaces
            if modifications:
                # Lire l'encoding original
                encoding = 'iso-8859-1'
                with open(xml_path, 'rb') as f:
                    first_line = f.readline().decode('iso-8859-1', errors='ignore')
                    if 'encoding=' in first_line:
                        match = re.search(r'encoding=["\']([^"\']+)["\']', first_line)
                        if match:
                            encoding = match.group(1)
                
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
                
                message = f"✅ XML enrichi avec succès!\n\nModifications effectuées:\n" + "\n".join(f"  • {mod}" for mod in modifications)
                print(f"\n{message}")
                return True, message
            else:
                return False, "Aucune balise à modifier trouvée dans le XML"
                
        except ET.ParseError as e:
            return False, f"Erreur de parsing XML: {e}"
        except Exception as e:
            return False, f"Erreur inattendue: {e}"
    
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
    success, message = enricher.enrich_xml(xml_path, output_path)
    
    if success:
        print(f"\n✅ Fichier enrichi sauvegardé: {output_path}")
    else:
        print(f"\n❌ Échec: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
