#!/usr/bin/env python3
"""
Script principal de synchronisation PIXID
Extrait les données des emails dans Google Drive et les synchronise vers Google Sheets
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
import time

from loguru import logger
import pandas as pd

# Ajouter le répertoire src au path si nécessaire
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import (
    EmailParser,
    GoogleDriveClient,
    GoogleSheetsClient,
    GoogleAuthenticator,
    FIELDS_TO_EXTRACT,
    logger as package_logger
)


class PIXIDSynchronizer:
    """Orchestrateur principal pour la synchronisation Drive -> Sheets"""
    
    def __init__(self, folder_id: str, spreadsheet_id: str, 
                 credentials_path: Optional[str] = None,
                 state_file: str = "sync_state.json"):
        """
        Initialise le synchroniseur
        
        Args:
            folder_id: ID du dossier Google Drive
            spreadsheet_id: ID du Google Sheet
            credentials_path: Chemin vers les credentials (optionnel)
            state_file: Fichier pour sauvegarder l'état
        """
        self.folder_id = folder_id
        self.spreadsheet_id = spreadsheet_id
        self.state_file = Path(state_file)
        
        # Statistiques d'exécution
        self.stats = {
            'start_time': datetime.now().isoformat(),
            'files_found': 0,
            'files_processed': 0,
            'files_skipped': 0,
            'files_error': 0,
            'rows_added': 0,
            'extraction_success': 0,
            'extraction_partial': 0,
            'extraction_failed': 0,
            'errors': []
        }
        
        # Initialiser les clients
        logger.info("Initialisation du synchroniseur PIXID")
        
        try:
            # Obtenir les credentials
            credentials = GoogleAuthenticator.get_credentials(credentials_path)
            
            # Initialiser les clients
            self.drive_client = GoogleDriveClient(credentials)
            self.sheets_client = GoogleSheetsClient(credentials)
            self.email_parser = EmailParser()
            
            # Charger l'état précédent
            self._load_state()
            
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation: {e}")
            self.stats['errors'].append(f"Initialisation: {str(e)}")
            raise
    
    def _load_state(self):
        """Charge l'état de synchronisation précédent"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                # Charger les fichiers déjà traités
                processed_files = state.get('processed_files', [])
                self.drive_client.load_processed_files(processed_files)
                
                logger.info(f"État chargé: {len(processed_files)} fichiers déjà traités")
                
            except Exception as e:
                logger.warning(f"Impossible de charger l'état: {e}")
    
    def _save_state(self):
        """Sauvegarde l'état de synchronisation"""
        try:
            state = {
                'last_sync': datetime.now().isoformat(),
                'processed_files': list(self.drive_client.get_processed_files()),
                'stats': self.stats
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            logger.info("État sauvegardé")
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'état: {e}")
    
    def sync(self) -> Dict[str, Any]:
        """
        Exécute la synchronisation complète
        
        Returns:
            Statistiques d'exécution
        """
        logger.info("=== Début de la synchronisation PIXID ===")
        
        try:
            # 1. Ouvrir la feuille Google Sheets
            self._open_sheet()
            
            # 2. Lister les fichiers dans Drive
            files = self._list_files()
            
            # 3. Traiter chaque fichier
            processed_data = self._process_files(files)
            
            # 4. Ajouter les données à Sheets
            if processed_data:
                self._add_to_sheet(processed_data)
            
            # 5. Sauvegarder l'état
            self._save_state()
            
            # 6. Finaliser les stats
            self._finalize_stats()
            
        except Exception as e:
            logger.error(f"Erreur fatale lors de la synchronisation: {e}")
            self.stats['errors'].append(f"Erreur fatale: {str(e)}")
            self.stats['status'] = 'error'
        
        return self.stats
    
    def _open_sheet(self):
        """Ouvre et prépare la feuille Google Sheets"""
        logger.info(f"Ouverture de la feuille {self.spreadsheet_id}")
        
        try:
            self.sheets_client.open_sheet(self.spreadsheet_id)
            
            # S'assurer que les headers existent
            headers = ['date_extraction', 'fichier_source', 'file_id'] + FIELDS_TO_EXTRACT
            self.sheets_client.ensure_headers(headers)
            
            # Charger les file_id déjà traités depuis Sheets
            existing_file_ids = self.sheets_client.get_processed_file_ids()
            if existing_file_ids:
                self.drive_client.load_processed_files(existing_file_ids)
                logger.info(f"{len(existing_file_ids)} fichiers déjà dans Sheets")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'ouverture de la feuille: {e}")
            self.stats['errors'].append(f"Ouverture Sheet: {str(e)}")
            raise
    
    def _list_files(self) -> List[Dict[str, Any]]:
        """Liste les fichiers à traiter dans Drive"""
        logger.info(f"Recherche des fichiers dans le dossier {self.folder_id}")
        
        try:
            files = self.drive_client.list_files(
                self.folder_id,
                file_types=['.eml', '.txt'],
                only_new=True
            )
            
            self.stats['files_found'] = len(files)
            logger.info(f"{len(files)} nouveaux fichiers trouvés")
            
            return files
            
        except Exception as e:
            logger.error(f"Erreur lors de la liste des fichiers: {e}")
            self.stats['errors'].append(f"Liste fichiers: {str(e)}")
            return []
    
    def _process_files(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Traite tous les fichiers et extrait les données"""
        processed_data = []
        
        for i, file_info in enumerate(files, 1):
            file_name = file_info['name']
            file_id = file_info['id']
            
            logger.info(f"[{i}/{len(files)}] Traitement de {file_name}")
            
            try:
                # Télécharger le fichier
                content = self.drive_client.download_file(file_id, file_name)
                if not content:
                    logger.error(f"Impossible de télécharger {file_name}")
                    self.stats['files_error'] += 1
                    continue
                
                # Parser le fichier
                extracted_data = self.email_parser.parse_file(file_name, content)
                
                # Ajouter les métadonnées
                extracted_data['fichier_source'] = file_name
                extracted_data['file_id'] = file_id
                
                # Évaluer la qualité de l'extraction
                quality = self._evaluate_extraction(extracted_data)
                
                if quality == 'failed':
                    logger.warning(f"Aucune donnée extraite de {file_name}")
                    self.stats['extraction_failed'] += 1
                    self.stats['files_skipped'] += 1
                    continue
                elif quality == 'partial':
                    logger.warning(f"Extraction partielle pour {file_name}")
                    self.stats['extraction_partial'] += 1
                else:
                    self.stats['extraction_success'] += 1
                
                # Log du résumé
                summary = self.email_parser.extract_summary(extracted_data)
                logger.info(f"  → {summary}")
                
                # Ajouter aux données à traiter
                processed_data.append(extracted_data)
                self.stats['files_processed'] += 1
                
                # Pause courte pour éviter les rate limits
                if i % 10 == 0:
                    time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Erreur lors du traitement de {file_name}: {e}")
                self.stats['files_error'] += 1
                self.stats['errors'].append(f"{file_name}: {str(e)}")
                continue
        
        logger.info(f"Traitement terminé: {len(processed_data)} fichiers avec données")
        return processed_data
    
    def _evaluate_extraction(self, data: Dict[str, Any]) -> str:
        """
        Évalue la qualité de l'extraction
        
        Returns:
            'success' | 'partial' | 'failed'
        """
        # Champs critiques
        critical_fields = ['numero_commande']
        # Au moins un des deux codes doit être présent
        code_present = data.get('code_agence') or data.get('code_unite')
        
        # Vérifier les champs critiques
        if not all(data.get(field) for field in critical_fields) or not code_present:
            return 'failed'
        
        # Compter les champs extraits
        extracted_count = sum(1 for field in FIELDS_TO_EXTRACT if data.get(field))
        
        # Plus de 50% des champs = succès, sinon partiel
        if extracted_count >= len(FIELDS_TO_EXTRACT) * 0.5:
            return 'success'
        else:
            return 'partial'
    
    def _add_to_sheet(self, data: List[Dict[str, Any]]):
        """Ajoute les données extraites à Google Sheets"""
        logger.info(f"Ajout de {len(data)} lignes à Google Sheets")
        
        try:
            rows_added = self.sheets_client.append_rows(data, check_duplicates=True)
            self.stats['rows_added'] = rows_added
            
            logger.info(f"{rows_added} lignes ajoutées avec succès")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout à Sheets: {e}")
            self.stats['errors'].append(f"Ajout Sheets: {str(e)}")
    
    def _finalize_stats(self):
        """Finalise les statistiques d'exécution"""
        end_time = datetime.now()
        start_time = datetime.fromisoformat(self.stats['start_time'])
        
        self.stats['end_time'] = end_time.isoformat()
        self.stats['duration_seconds'] = (end_time - start_time).total_seconds()
        self.stats['status'] = 'success' if not self.stats['errors'] else 'partial'
        
        # Résumé
        logger.info("=== Résumé de la synchronisation ===")
        logger.info(f"Durée: {self.stats['duration_seconds']:.1f} secondes")
        logger.info(f"Fichiers trouvés: {self.stats['files_found']}")
        logger.info(f"Fichiers traités: {self.stats['files_processed']}")
        logger.info(f"Fichiers en erreur: {self.stats['files_error']}")
        logger.info(f"Lignes ajoutées: {self.stats['rows_added']}")
        logger.info(f"Extractions: {self.stats['extraction_success']} succès, "
                   f"{self.stats['extraction_partial']} partielles, "
                   f"{self.stats['extraction_failed']} échecs")
        
        if self.stats['errors']:
            logger.warning(f"{len(self.stats['errors'])} erreurs rencontrées")
    
    def generate_monitoring_stats(self) -> Dict[str, Any]:
        """Génère les statistiques pour le monitoring"""
        monitoring_stats = {
            'timestamp': datetime.now().isoformat(),
            'run_id': f"sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'folder_id': self.folder_id,
            'spreadsheet_id': self.spreadsheet_id,
            **self.stats
        }
        
        # Sauvegarder pour le monitoring Streamlit
        monitoring_file = Path('monitoring_data.json')
        
        try:
            # Charger l'historique existant
            history = []
            if monitoring_file.exists():
                with open(monitoring_file, 'r') as f:
                    data = json.load(f)
                    history = data.get('history', [])
            
            # Ajouter la nouvelle exécution
            history.append(monitoring_stats)
            
            # Garder seulement les 100 dernières exécutions
            history = history[-100:]
            
            # Sauvegarder
            with open(monitoring_file, 'w') as f:
                json.dump({
                    'last_update': datetime.now().isoformat(),
                    'history': history
                }, f, indent=2)
            
            logger.info("Statistiques de monitoring sauvegardées")
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du monitoring: {e}")
        
        return monitoring_stats


def main():
    """Fonction principale"""
    # Parser les arguments
    parser = argparse.ArgumentParser(
        description="Synchronise les emails PIXID de Drive vers Sheets"
    )
    parser.add_argument(
        '--folder-id',
        default='1YevTmiEAycLE2X0g01juOO-cWm-O6V2F',
        help='ID du dossier Google Drive'
    )
    parser.add_argument(
        '--sheet-id',
        default='1eVoS4Pd6RiL-4PLaZWC5s8Yzax6VbT5D9Tz5K2deMs4',
        help='ID du Google Sheet'
    )
    parser.add_argument(
        '--credentials',
        help='Chemin vers le fichier credentials JSON'
    )
    parser.add_argument(
        '--state-file',
        default='sync_state.json',
        help='Fichier pour sauvegarder l\'état'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Mode verbose'
    )
    
    args = parser.parse_args()
    
    # Configurer le logging
    if args.verbose:
        logger.level("DEBUG")
    
    # Créer le dossier logs si nécessaire
    Path('logs').mkdir(exist_ok=True)
    
    # Exécuter la synchronisation
    try:
        synchronizer = PIXIDSynchronizer(
            folder_id=args.folder_id,
            spreadsheet_id=args.sheet_id,
            credentials_path=args.credentials,
            state_file=args.state_file
        )
        
        stats = synchronizer.sync()
        monitoring_stats = synchronizer.generate_monitoring_stats()
        
        # Code de sortie basé sur le statut
        if stats['status'] == 'error':
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
