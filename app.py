"""
Application Streamlit PIXID - Enrichissement XML et Dashboard de Monitoring
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
from typing import Dict, Optional, Any, List
import base64

# Import des modules personnalisés
from src import (
    GoogleSheetsClient,
    GoogleAuthenticator,
    XMLProcessor,
    MonitoringCollector,
    XML_FIELD_MAPPING,
    FIELDS_TO_EXTRACT,
    logger
)

# Configuration de la page
st.set_page_config(
    page_title="PIXID Automation Platform",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/your-repo/pixid-automation',
        'Report a bug': 'https://github.com/your-repo/pixid-automation/issues',
        'About': "PIXID Automation Platform - Synchronisation et enrichissement des données RH"
    }
)

# Style CSS personnalisé
st.markdown("""
<style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .success-metric {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
    }
    
    .warning-metric {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
    }
    
    .error-metric {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
    }
    
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #e7f3ff;
        border: 1px solid #2196F3;
        margin: 1rem 0;
    }
    
    div[data-testid="stSidebar"] {
        background-color: #f0f2f6;
    }
</style>
""", unsafe_allow_html=True)


class PIXIDStreamlitApp:
    """Application Streamlit principale pour PIXID Automation"""
    
    def __init__(self):
        """Initialise l'application"""
        self.init_session_state()
        self.setup_sidebar()
    
    def init_session_state(self):
        """Initialise les variables de session"""
        if 'sheets_client' not in st.session_state:
            st.session_state.sheets_client = None
        if 'sheets_data' not in st.session_state:
            st.session_state.sheets_data = None
        if 'last_refresh' not in st.session_state:
            st.session_state.last_refresh = None
        if 'monitoring_data' not in st.session_state:
            st.session_state.monitoring_data = None
    
    def setup_sidebar(self):
        """Configure la barre latérale"""
        with st.sidebar:
            st.image("https://via.placeholder.com/300x100/2196F3/FFFFFF?text=PIXID+Automation", width=300)
            st.markdown("---")
            
            # Navigation
            st.header("🧭 Navigation")
            self.page = st.radio(
                "Choisir une fonctionnalité",
                [
                    "📊 Dashboard Monitoring",
                    "📝 Enrichissement XML",
                    "🔍 Recherche Commande",
                    "⚙️ Configuration"
                ],
                index=0
            )
            
            st.markdown("---")
            
            # Statut de connexion
            self._show_connection_status()
            
            st.markdown("---")
            
            # Actions rapides
            st.header("⚡ Actions rapides")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Rafraîchir", use_container_width=True):
                    st.session_state.sheets_data = None
                    st.session_state.monitoring_data = None
                    st.rerun()
            
            with col2:
                if st.button("📥 Export", use_container_width=True):
                    self._export_data()
    
    def _show_connection_status(self):
        """Affiche le statut de connexion Google"""
        st.subheader("📡 Statut connexion")
        
        try:
            if st.session_state.sheets_client is None:
                credentials = GoogleAuthenticator.get_credentials()
                st.session_state.sheets_client = GoogleSheetsClient(credentials)
            
            st.success("✅ Connecté à Google")
            
            if st.session_state.last_refresh:
                st.caption(f"Dernière MAJ: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
            
        except Exception as e:
            st.error("❌ Non connecté")
            st.caption(str(e))
    
    def run(self):
        """Lance l'application selon la page sélectionnée"""
        # Titre principal
        st.title("🤖 PIXID Automation Platform")
        
        # Router vers la bonne page
        if self.page == "📊 Dashboard Monitoring":
            self.show_monitoring_dashboard()
        elif self.page == "📝 Enrichissement XML":
            self.show_xml_enrichment()
        elif self.page == "🔍 Recherche Commande":
            self.show_order_search()
        elif self.page == "⚙️ Configuration":
            self.show_configuration()
    
    def show_monitoring_dashboard(self):
        """Affiche le dashboard de monitoring"""
        st.header("📊 Dashboard de Monitoring")
        
        # Charger les données de monitoring
        monitoring_data = self._load_monitoring_data()
        
        if not monitoring_data:
            st.warning("Aucune donnée de monitoring disponible")
            return
        
        # Tabs pour différentes vues
        tab1, tab2, tab3, tab4 = st.tabs([
            "🎯 Vue d'ensemble", 
            "📈 Tendances", 
            "🚨 Erreurs",
            "🏥 Santé système"
        ])
        
        with tab1:
            self._show_overview_metrics(monitoring_data)
        
        with tab2:
            self._show_trends(monitoring_data)
        
        with tab3:
            self._show_errors_analysis(monitoring_data)
        
        with tab4:
            self._show_health_check(monitoring_data)
    
    def _show_overview_metrics(self, data: Dict):
        """Affiche les métriques principales"""
        # Calculer les statistiques
        collector = MonitoringCollector()
        stats_24h = collector.get_statistics(hours=24)
        stats_7d = collector.get_statistics(hours=168)
        recent_runs = collector.get_recent_runs(limit=10)
        
        # Métriques en colonnes
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            success_rate = stats_24h.get('success_rate', 0)
            delta = success_rate - stats_7d.get('success_rate', 0)
            st.metric(
                "Taux de succès (24h)",
                f"{success_rate:.1f}%",
                delta=f"{delta:+.1f}%",
                delta_color="normal" if delta >= 0 else "inverse"
            )
        
        with col2:
            total_files = stats_24h.get('total_files_processed', 0)
            st.metric(
                "Fichiers traités (24h)",
                f"{total_files:,}",
                delta=f"+{recent_runs[0]['files_processed']}" if recent_runs else None
            )
        
        with col3:
            avg_duration = stats_24h.get('avg_duration', 0)
            st.metric(
                "Durée moyenne",
                f"{avg_duration:.1f}s",
                delta=None
            )
        
        with col4:
            total_errors = stats_24h.get('total_errors', 0)
            st.metric(
                "Erreurs (24h)",
                total_errors,
                delta_color="inverse"
            )
        
        # Tableau des exécutions récentes
        st.subheader("📋 Exécutions récentes")
        
        if recent_runs:
            df_runs = pd.DataFrame(recent_runs)
            
            # Formatter le tableau
            df_runs['start_time'] = pd.to_datetime(df_runs['start_time']).dt.strftime('%Y-%m-%d %H:%M')
            
            # Colorer selon le statut
            def highlight_status(row):
                colors = {
                    'success': 'background-color: #d4edda',
                    'partial': 'background-color: #fff3cd',
                    'error': 'background-color: #f8d7da'
                }
                return [colors.get(row['status'], '')] * len(row)
            
            styled_df = df_runs.style.apply(highlight_status, axis=1)
            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "run_id": st.column_config.TextColumn("ID", width="small"),
                    "start_time": st.column_config.TextColumn("Date/Heure"),
                    "duration": st.column_config.TextColumn("Durée"),
                    "status": st.column_config.TextColumn("Statut"),
                    "files_processed": st.column_config.NumberColumn("Fichiers"),
                    "rows_added": st.column_config.NumberColumn("Lignes"),
                    "errors": st.column_config.NumberColumn("Erreurs")
                }
            )
        else:
            st.info("Aucune exécution récente")
    
    def _show_trends(self, data: Dict):
        """Affiche les graphiques de tendances"""
        collector = MonitoringCollector()
        stats = collector.get_statistics(hours=168)  # 7 jours
        
        if 'hourly_trends' in stats and stats['hourly_trends']:
            # Préparer les données
            df_trends = pd.DataFrame(stats['hourly_trends'])
            df_trends['hour'] = pd.to_datetime(df_trends['hour'])
            
            # Graphique du nombre d'exécutions
            col1, col2 = st.columns(2)
            
            with col1:
                fig_runs = px.line(
                    df_trends,
                    x='hour',
                    y='runs',
                    title='Nombre d\'exécutions par heure',
                    markers=True
                )
                fig_runs.update_layout(
                    xaxis_title="Heure",
                    yaxis_title="Exécutions",
                    hovermode='x unified'
                )
                st.plotly_chart(fig_runs, use_container_width=True)
            
            with col2:
                fig_success = px.line(
                    df_trends,
                    x='hour',
                    y='success_rate',
                    title='Taux de succès par heure',
                    markers=True,
                    color_discrete_sequence=['#28a745']
                )
                fig_success.update_layout(
                    xaxis_title="Heure",
                    yaxis_title="Taux de succès (%)",
                    yaxis_range=[0, 105],
                    hovermode='x unified'
                )
                st.plotly_chart(fig_success, use_container_width=True)
            
            # Graphique des durées
            fig_duration = px.box(
                df_trends,
                x=df_trends['hour'].dt.date,
                y='avg_duration',
                title='Distribution des durées d\'exécution',
                color_discrete_sequence=['#2196F3']
            )
            fig_duration.update_layout(
                xaxis_title="Date",
                yaxis_title="Durée (secondes)",
                showlegend=False
            )
            st.plotly_chart(fig_duration, use_container_width=True)
            
        else:
            st.info("Pas assez de données pour afficher les tendances")
    
    def _show_errors_analysis(self, data: Dict):
        """Affiche l'analyse des erreurs"""
        collector = MonitoringCollector()
        stats = collector.get_statistics(hours=168)
        
        if 'top_errors' in stats and stats['top_errors']:
            # Graphique des top erreurs
            df_errors = pd.DataFrame(stats['top_errors'])
            
            fig_errors = px.bar(
                df_errors,
                x='count',
                y='type',
                orientation='h',
                title='Top 10 des types d\'erreurs',
                color='count',
                color_continuous_scale='Reds'
            )
            fig_errors.update_layout(
                xaxis_title="Nombre d'occurrences",
                yaxis_title="Type d'erreur",
                showlegend=False
            )
            st.plotly_chart(fig_errors, use_container_width=True)
            
            # Détails des erreurs récentes
            st.subheader("🔍 Erreurs récentes détaillées")
            
            # Charger les dernières exécutions avec erreurs
            history = self._load_monitoring_history()
            recent_errors = []
            
            for run in reversed(history.get('runs', [])[-20:]):
                for error in run.get('errors', []):
                    recent_errors.append({
                        'timestamp': error['timestamp'],
                        'type': error['type'],
                        'message': error['message'][:100] + '...' if len(error['message']) > 100 else error['message'],
                        'run_id': run['run_id']
                    })
            
            if recent_errors:
                df_recent = pd.DataFrame(recent_errors[:20])  # Limiter à 20
                st.dataframe(df_recent, use_container_width=True, hide_index=True)
            else:
                st.success("Aucune erreur récente!")
        else:
            st.success("✅ Aucune erreur détectée!")
    
    def _show_health_check(self, data: Dict):
        """Affiche le health check du système"""
        collector = MonitoringCollector()
        health = collector.generate_health_check()
        
        # Score global
        score = health.get('score', 0)
        status = health.get('status', 'unknown')
        
        # Couleur selon le statut
        color_map = {
            'healthy': '#28a745',
            'warning': '#ffc107',
            'critical': '#dc3545'
        }
        
        # Afficher le score
        col1, col2 = st.columns([1, 2])
        
        with col1:
            # Gauge chart pour le score
            fig_gauge = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = score,
                domain = {'x': [0, 1], 'y': [0, 1]},
                title = {'text': "Score de santé"},
                gauge = {
                    'axis': {'range': [None, 100]},
                    'bar': {'color': color_map.get(status, '#6c757d')},
                    'steps': [
                        {'range': [0, 25], 'color': "#f8d7da"},
                        {'range': [25, 75], 'color': "#fff3cd"},
                        {'range': [75, 100], 'color': "#d4edda"}
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': 90
                    }
                }
            ))
            fig_gauge.update_layout(height=300)
            st.plotly_chart(fig_gauge, use_container_width=True)
        
        with col2:
            st.subheader(f"Statut: {status.upper()}")
            
            # Checks individuels
            for check in health.get('checks', []):
                icon = {
                    'healthy': '✅',
                    'warning': '⚠️',
                    'critical': '❌'
                }.get(check['status'], '❓')
                
                st.write(f"{icon} **{check['name']}**: {check['value']}")
                st.caption(check['message'])
            
            # Recommandations
            if health.get('recommendations'):
                st.subheader("💡 Recommandations")
                for rec in health['recommendations']:
                    st.info(f"• {rec}")
    
    def show_xml_enrichment(self):
        """Page d'enrichissement XML"""
        st.header("📝 Enrichissement XML")
        
        # Charger les données Sheets si nécessaire
        if st.session_state.sheets_data is None:
            self._load_sheets_data()
        
        # Interface d'upload
        col1, col2 = st.columns([2, 1])
        
        with col1:
            uploaded_file = st.file_uploader(
                "Sélectionner un fichier XML",
                type=['xml'],
                help="Le fichier doit contenir une balise OrderId"
            )
        
        with col2:
            st.markdown("""
            <div class="info-box">
            <h4>📌 Guide rapide</h4>
            <ol>
            <li>Uploadez votre XML</li>
            <li>L'OrderId sera détecté</li>
            <li>Les données seront récupérées</li>
            <li>Le XML sera enrichi</li>
            <li>Téléchargez le résultat</li>
            </ol>
            </div>
            """, unsafe_allow_html=True)
        
        if uploaded_file:
            self._process_xml_file(uploaded_file)
    
    def _process_xml_file(self, uploaded_file):
        """Traite le fichier XML uploadé"""
        try:
            # Lire le contenu
            xml_content = uploaded_file.read()
            processor = XMLProcessor()
            
            # Valider le XML
            st.subheader("1️⃣ Validation du fichier")
            validation = processor.validate_xml(xml_content)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if validation['valid']:
                    st.success("✅ XML valide")
                else:
                    st.error("❌ XML invalide")
                    st.write(validation['errors'])
                    return
            
            with col2:
                if validation['has_order_id']:
                    st.success(f"✅ OrderId: {validation['order_id']}")
                else:
                    st.error("❌ OrderId non trouvé")
                    return
            
            with col3:
                if validation['has_pixid_section']:
                    st.info("ℹ️ Déjà enrichi")
                else:
                    st.info("ℹ️ Non enrichi")
            
            # Rechercher les données
            order_id = validation['order_id']
            st.subheader("2️⃣ Recherche des données")
            
            order_data = self._search_order_data(order_id)
            
            if order_data:
                # Afficher les données trouvées
                st.success("✅ Données trouvées!")
                
                # Afficher en colonnes
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**Informations générales:**")
                    for field in ['code_agence', 'code_unite', 'statut']:
                        if field in order_data and order_data[field]:
                            st.write(f"• **{field.replace('_', ' ').title()}:** {order_data[field]}")
                
                with col2:
                    st.write("**Informations complémentaires:**")
                    for field in ['niveau_convention_collective', 'classification_interimaire', 'personne_absente']:
                        if field in order_data and order_data[field]:
                            st.write(f"• **{field.replace('_', ' ').title()}:** {order_data[field]}")
                
                # Enrichir le XML
                st.subheader("3️⃣ Enrichissement")
                
                if st.button("🚀 Enrichir le XML", type="primary", use_container_width=True):
                    enriched_xml = processor.enrich_xml(xml_content, order_data)
                    
                    if enriched_xml:
                        st.success("✅ XML enrichi avec succès!")
                        
                        # Comparer avant/après
                        comparison = processor.compare_xml(xml_content, enriched_xml)
                        st.info(f"📊 {comparison.get('new_count', 0)} nouveaux éléments ajoutés")
                        
                        # Prévisualisation
                        with st.expander("👁️ Prévisualiser le XML enrichi"):
                            st.code(processor.prettify_xml(enriched_xml), language='xml')
                        
                        # Téléchargement
                        st.subheader("4️⃣ Téléchargement")
                        
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"enriched_{order_id}_{timestamp}.xml"
                        
                        st.download_button(
                            label="📥 Télécharger le XML enrichi",
                            data=enriched_xml,
                            file_name=filename,
                            mime="application/xml",
                            type="primary",
                            use_container_width=True
                        )
                    else:
                        st.error("❌ Erreur lors de l'enrichissement")
            else:
                st.warning(f"⚠️ Aucune donnée trouvée pour la commande {order_id}")
                st.info("Vérifiez que cette commande existe dans Google Sheets")
                
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
            logger.error(f"Erreur enrichissement XML: {e}")
    
    def show_order_search(self):
        """Page de recherche de commande"""
        st.header("🔍 Recherche de commande")
        
        # Charger les données
        if st.session_state.sheets_data is None:
            self._load_sheets_data()
        
        if st.session_state.sheets_data is None:
            st.error("Impossible de charger les données")
            return
        
        # Barre de recherche
        search_term = st.text_input(
            "Rechercher par numéro de commande, code agence ou code unité",
            placeholder="Ex: 12345, AG-001, UN-123"
        )
        
        if search_term:
            # Rechercher dans les données
            df = st.session_state.sheets_data
            
            # Recherche multi-colonnes
            mask = (
                df['numero_commande'].astype(str).str.contains(search_term, case=False, na=False) |
                df['code_agence'].astype(str).str.contains(search_term, case=False, na=False) |
                df['code_unite'].astype(str).str.contains(search_term, case=False, na=False)
            )
            
            results = df[mask]
            
            if not results.empty:
                st.success(f"✅ {len(results)} résultat(s) trouvé(s)")
                
                # Afficher les résultats
                st.dataframe(
                    results,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "date_extraction": st.column_config.DatetimeColumn(
                            "Date extraction",
                            format="DD/MM/YYYY HH:mm"
                        ),
                        "numero_commande": st.column_config.TextColumn("N° Commande"),
                        "code_agence": st.column_config.TextColumn("Code Agence"),
                        "code_unite": st.column_config.TextColumn("Code Unité"),
                        "statut": st.column_config.TextColumn("Statut")
                    }
                )
                
                # Export des résultats
                if st.button("📥 Exporter les résultats"):
                    csv = results.to_csv(index=False)
                    st.download_button(
                        label="Télécharger CSV",
                        data=csv,
                        file_name=f"recherche_{search_term}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
            else:
                st.warning(f"Aucun résultat pour '{search_term}'")
        
        # Statistiques globales
        with st.expander("📊 Statistiques globales"):
            if st.session_state.sheets_data is not None:
                df = st.session_state.sheets_data
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Total commandes", len(df))
                    st.metric("Agences uniques", df['code_agence'].nunique())
                
                with col2:
                    st.metric("Dernière extraction", df['date_extraction'].max())
                    st.metric("Unités uniques", df['code_unite'].nunique())
                
                with col3:
                    # Top statuts
                    top_statuts = df['statut'].value_counts().head(3)
                    st.write("**Top statuts:**")
                    for statut, count in top_statuts.items():
                        st.write(f"• {statut}: {count}")
    
    def show_configuration(self):
        """Page de configuration"""
        st.header("⚙️ Configuration")
        
        tabs = st.tabs(["🔑 Authentification", "📁 Ressources", "ℹ️ À propos"])
        
        with tabs[0]:
            st.subheader("Configuration Google Service Account")
            
            st.info("""
            **Pour configurer l'authentification:**
            1. Créez un Service Account dans Google Cloud Console
            2. Téléchargez le fichier JSON de credentials
            3. Définissez la variable d'environnement `GOOGLE_CREDENTIALS`
            4. Partagez vos ressources Google avec l'email du Service Account
            """)
            
            # Test de connexion
            if st.button("🔧 Tester la connexion"):
                with st.spinner("Test en cours..."):
                    try:
                        credentials = GoogleAuthenticator.get_credentials()
                        client = GoogleSheetsClient(credentials)
                        st.success("✅ Connexion réussie!")
                        
                        # Afficher les infos du service account
                        if hasattr(credentials, '_service_account_email'):
                            st.info(f"Service Account: {credentials._service_account_email}")
                    except Exception as e:
                        st.error(f"❌ Erreur: {str(e)}")
        
        with tabs[1]:
            st.subheader("Ressources Google")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**🗂️ Google Drive:**")
                st.code("1YevTmiEAycLE2X0g01juOO-cWm-O6V2F")
                st.caption("ID du dossier contenant les emails")
                
                if st.button("Ouvrir dans Drive", key="open_drive"):
                    st.markdown("[Ouvrir ↗](https://drive.google.com/drive/folders/1YevTmiEAycLE2X0g01juOO-cWm-O6V2F)")
            
            with col2:
                st.write("**📊 Google Sheets:**")
                st.code("1eVoS4Pd6RiL-4PLaZWC5s8Yzax6VbT5D9Tz5K2deMs4")
                st.caption("ID de la feuille de données")
                
                if st.button("Ouvrir dans Sheets", key="open_sheets"):
                    st.markdown("[Ouvrir ↗](https://docs.google.com/spreadsheets/d/1eVoS4Pd6RiL-4PLaZWC5s8Yzax6VbT5D9Tz5K2deMs4)")
        
        with tabs[2]:
            st.subheader("À propos de PIXID Automation")
            
            st.markdown("""
            **Version:** 1.0.0  
            **Auteur:** PIXID Automation Team  
            **License:** MIT  
            
            ### 🚀 Fonctionnalités
            - ✅ Synchronisation automatique Drive → Sheets
            - ✅ Enrichissement de fichiers XML
            - ✅ Dashboard de monitoring en temps réel
            - ✅ Recherche et export de données
            
            ### 📚 Documentation
            - [GitHub Repository](https://github.com/your-repo/pixid-automation)
            - [Guide d'utilisation](https://github.com/your-repo/pixid-automation/wiki)
            - [Signaler un bug](https://github.com/your-repo/pixid-automation/issues)
            
            ### 🛠️ Stack technique
            - Python 3.11
            - Streamlit
            - Google APIs
            - GitHub Actions
            - Plotly
            """)
    
    def _load_monitoring_data(self) -> Optional[Dict]:
        """Charge les données de monitoring"""
        try:
            monitoring_file = Path("monitoring_data.json")
            if monitoring_file.exists():
                with open(monitoring_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Erreur chargement monitoring: {e}")
        return None
    
    def _load_monitoring_history(self) -> Dict:
        """Charge l'historique complet du monitoring"""
        data = self._load_monitoring_data()
        return data if data else {'runs': []}
    
    def _load_sheets_data(self):
        """Charge les données depuis Google Sheets"""
        try:
            with st.spinner("Chargement des données..."):
                if st.session_state.sheets_client is None:
                    credentials = GoogleAuthenticator.get_credentials()
                    st.session_state.sheets_client = GoogleSheetsClient(credentials)
                
                client = st.session_state.sheets_client
                client.open_sheet('1eVoS4Pd6RiL-4PLaZWC5s8Yzax6VbT5D9Tz5K2deMs4')
                
                df = client.get_data()
                st.session_state.sheets_data = df
                st.session_state.last_refresh = datetime.now()
                
                logger.info(f"Données chargées: {len(df)} lignes")
                
        except Exception as e:
            st.error(f"Erreur lors du chargement: {str(e)}")
            logger.error(f"Erreur chargement Sheets: {e}")
    
    def _search_order_data(self, order_id: str) -> Optional[Dict]:
        """Recherche les données d'une commande"""
        if st.session_state.sheets_data is None:
            return None
        
        df = st.session_state.sheets_data
        mask = df['numero_commande'].astype(str) == str(order_id)
        results = df[mask]
        
        if not results.empty:
            return results.iloc[0].to_dict()
        return None
    
    def _export_data(self):
        """Exporte les données (placeholder pour l'instant)"""
        st.info("Fonction d'export en développement")


def main():
    """Point d'entrée principal"""
    app = PIXIDStreamlitApp()
    app.run()


if __name__ == "__main__":
    main()
