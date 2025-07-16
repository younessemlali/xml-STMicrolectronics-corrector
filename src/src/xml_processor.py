"""
Module de traitement et enrichissement des fichiers XML PIXID
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
import json
from typing import Dict, Optional, Any, Union, List
from pathlib import Path
from datetime import datetime
import re
from lxml import etree
import xmltodict
from loguru import logger

from . import XML_FIELD_MAPPING, FIELDS_TO_EXTRACT


class XMLProcessor:
    """
    Classe pour traiter et enrichir les fichiers XML PIXID
    """
    
    def __init__(self):
        """Initialise le processeur XML"""
        self.field_mapping = XML_FIELD_MAPPING
        logger.info("XMLProcessor initialisé")
    
    def parse_xml(self, xml_content: Union[str, bytes, Path]) -> Optional[Dict[str, Any]]:
        """
        Parse un fichier XML et retourne sa structure sous forme de dictionnaire
        
        Args:
            xml_content: Contenu XML (string, bytes) ou chemin vers fichier
            
        Returns:
            Dictionnaire représentant la structure XML ou None si erreur
        """
        try:
            # Gérer les différents types d'entrée
            if isinstance(xml_content, Path):
                with open(xml_content, 'rb') as f:
                    xml_content = f.read()
            elif isinstance(xml_content, str):
                xml_content = xml_content.encode('utf-8')
            
            # Parser avec xmltodict pour faciliter la manipulation
            xml_dict = xmltodict.parse(xml_content, dict_constructor=dict)
            
            logger.debug("XML parsé avec succès")
            return xml_dict
            
        except Exception as e:
            logger.error(f"Erreur lors du parsing XML: {e}")
            return None
    
    def extract_order_id(self, xml_content: Union[str, bytes, Path, Dict]) -> Optional[str]:
        """
        Extrait l'OrderId du fichier XML
        
        Args:
            xml_content: Contenu XML ou dictionnaire parsé
            
        Returns:
            L'OrderId trouvé ou None
        """
        try:
            # Si c'est déjà un dictionnaire parsé
            if isinstance(xml_content, dict):
                xml_dict = xml_content
            else:
                xml_dict = self.parse_xml(xml_content)
                
            if not xml_dict:
                return None
            
            # Recherche récursive de l'OrderId
            order_id = self._find_key_recursive(xml_dict, ['OrderId', 'orderid', 'order_id', 'OrderID'])
            
            if order_id:
                logger.info(f"OrderId trouvé: {order_id}")
                return str(order_id)
            
            # Recherche alternative dans les attributs
            order_id = self._find_in_attributes(xml_dict, ['OrderId', 'orderid', 'order_id'])
            
            if order_id:
                logger.info(f"OrderId trouvé dans attributs: {order_id}")
                return str(order_id)
            
            logger.warning("OrderId non trouvé dans le XML")
            return None
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction de l'OrderId: {e}")
            return None
    
    def _find_key_recursive(self, data: Union[Dict, List, Any], keys: List[str]) -> Optional[Any]:
        """
        Recherche récursive d'une clé dans une structure de données
        
        Args:
            data: Structure de données à parcourir
            keys: Liste de clés à rechercher (insensible à la casse)
            
        Returns:
            La valeur trouvée ou None
        """
        if isinstance(data, dict):
            # Vérifier les clés directes
            for key, value in data.items():
                if key.lower() in [k.lower() for k in keys]:
                    return value
                
                # Recherche récursive
                result = self._find_key_recursive(value, keys)
                if result is not None:
                    return result
                    
        elif isinstance(data, list):
            # Parcourir les éléments de la liste
            for item in data:
                result = self._find_key_recursive(item, keys)
                if result is not None:
                    return result
        
        return None
    
    def _find_in_attributes(self, data: Union[Dict, List, Any], keys: List[str]) -> Optional[str]:
        """
        Recherche dans les attributs XML (format @attribute)
        """
        if isinstance(data, dict):
            # Vérifier les attributs directs
            for key, value in data.items():
                if key.startswith('@') and key[1:].lower() in [k.lower() for k in keys]:
                    return str(value)
                
                # Recherche récursive
                result = self._find_in_attributes(value, keys)
                if result:
                    return result
                    
        elif isinstance(data, list):
            for item in data:
                result = self._find_in_attributes(item, keys)
                if result:
                    return result
        
        return None
    
    def enrich_xml(self, xml_content: Union[str, bytes, Path], 
                   enrichment_data: Dict[str, Any]) -> Optional[bytes]:
        """
        Enrichit un fichier XML avec les données fournies
        
        Args:
            xml_content: Contenu XML original
            enrichment_data: Données à ajouter au XML
            
        Returns:
            XML enrichi en bytes ou None si erreur
        """
        try:
            # Parser le XML avec lxml pour préserver la structure
            if isinstance(xml_content, Path):
                parser = etree.XMLParser(remove_blank_text=True)
                tree = etree.parse(str(xml_content), parser)
                root = tree.getroot()
            else:
                if isinstance(xml_content, str):
                    xml_content = xml_content.encode('utf-8')
                parser = etree.XMLParser(remove_blank_text=True)
                root = etree.fromstring(xml_content, parser)
            
            # Créer ou trouver la section PIXID
            pixid_section = self._find_or_create_pixid_section(root)
            
            # Ajouter les données d'enrichissement
            enrichment_count = 0
            for field_fr, field_en in self.field_mapping.items():
                if field_fr in enrichment_data and enrichment_data[field_fr]:
                    value = str(enrichment_data[field_fr])
                    
                    # Ignorer les valeurs vides ou 'nan'
                    if value and value.lower() not in ['nan', 'none', 'null', '']:
                        self._update_or_create_element(pixid_section, field_en, value)
                        enrichment_count += 1
            
            # Ajouter les métadonnées d'enrichissement
            metadata = pixid_section.find('EnrichmentMetadata')
            if metadata is None:
                metadata = etree.SubElement(pixid_section, 'EnrichmentMetadata')
            
            # Timestamp
            timestamp_elem = metadata.find('Timestamp')
            if timestamp_elem is None:
                timestamp_elem = etree.SubElement(metadata, 'Timestamp')
            timestamp_elem.text = datetime.now().isoformat()
            
            # Nombre de champs enrichis
            count_elem = metadata.find('FieldsEnriched')
            if count_elem is None:
                count_elem = etree.SubElement(metadata, 'FieldsEnriched')
            count_elem.text = str(enrichment_count)
            
            # Source
            source_elem = metadata.find('Source')
            if source_elem is None:
                source_elem = etree.SubElement(metadata, 'Source')
            source_elem.text = 'PIXID Google Sheets Sync'
            
            # Convertir en bytes avec formatage
            xml_bytes = etree.tostring(
                root,
                pretty_print=True,
                xml_declaration=True,
                encoding='UTF-8'
            )
            
            logger.info(f"XML enrichi avec {enrichment_count} champs")
            return xml_bytes
            
        except Exception as e:
            logger.error(f"Erreur lors de l'enrichissement XML: {e}")
            return None
    
    def _find_or_create_pixid_section(self, root: etree.Element) -> etree.Element:
        """
        Trouve ou crée la section PIXIDEnrichment dans le XML
        """
        # Chercher une section existante
        pixid_section = root.find('.//PIXIDEnrichment')
        
        if pixid_section is None:
            # Créer la section à la fin du root
            pixid_section = etree.SubElement(root, 'PIXIDEnrichment')
            logger.debug("Section PIXIDEnrichment créée")
        else:
            logger.debug("Section PIXIDEnrichment existante trouvée")
        
        return pixid_section
    
    def _update_or_create_element(self, parent: etree.Element, tag: str, value: str):
        """
        Met à jour ou crée un élément XML
        """
        element = parent.find(tag)
        
        if element is None:
            element = etree.SubElement(parent, tag)
            logger.debug(f"Élément créé: {tag}")
        else:
            logger.debug(f"Élément mis à jour: {tag}")
        
        element.text = value
    
    def validate_xml(self, xml_content: Union[str, bytes]) -> Dict[str, Any]:
        """
        Valide un fichier XML et retourne un rapport
        
        Args:
            xml_content: Contenu XML à valider
            
        Returns:
            Dictionnaire avec les résultats de validation
        """
        validation_result = {
            'valid': False,
            'errors': [],
            'warnings': [],
            'has_order_id': False,
            'has_pixid_section': False,
            'enriched_fields': []
        }
        
        try:
            # Parser le XML
            if isinstance(xml_content, str):
                xml_content = xml_content.encode('utf-8')
            
            parser = etree.XMLParser()
            root = etree.fromstring(xml_content, parser)
            
            validation_result['valid'] = True
            
            # Vérifier la présence de l'OrderId
            order_id = self.extract_order_id(xml_content)
            if order_id:
                validation_result['has_order_id'] = True
                validation_result['order_id'] = order_id
            else:
                validation_result['warnings'].append("OrderId non trouvé")
            
            # Vérifier la section PIXID
            pixid_section = root.find('.//PIXIDEnrichment')
            if pixid_section is not None:
                validation_result['has_pixid_section'] = True
                
                # Lister les champs enrichis
                for field_fr, field_en in self.field_mapping.items():
                    elem = pixid_section.find(field_en)
                    if elem is not None and elem.text:
                        validation_result['enriched_fields'].append({
                            'field': field_fr,
                            'value': elem.text
                        })
            
            # Vérifier la structure basique
            if len(root) == 0:
                validation_result['warnings'].append("Le XML semble vide")
            
        except etree.XMLSyntaxError as e:
            validation_result['valid'] = False
            validation_result['errors'].append(f"Erreur de syntaxe XML: {str(e)}")
            
        except Exception as e:
            validation_result['valid'] = False
            validation_result['errors'].append(f"Erreur de validation: {str(e)}")
        
        return validation_result
    
    def prettify_xml(self, xml_content: Union[str, bytes]) -> str:
        """
        Formate un XML pour l'affichage
        
        Args:
            xml_content: Contenu XML
            
        Returns:
            XML formaté en string
        """
        try:
            if isinstance(xml_content, str):
                xml_content = xml_content.encode('utf-8')
            
            # Parser avec minidom pour un joli formatage
            dom = minidom.parseString(xml_content)
            
            # Retirer les lignes vides
            pretty_xml = dom.toprettyxml(indent='  ')
            lines = [line for line in pretty_xml.split('\n') if line.strip()]
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"Erreur lors du formatage XML: {e}")
            # Retourner le XML original en cas d'erreur
            if isinstance(xml_content, bytes):
                return xml_content.decode('utf-8', errors='ignore')
            return str(xml_content)
    
    def compare_xml(self, original: Union[str, bytes], enriched: Union[str, bytes]) -> Dict[str, Any]:
        """
        Compare deux XML et retourne les différences
        
        Args:
            original: XML original
            enriched: XML enrichi
            
        Returns:
            Dictionnaire avec les différences
        """
        try:
            # Parser les deux XML
            if isinstance(original, str):
                original = original.encode('utf-8')
            if isinstance(enriched, str):
                enriched = enriched.encode('utf-8')
            
            orig_root = etree.fromstring(original)
            enr_root = etree.fromstring(enriched)
            
            # Trouver les nouveaux éléments
            orig_elements = set(self._get_all_paths(orig_root))
            enr_elements = set(self._get_all_paths(enr_root))
            
            new_elements = enr_elements - orig_elements
            
            # Extraire les valeurs des nouveaux éléments
            changes = {
                'new_elements': [],
                'new_count': len(new_elements)
            }
            
            for path in new_elements:
                elem = enr_root.xpath(path)
                if elem and hasattr(elem[0], 'text') and elem[0].text:
                    changes['new_elements'].append({
                        'path': path,
                        'value': elem[0].text
                    })
            
            return changes
            
        except Exception as e:
            logger.error(f"Erreur lors de la comparaison XML: {e}")
            return {'error': str(e)}
    
    def _get_all_paths(self, root: etree.Element, path: str = '') -> List[str]:
        """
        Récupère tous les chemins XPath d'un XML
        """
        paths = []
        
        current_path = f"{path}/{root.tag}"
        paths.append(current_path)
        
        for child in root:
            paths.extend(self._get_all_paths(child, current_path))
        
        return paths
