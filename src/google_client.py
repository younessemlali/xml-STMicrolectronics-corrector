"""
Clients pour interagir avec Google Drive et Google Sheets
Utilise les API REST natives via Service Account
"""

import os
import io
import json
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
import pandas as pd
from loguru import logger

from . import FIELDS_TO_EXTRACT


class GoogleAuthenticator:
    """Gère l'authentification Google via Service Account"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/spreadsheets'
    ]
    
    @staticmethod
    def get_credentials(credentials_path: Optional[str] = None) -> service_account.Credentials:
        """
        Obtient les credentials du Service Account
        
        Args:
            credentials_path: Chemin vers le fichier JSON (optionnel)
            
        Returns:
            Credentials pour l'authentification
        """
        # Priorité : paramètre > env var > fichier par défaut
        if credentials_path:
            creds_source = credentials_path
        elif os.environ.get('GOOGLE_CREDENTIALS'):
            # Si c'est une string JSON dans l'env var
            creds_json = os.environ['GOOGLE_CREDENTIALS']
            if creds_json.strip().startswith('{'):
                # C'est du JSON direct
                creds_info = json.loads(creds_json)
                return service_account.Credentials.from_service_account_info(
                    creds_info, scopes=GoogleAuthenticator.SCOPES
                )
            else:
                # C'est un chemin de fichier
                creds_source = creds_json
        else:
            # Chercher un fichier credentials.json par défaut
            default_paths = [
                'credentials.json',
                'service-account.json',
                '.credentials/google.json'
            ]
            for path in default_paths:
                if os.path.exists(path):
                    creds_source = path
                    break
            else:
                raise ValueError(
                    "Aucune credential trouvée. Définissez GOOGLE_CREDENTIALS ou "
                    "placez credentials.json à la racine du projet"
                )
        
        # Charger depuis le fichier
        return service_account.Credentials.from_service_account_file(
            creds_source, scopes=GoogleAuthenticator.SCOPES
        )


class GoogleDriveClient:
    """Client pour interagir avec Google Drive"""
    
    def __init__(self, credentials: Optional[service_account.Credentials] = None):
        """
        Initialise le client Drive
        
        Args:
            credentials: Credentials du Service Account (optionnel)
        """
        if credentials is None:
            credentials = GoogleAuthenticator.get_credentials()
        
        self.service = build('drive', 'v3', credentials=credentials)
        self._processed_files_cache = set()
        logger.info("GoogleDriveClient initialisé")
    
    def list_files(self, folder_id: str, file_types: List[str] = ['.eml', '.txt'],
                   only_new: bool = True) -> List[Dict[str, Any]]:
        """
        Liste les fichiers dans un dossier Drive
        
        Args:
            folder_id: ID du dossier Drive
            file_types: Extensions de fichiers à chercher
            only_new: Si True, exclut les fichiers déjà traités
            
        Returns:
            Liste des métadonnées de fichiers
        """
        try:
            # Construire la query
            query_parts = [f"'{folder_id}' in parents", "trashed = false"]
            
            # Filtrer par type MIME si possible
            mime_types = []
            for ext in file_types:
                if ext == '.txt':
                    mime_types.append("mimeType='text/plain'")
                elif ext == '.eml':
                    mime_types.append("mimeType='message/rfc822'")
            
            if mime_types:
                query_parts.append(f"({' or '.join(mime_types)})")
            
            query = ' and '.join(query_parts)
            logger.debug(f"Query Drive: {query}")
            
            # Exécuter la requête
            results = []
            page_token = None
            
            while True:
                response = self.service.files().list(
                    q=query,
                    fields='nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, size)',
                    pageSize=1000,
                    pageToken=page_token,
                    orderBy='createdTime desc'
                ).execute()
                
                files = response.get('files', [])
                
                # Filtrer par extension si nécessaire
                for file in files:
                    name = file['name'].lower()
                    if any(name.endswith(ext.lower()) for ext in file_types):
                        # Vérifier si déjà traité
                        if only_new and file['id'] in self._processed_files_cache:
                            continue
                        results.append(file)
                
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
            
            logger.info(f"{len(results)} fichiers trouvés dans le dossier {folder_id}")
            return results
            
        except HttpError as e:
            logger.error(f"Erreur lors de la liste des fichiers: {e}")
            return []
    
    def download_file(self, file_id: str, file_name: str = None) -> Optional[bytes]:
        """
        Télécharge le contenu d'un fichier
        
        Args:
            file_id: ID du fichier Drive
            file_name: Nom du fichier (pour les logs)
            
        Returns:
            Contenu du fichier en bytes ou None si erreur
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            file_buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(file_buffer, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Téléchargement {file_name or file_id}: {int(status.progress() * 100)}%")
            
            content = file_buffer.getvalue()
            logger.info(f"Fichier téléchargé: {file_name or file_id} ({len(content)} bytes)")
            
            # Marquer comme traité
            self._processed_files_cache.add(file_id)
            
            return content
            
        except HttpError as e:
            logger.error(f"Erreur lors du téléchargement de {file_name or file_id}: {e}")
            return None
    
    def mark_as_processed(self, file_id: str):
        """Marque un fichier comme traité"""
        self._processed_files_cache.add(file_id)
    
    def get_processed_files(self) -> set:
        """Retourne l'ensemble des fichiers traités"""
        return self._processed_files_cache.copy()
    
    def load_processed_files(self, file_ids: List[str]):
        """Charge une liste de fichiers déjà traités"""
        self._processed_files_cache.update(file_ids)
        logger.info(f"{len(file_ids)} fichiers marqués comme déjà traités")


class GoogleSheetsClient:
    """Client pour interagir avec Google Sheets"""
    
    def __init__(self, credentials: Optional[service_account.Credentials] = None):
        """
        Initialise le client Sheets
        
        Args:
            credentials: Credentials du Service Account (optionnel)
        """
        if credentials is None:
            credentials = GoogleAuthenticator.get_credentials()
        
        self.client = gspread.authorize(credentials)
        self.sheet = None
        self.worksheet = None
        logger.info("GoogleSheetsClient initialisé")
    
    def open_sheet(self, spreadsheet_id: str, worksheet_name: str = None) -> Tuple[gspread.Spreadsheet, gspread.Worksheet]:
        """
        Ouvre une feuille Google Sheets
        
        Args:
            spreadsheet_id: ID du spreadsheet
            worksheet_name: Nom de la feuille (par défaut: première feuille)
            
        Returns:
            Tuple (spreadsheet, worksheet)
        """
        try:
            self.sheet = self.client.open_by_key(spreadsheet_id)
            
            if worksheet_name:
                self.worksheet = self.sheet.worksheet(worksheet_name)
            else:
                self.worksheet = self.sheet.sheet1  # Première feuille
            
            logger.info(f"Feuille ouverte: {self.sheet.title} / {self.worksheet.title}")
            return self.sheet, self.worksheet
            
        except Exception as e:
            logger.error(f"Erreur lors de l'ouverture de la feuille {spreadsheet_id}: {e}")
            raise
    
    def ensure_headers(self, headers: List[str] = None) -> bool:
        """
        S'assure que les headers nécessaires existent dans la feuille
        
        Args:
            headers: Liste des headers requis (par défaut: FIELDS_TO_EXTRACT)
            
        Returns:
            True si les headers ont été créés/mis à jour
        """
        if not self.worksheet:
            raise ValueError("Aucune feuille ouverte. Appelez open_sheet() d'abord")
        
        if headers is None:
            # Headers par défaut avec métadonnées
            headers = ['date_extraction', 'fichier_source', 'file_id'] + FIELDS_TO_EXTRACT
        
        try:
            # Récupérer les headers existants
            existing_headers = self.worksheet.row_values(1)
            
            if not existing_headers:
                # Créer tous les headers
                self.worksheet.update('A1', [headers])
                logger.info(f"Headers créés: {headers}")
                return True
            
            # Vérifier et ajouter les headers manquants
            updated = False
            for header in headers:
                if header not in existing_headers:
                    # Ajouter à la fin
                    col_letter = gspread.utils.rowcol_to_a1(1, len(existing_headers) + 1)[:-1]
                    self.worksheet.update(f'{col_letter}1', header)
                    existing_headers.append(header)
                    logger.info(f"Header ajouté: {header}")
                    updated = True
            
            return updated
            
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des headers: {e}")
            return False
    
    def get_data(self, as_dict: bool = True) -> pd.DataFrame:
        """
        Récupère toutes les données de la feuille
        
        Args:
            as_dict: Si True, retourne les records comme liste de dicts
            
        Returns:
            DataFrame pandas avec les données
        """
        if not self.worksheet:
            raise ValueError("Aucune feuille ouverte. Appelez open_sheet() d'abord")
        
        try:
            # Utiliser gspread_dataframe pour récupérer efficacement
            df = get_as_dataframe(self.worksheet, evaluate_formulas=True)
            
            # Nettoyer les lignes et colonnes vides
            df = df.dropna(how='all').dropna(axis=1, how='all')
            
            logger.info(f"{len(df)} lignes récupérées de la feuille")
            return df
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des données: {e}")
            return pd.DataFrame()
    
    def append_rows(self, data: List[Dict[str, Any]], check_duplicates: bool = True) -> int:
        """
        Ajoute des lignes à la feuille
        
        Args:
            data: Liste de dictionnaires avec les données
            check_duplicates: Si True, vérifie les doublons par numero_commande
            
        Returns:
            Nombre de lignes ajoutées
        """
        if not self.worksheet or not data:
            return 0
        
        try:
            # Récupérer les données existantes pour vérifier les doublons
            existing_df = pd.DataFrame()
            if check_duplicates:
                existing_df = self.get_data()
            
            # Convertir en DataFrame
            new_df = pd.DataFrame(data)
            
            # Ajouter métadonnées
            new_df['date_extraction'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Filtrer les doublons si demandé
            if check_duplicates and not existing_df.empty and 'numero_commande' in existing_df.columns:
                existing_orders = set(existing_df['numero_commande'].dropna().astype(str))
                
                # Filtrer les nouvelles lignes
                before_count = len(new_df)
                new_df = new_df[~new_df['numero_commande'].astype(str).isin(existing_orders)]
                
                if before_count > len(new_df):
                    logger.info(f"{before_count - len(new_df)} doublons filtrés")
            
            if new_df.empty:
                logger.info("Aucune nouvelle ligne à ajouter")
                return 0
            
            # Obtenir les headers actuels
            headers = self.worksheet.row_values(1)
            
            # Réorganiser les colonnes selon les headers
            new_df = new_df.reindex(columns=headers, fill_value='')
            
            # Convertir en liste de listes pour l'append
            values = new_df.values.tolist()
            
            # Ajouter à la feuille
            self.worksheet.append_rows(values, value_input_option='USER_ENTERED')
            
            logger.info(f"{len(values)} lignes ajoutées à la feuille")
            return len(values)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout des lignes: {e}")
            return 0
    
    def find_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Trouve une ligne par numéro de commande
        
        Args:
            order_id: Numéro de commande à chercher
            
        Returns:
            Dict avec les données ou None si non trouvé
        """
        try:
            df = self.get_data()
            
            if df.empty or 'numero_commande' not in df.columns:
                return None
            
            # Rechercher la commande
            mask = df['numero_commande'].astype(str) == str(order_id)
            results = df[mask]
            
            if results.empty:
                return None
            
            # Retourner la première correspondance
            return results.iloc[0].to_dict()
            
        except Exception as e:
            logger.error(f"Erreur lors de la recherche de la commande {order_id}: {e}")
            return None
    
    def get_processed_file_ids(self) -> List[str]:
        """
        Récupère la liste des file_id déjà traités
        
        Returns:
            Liste des file_id
        """
        try:
            df = self.get_data()
            
            if df.empty or 'file_id' not in df.columns:
                return []
            
            return df['file_id'].dropna().unique().tolist()
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des file_id: {e}")
            return []
