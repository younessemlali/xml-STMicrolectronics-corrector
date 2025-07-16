"""
Module de monitoring et collecte de statistiques pour PIXID Automation
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict, Counter
import pandas as pd
import numpy as np
from loguru import logger


class MonitoringCollector:
    """
    Collecte et agrège les statistiques d'exécution
    """
    
    def __init__(self, data_file: str = "monitoring_data.json"):
        """
        Initialise le collecteur de monitoring
        
        Args:
            data_file: Fichier pour stocker les données de monitoring
        """
        self.data_file = Path(data_file)
        self.current_run = {
            'run_id': f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'start_time': datetime.now().isoformat(),
            'events': [],
            'metrics': defaultdict(int),
            'errors': []
        }
        logger.info("MonitoringCollector initialisé")
    
    def log_event(self, event_type: str, data: Dict[str, Any]):
        """
        Enregistre un événement
        
        Args:
            event_type: Type d'événement (file_processed, error, etc.)
            data: Données associées à l'événement
        """
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'data': data
        }
        self.current_run['events'].append(event)
        
        # Incrémenter les métriques automatiquement
        self.current_run['metrics'][f'event_{event_type}'] += 1
    
    def record_metric(self, metric_name: str, value: Any):
        """
        Enregistre une métrique
        
        Args:
            metric_name: Nom de la métrique
            value: Valeur de la métrique
        """
        self.current_run['metrics'][metric_name] = value
    
    def increment_metric(self, metric_name: str, value: int = 1):
        """
        Incrémente une métrique
        
        Args:
            metric_name: Nom de la métrique
            value: Valeur à ajouter (par défaut: 1)
        """
        self.current_run['metrics'][metric_name] += value
    
    def record_error(self, error_type: str, error_message: str, context: Optional[Dict] = None):
        """
        Enregistre une erreur
        
        Args:
            error_type: Type d'erreur
            error_message: Message d'erreur
            context: Contexte additionnel
        """
        error = {
            'timestamp': datetime.now().isoformat(),
            'type': error_type,
            'message': error_message,
            'context': context or {}
        }
        self.current_run['errors'].append(error)
        self.increment_metric('total_errors')
    
    def finalize_run(self) -> Dict[str, Any]:
        """
        Finalise l'exécution courante et sauvegarde les données
        
        Returns:
            Statistiques de l'exécution
        """
        # Calculer la durée
        start_time = datetime.fromisoformat(self.current_run['start_time'])
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        self.current_run['end_time'] = end_time.isoformat()
        self.current_run['duration_seconds'] = duration
        self.current_run['metrics'] = dict(self.current_run['metrics'])  # Convertir defaultdict
        
        # Déterminer le statut
        if self.current_run['errors']:
            self.current_run['status'] = 'error' if len(self.current_run['errors']) > 5 else 'partial'
        else:
            self.current_run['status'] = 'success'
        
        # Sauvegarder
        self._save_run()
        
        return self.current_run
    
    def _save_run(self):
        """Sauvegarde l'exécution courante dans le fichier de monitoring"""
        try:
            # Charger l'historique existant
            history = self._load_history()
            
            # Ajouter l'exécution courante
            history['runs'].append(self.current_run)
            
            # Garder seulement les 1000 dernières exécutions
            history['runs'] = history['runs'][-1000:]
            
            # Mettre à jour les métadonnées
            history['last_update'] = datetime.now().isoformat()
            history['total_runs'] = len(history['runs'])
            
            # Sauvegarder
            with open(self.data_file, 'w') as f:
                json.dump(history, f, indent=2)
            
            logger.info(f"Monitoring sauvegardé: {self.current_run['run_id']}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du monitoring: {e}")
    
    def _load_history(self) -> Dict[str, Any]:
        """Charge l'historique de monitoring"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # Structure par défaut
        return {
            'version': '1.0',
            'created': datetime.now().isoformat(),
            'last_update': datetime.now().isoformat(),
            'total_runs': 0,
            'runs': []
        }
    
    def get_statistics(self, hours: Optional[int] = None) -> Dict[str, Any]:
        """
        Calcule les statistiques sur une période donnée
        
        Args:
            hours: Nombre d'heures à analyser (None = tout l'historique)
            
        Returns:
            Dictionnaire de statistiques
        """
        history = self._load_history()
        runs = history.get('runs', [])
        
        if not runs:
            return {'error': 'Aucune donnée disponible'}
        
        # Filtrer par période si demandé
        if hours:
            cutoff = datetime.now() - timedelta(hours=hours)
            runs = [r for r in runs if datetime.fromisoformat(r['start_time']) > cutoff]
        
        if not runs:
            return {'error': f'Aucune donnée dans les {hours} dernières heures'}
        
        # Convertir en DataFrame pour faciliter l'analyse
        df = pd.DataFrame(runs)
        
        # Statistiques générales
        stats = {
            'period': f'Dernières {hours} heures' if hours else 'Tout l\'historique',
            'total_runs': len(runs),
            'first_run': runs[0]['start_time'],
            'last_run': runs[-1]['start_time'],
            
            # Taux de succès
            'success_rate': (df['status'] == 'success').mean() * 100,
            'error_rate': (df['status'] == 'error').mean() * 100,
            'partial_rate': (df['status'] == 'partial').mean() * 100,
            
            # Durées
            'avg_duration': df['duration_seconds'].mean(),
            'min_duration': df['duration_seconds'].min(),
            'max_duration': df['duration_seconds'].max(),
            
            # Métriques agrégées
            'total_files_processed': sum(r['metrics'].get('files_processed', 0) for r in runs),
            'total_rows_added': sum(r['metrics'].get('rows_added', 0) for r in runs),
            'total_errors': sum(len(r.get('errors', [])) for r in runs),
        }
        
        # Tendances par heure
        df['hour'] = pd.to_datetime(df['start_time']).dt.floor('H')
        hourly_stats = []
        
        for hour, group in df.groupby('hour'):
            hourly_stats.append({
                'hour': hour.isoformat(),
                'runs': len(group),
                'success_rate': (group['status'] == 'success').mean() * 100,
                'avg_duration': group['duration_seconds'].mean()
            })
        
        stats['hourly_trends'] = hourly_stats
        
        # Top erreurs
        all_errors = []
        for run in runs:
            for error in run.get('errors', []):
                all_errors.append(error['type'])
        
        error_counts = Counter(all_errors)
        stats['top_errors'] = [
            {'type': err_type, 'count': count}
            for err_type, count in error_counts.most_common(10)
        ]
        
        return stats
    
    def get_recent_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Récupère les exécutions récentes
        
        Args:
            limit: Nombre maximum d'exécutions à retourner
            
        Returns:
            Liste des exécutions récentes
        """
        history = self._load_history()
        runs = history.get('runs', [])
        
        # Retourner les plus récentes
        recent_runs = runs[-limit:]
        
        # Simplifier pour l'affichage
        simplified = []
        for run in reversed(recent_runs):  # Plus récent en premier
            simplified.append({
                'run_id': run['run_id'],
                'start_time': run['start_time'],
                'duration': f"{run['duration_seconds']:.1f}s",
                'status': run['status'],
                'files_processed': run['metrics'].get('files_processed', 0),
                'rows_added': run['metrics'].get('rows_added', 0),
                'errors': len(run.get('errors', []))
            })
        
        return simplified
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Calcule les métriques de performance détaillées
        
        Returns:
            Métriques de performance
        """
        history = self._load_history()
        runs = history.get('runs', [])
        
        if not runs:
            return {}
        
        # Extraire les durées
        durations = [r['duration_seconds'] for r in runs if 'duration_seconds' in r]
        
        if not durations:
            return {}
        
        # Calculer les percentiles
        metrics = {
            'duration_p50': np.percentile(durations, 50),
            'duration_p90': np.percentile(durations, 90),
            'duration_p95': np.percentile(durations, 95),
            'duration_p99': np.percentile(durations, 99),
            'duration_mean': np.mean(durations),
            'duration_std': np.std(durations),
            
            # Taux de traitement
            'avg_files_per_run': np.mean([
                r['metrics'].get('files_processed', 0) 
                for r in runs
            ]),
            'max_files_per_run': max([
                r['metrics'].get('files_processed', 0) 
                for r in runs
            ], default=0),
            
            # Efficacité
            'avg_extraction_rate': np.mean([
                r['metrics'].get('extraction_success', 0) / max(r['metrics'].get('files_processed', 1), 1) * 100
                for r in runs if r['metrics'].get('files_processed', 0) > 0
            ]) if runs else 0
        }
        
        return metrics
    
    def generate_health_check(self) -> Dict[str, Any]:
        """
        Génère un rapport de santé du système
        
        Returns:
            Rapport de santé avec statut et recommandations
        """
        stats = self.get_statistics(hours=24)
        recent_runs = self.get_recent_runs(limit=10)
        
        health = {
            'status': 'healthy',
            'checks': [],
            'recommendations': []
        }
        
        # Vérifier le taux de succès
        success_rate = stats.get('success_rate', 0)
        if success_rate < 50:
            health['status'] = 'critical'
            health['checks'].append({
                'name': 'Success Rate',
                'status': 'critical',
                'value': f"{success_rate:.1f}%",
                'message': 'Taux de succès très bas'
            })
            health['recommendations'].append(
                'Vérifier les credentials Google et les permissions'
            )
        elif success_rate < 80:
            health['status'] = 'warning'
            health['checks'].append({
                'name': 'Success Rate',
                'status': 'warning',
                'value': f"{success_rate:.1f}%",
                'message': 'Taux de succès en dessous du seuil'
            })
        else:
            health['checks'].append({
                'name': 'Success Rate',
                'status': 'healthy',
                'value': f"{success_rate:.1f}%",
                'message': 'Taux de succès normal'
            })
        
        # Vérifier la dernière exécution
        if recent_runs:
            last_run = recent_runs[0]
            last_run_time = datetime.fromisoformat(last_run['start_time'])
            time_since_last = (datetime.now() - last_run_time).total_seconds() / 60
            
            if time_since_last > 30:  # Plus de 30 minutes
                health['status'] = 'warning' if health['status'] == 'healthy' else health['status']
                health['checks'].append({
                    'name': 'Last Run',
                    'status': 'warning',
                    'value': f"{time_since_last:.0f} minutes ago",
                    'message': 'Aucune exécution récente'
                })
                health['recommendations'].append(
                    'Vérifier que le cron GitHub Actions fonctionne'
                )
            else:
                health['checks'].append({
                    'name': 'Last Run',
                    'status': 'healthy',
                    'value': f"{time_since_last:.0f} minutes ago",
                    'message': 'Exécution récente détectée'
                })
        
        # Vérifier les erreurs
        total_errors = stats.get('total_errors', 0)
        if total_errors > 50:
            health['status'] = 'warning' if health['status'] == 'healthy' else health['status']
            health['checks'].append({
                'name': 'Error Count',
                'status': 'warning',
                'value': f"{total_errors} errors",
                'message': 'Nombre élevé d\'erreurs'
            })
            health['recommendations'].append(
                'Analyser les logs pour identifier les causes d\'erreur'
            )
        
        # Score de santé global
        health['score'] = {
            'healthy': 100,
            'warning': 75,
            'critical': 25
        }.get(health['status'], 50)
        
        return health
    
    def export_metrics_csv(self, output_file: str = "monitoring_metrics.csv"):
        """
        Exporte les métriques au format CSV
        
        Args:
            output_file: Nom du fichier de sortie
        """
        history = self._load_history()
        runs = history.get('runs', [])
        
        if not runs:
            logger.warning("Aucune donnée à exporter")
            return
        
        # Préparer les données pour l'export
        rows = []
        for run in runs:
            row = {
                'run_id': run['run_id'],
                'start_time': run['start_time'],
                'end_time': run.get('end_time', ''),
                'duration_seconds': run.get('duration_seconds', 0),
                'status': run['status'],
                'error_count': len(run.get('errors', []))
            }
            
            # Ajouter les métriques
            for metric_name, value in run.get('metrics', {}).items():
                row[f'metric_{metric_name}'] = value
            
            rows.append(row)
        
        # Créer le DataFrame et exporter
        df = pd.DataFrame(rows)
        df.to_csv(output_file, index=False)
        
        logger.info(f"Métriques exportées vers {output_file}")
