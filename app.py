import streamlit as st
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import tempfile
from datetime import datetime
from xml_enricher import XMLEnricher
import pandas as pd
import io

# Configuration de la page
st.set_page_config(
    page_title="PIXID XML Enricher",
    page_icon="🔧",
    layout="wide"
)

# CSS personnalisé
st.markdown("""
<style>
    .success-box {
        padding: 20px;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        margin: 10px 0;
    }
    .info-box {
        padding: 15px;
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        border-radius: 5px;
        margin: 10px 0;
    }
    .warning-box {
        padding: 15px;
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        border-radius: 5px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Titre principal
st.title("🔧 PIXID XML Enricher - STMicroelectronics")
st.markdown("Enrichissez automatiquement vos fichiers XML avec les données PIXID extraites des emails")

# Initialisation de la session
if 'enriched_xml' not in st.session_state:
    st.session_state.enriched_xml = None
if 'stats' not in st.session_state:
    st.session_state.stats = None

# Sidebar - Navigation
st.sidebar.title("📋 Navigation")
page = st.sidebar.radio(
    "Choisir une page",
    ["🔧 Enrichissement XML", "🔍 Recherche commande", "📊 Statistiques", "ℹ️ Documentation"]
)

# Charger automatiquement le fichier JSON des commandes
st.sidebar.markdown("---")
st.sidebar.subheader("📁 Base de données")

# Initialiser l'enrichisseur automatiquement au démarrage
if 'enricher' not in st.session_state:
    try:
        # Essayer d'abord data/commandes_stm.json
        json_path = 'data/commandes_stm.json'
        if not Path(json_path).exists():
            # Sinon chercher à la racine
            json_path = 'commandes_stm.json'
        
        st.session_state.enricher = XMLEnricher(json_path)
        st.sidebar.success(f"✅ {len(st.session_state.enricher.commandes_data)} commandes chargées")
    except FileNotFoundError:
        st.session_state.enricher = None
        st.sidebar.error("❌ Fichier commandes_stm.json introuvable")
        st.sidebar.info("💡 Placez commandes_stm.json dans /data/ ou à la racine")
    except Exception as e:
        st.session_state.enricher = None
        st.sidebar.error(f"❌ Erreur: {e}")
else:
    # L'enrichisseur est déjà chargé
    if st.session_state.enricher:
        st.sidebar.info(f"✅ {len(st.session_state.enricher.commandes_data)} commandes disponibles")

# ============= PAGE 1: ENRICHISSEMENT XML =============
if page == "🔧 Enrichissement XML":
    st.header("🔧 Enrichissement XML Multi-Contrats")
    
    if not st.session_state.enricher:
        st.error("⚠️ Base de données non disponible")
        st.info("""
        **Fichier manquant: commandes_stm.json**
        
        Ce fichier est généré automatiquement par le système Google Apps Script.
        Placez-le dans le dossier `/data/` ou à la racine du projet.
        """)
        st.stop()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📤 Upload du fichier XML")
        xml_file = st.file_uploader(
            "Sélectionnez votre fichier XML contenant un ou plusieurs contrats",
            type=['xml'],
            help="Le fichier XML peut contenir plusieurs contrats. Chaque contrat avec un OrderId valide sera enrichi."
        )
    
    with col2:
        st.subheader("📊 Informations")
        total_commandes = len(st.session_state.enricher.commandes_data)
        st.metric("Commandes disponibles", total_commandes)
    
    if xml_file:
        # Sauvegarder temporairement le XML
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xml', mode='wb') as tmp_xml:
            tmp_xml.write(xml_file.getvalue())
            tmp_xml_path = tmp_xml.name
        
        # Afficher un aperçu
        st.subheader("🔍 Analyse du fichier XML")
        
        # Trouver tous les numéros de commande
        orders = st.session_state.enricher.find_all_order_ids_in_xml(tmp_xml_path)
        
        if orders:
            st.success(f"✅ **{len(orders)} contrat(s) détecté(s)** dans le fichier XML")
            
            # Afficher les contrats détectés
            with st.expander("📋 Liste des contrats détectés", expanded=True):
                orders_with_data = []
                orders_without_data = []
                
                for order_info in orders:
                    order_id = order_info['order_id']
                    commande = st.session_state.enricher.get_commande_info(order_id)
                    
                    if commande:
                        orders_with_data.append({
                            'OrderId': order_id,
                            'Agence': commande.get('code_agence', 'N/A'),
                            'Unité': commande.get('code_unite', 'N/A'),
                            'Statut': commande.get('statut', 'N/A'),
                            'Classification': commande.get('classification_interimaire', 'N/A'),
                            'Données': '✅ Disponibles'
                        })
                    else:
                        orders_without_data.append({
                            'OrderId': order_id,
                            'Agence': '-',
                            'Unité': '-',
                            'Statut': '-',
                            'Classification': '-',
                            'Données': '❌ Non trouvées'
                        })
                
                # Afficher les résultats
                col1, col2 = st.columns(2)
                
                with col1:
                    st.metric("✅ Contrats enrichissables", len(orders_with_data))
                
                with col2:
                    st.metric("❌ Contrats sans données", len(orders_without_data))
                
                # Tableau récapitulatif
                all_orders = orders_with_data + orders_without_data
                if all_orders:
                    df = pd.DataFrame(all_orders)
                    st.dataframe(df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # Bouton d'enrichissement
            if len(orders_with_data) > 0:
                if st.button("🚀 Enrichir le fichier XML", type="primary", use_container_width=True):
                    # Créer un placeholder pour la progression
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Créer le fichier de sortie
                    output_path = tempfile.NamedTemporaryFile(delete=False, suffix='_enrichi.xml').name
                    
                    # Fonction callback pour la progression
                    def update_progress(current, total):
                        progress = current / total
                        progress_bar.progress(progress)
                        status_text.text(f"Enrichissement: {current}/{total} contrats traités...")
                    
                    # Enrichir
                    success, message, stats = st.session_state.enricher.enrich_xml(
                        tmp_xml_path,
                        output_path,
                        progress_callback=update_progress
                    )
                    
                    # Nettoyer la barre de progression
                    progress_bar.empty()
                    status_text.empty()
                    
                    if success:
                        # Lire le fichier enrichi
                        with open(output_path, 'rb') as f:
                            st.session_state.enriched_xml = f.read()
                        
                        st.session_state.stats = stats
                        
                        st.balloons()
                        st.success("✅ Fichier XML enrichi avec succès!")
                        
                        # Afficher les statistiques
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("📦 Total contrats", stats['total'])
                        
                        with col2:
                            st.metric("✅ Enrichis", stats['enrichis'], 
                                    delta=f"{(stats['enrichis']/stats['total']*100):.0f}%")
                        
                        with col3:
                            st.metric("❌ Non trouvés", stats['non_trouves'])
                        
                        # Détails des modifications
                        with st.expander("📋 Détails des modifications par contrat"):
                            details_df = pd.DataFrame(stats['details'])
                            st.dataframe(details_df, use_container_width=True, hide_index=True)
                    else:
                        st.error(f"❌ {message}")
            else:
                st.warning("⚠️ Aucun contrat ne peut être enrichi (aucune donnée disponible)")
            
            # Téléchargement si enrichissement effectué
            if st.session_state.enriched_xml and st.session_state.stats:
                st.markdown("---")
                st.subheader("📥 Télécharger les résultats")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Générer le nom du fichier
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    xml_name = f"enrichi_{st.session_state.stats['enrichis']}contrats_{timestamp}.xml"
                    
                    st.download_button(
                        label="⬇️ Télécharger le XML enrichi",
                        data=st.session_state.enriched_xml,
                        file_name=xml_name,
                        mime="application/xml",
                        use_container_width=True
                    )
                
                with col2:
                    # Créer un rapport CSV
                    if st.session_state.stats and 'details' in st.session_state.stats:
                        csv_buffer = io.StringIO()
                        df_report = pd.DataFrame(st.session_state.stats['details'])
                        df_report.to_csv(csv_buffer, index=False)
                        csv_data = csv_buffer.getvalue()
                        
                        csv_name = f"rapport_{timestamp}.csv"
                        
                        st.download_button(
                            label="📊 Télécharger le rapport CSV",
                            data=csv_data,
                            file_name=csv_name,
                            mime="text/csv",
                            use_container_width=True
                        )
        else:
            st.error("❌ Aucun numéro de commande détecté dans le XML")
            st.info("""
            Le numéro de commande doit être au format:
            - CR000xxx (Crolles)
            - CD000xxx (Crolles Direct)
            - RT000xxx (Rousset)
            """)

# ============= PAGE 2: RECHERCHE =============
elif page == "🔍 Recherche commande":
    st.header("🔍 Recherche de commande")
    
    if not st.session_state.enricher:
        st.warning("⚠️ Base de données non disponible")
        st.stop()
    
    # Champ de recherche
    query = st.text_input(
        "🔎 Rechercher une commande",
        placeholder="Numéro de commande, code agence, code unité...",
        help="Ex: CR000722, STC, CR8043..."
    )
    
    if query:
        results = st.session_state.enricher.search_commandes(query)
        
        st.subheader(f"📊 Résultats ({len(results)} trouvé{'s' if len(results) > 1 else ''})")
        
        if results:
            for i, cmd in enumerate(results[:20], 1):  # Limiter à 20 résultats
                with st.expander(f"📋 {cmd['numero_commande']} - {cmd.get('personne_absente', 'N/A')[:50]}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown(f"**🏢 Agence:** {cmd.get('code_agence', 'N/A')}")
                        st.markdown(f"**🔧 Unité:** {cmd.get('code_unite', 'N/A')}")
                        st.markdown(f"**👔 Statut:** {cmd.get('statut', 'N/A')}")
                    
                    with col2:
                        st.markdown(f"**🎯 Classification:** {cmd.get('classification_interimaire', 'N/A')}")
                        st.markdown(f"**👤 Personne:** {cmd.get('personne_absente', 'N/A')[:100]}")
                        
                        date_str = cmd.get('date_extraction', 'N/A')
                        if date_str != 'N/A':
                            try:
                                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                st.markdown(f"**📅 Date:** {date_obj.strftime('%d/%m/%Y %H:%M')}")
                            except:
                                st.markdown(f"**📅 Date:** {date_str}")
            
            if len(results) > 20:
                st.info(f"💡 {len(results) - 20} résultats supplémentaires non affichés")
        else:
            st.info("Aucun résultat trouvé")

# ============= PAGE 3: STATISTIQUES =============
elif page == "📊 Statistiques":
    st.header("📊 Statistiques des commandes")
    
    if not st.session_state.enricher:
        st.warning("⚠️ Base de données non disponible")
        st.stop()
    
    commandes = list(st.session_state.enricher.commandes_data.values())
    
    # Métriques globales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total commandes", len(commandes))
    
    with col2:
        agences = set(c.get('code_agence') for c in commandes if c.get('code_agence'))
        st.metric("Agences", len(agences))
    
    with col3:
        unites = set(c.get('code_unite') for c in commandes if c.get('code_unite'))
        st.metric("Unités", len(unites))
    
    with col4:
        statuts = set(c.get('statut') for c in commandes if c.get('statut'))
        st.metric("Statuts", len(statuts))
    
    st.markdown("---")
    
    # Statistiques par type
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Répartition par agence")
        agence_count = {}
        for cmd in commandes:
            agence = cmd.get('code_agence', 'N/A')
            agence_count[agence] = agence_count.get(agence, 0) + 1
        
        for agence, count in sorted(agence_count.items(), key=lambda x: -x[1])[:10]:
            st.metric(agence, count)
    
    with col2:
        st.subheader("📊 Répartition par statut")
        statut_count = {}
        for cmd in commandes:
            statut = cmd.get('statut', 'N/A')
            statut_short = statut.split('-')[0].strip() if statut and '-' in statut else statut
            statut_count[statut_short] = statut_count.get(statut_short, 0) + 1
        
        for statut, count in sorted(statut_count.items(), key=lambda x: -x[1])[:10]:
            st.metric(statut, count)

# ============= PAGE 4: DOCUMENTATION =============
elif page == "ℹ️ Documentation":
    st.header("ℹ️ Documentation")
    
    st.markdown("""
    ## 🎯 Objectif
    
    Cette application permet d'enrichir automatiquement vos fichiers XML (pouvant contenir plusieurs contrats)
    avec les données extraites des emails de confirmation de commande PIXID de STMicroelectronics.
    
    ## 🔧 Fonctionnement
    
    ### 1. Chargement des données
    - Le fichier `commandes_stm.json` est chargé automatiquement au démarrage
    - Ce fichier contient toutes les commandes extraites des emails
    
    ### 2. Enrichissement XML Multi-Contrats
    - Uploadez votre fichier XML (peut contenir plusieurs contrats)
    - L'application détecte **TOUS** les numéros de commande dans le fichier
    - Pour chaque contrat trouvé dans la base, les balises suivantes sont enrichies:
      - `<Code>` dans `<PositionStatus>` → Statut (ex: "OP", "VAC")
      - `<PositionCoefficient>` → Classification (ex: "A2", "B1")
    - Les contrats non trouvés dans la base restent inchangés
    
    ### 3. Suivi et Rapport
    - **Barre de progression** pendant le traitement
    - **Statistiques détaillées** : nombre total, enrichis, non trouvés
    - **Rapport CSV téléchargeable** avec le détail de chaque contrat
    
    ### 4. Téléchargement
    - Téléchargez votre fichier XML enrichi (tous les contrats dans un seul fichier)
    - Téléchargez le rapport CSV pour audit/suivi
    - Le nom inclut le nombre de contrats enrichis et un timestamp
    
    ## 📋 Structure des données
    
    ### Balises enrichies
    
    ```xml
    <PositionCharacteristics>
      <PositionTitle>Agent de fabrication (F/H)</PositionTitle>
      <PositionStatus>
        <Code>OP</Code>                    <!-- ✅ ENRICHI -->
        <Description>Opérateur</Description>
      </PositionStatus>
      <PositionLevel>Direct</PositionLevel>
      <PositionCoefficient>A2</PositionCoefficient>  <!-- ✅ ENRICHI -->
    </PositionCharacteristics>
    ```
    
    ### Formats de numéro de commande supportés
    - **CR000xxx**: Commandes Crolles
    - **CD000xxx**: Commandes Crolles Direct  
    - **RT000xxx**: Commandes Rousset
    
    ## ⚠️ Important
    
    - Le fichier `commandes_stm.json` doit être à jour
    - L'encodage **ISO-8859-1** est préservé
    - **Aucun namespace** n'est ajouté (pas de ns0:)
    - Les contrats sans données restent intacts
    - Vérifiez toujours le rapport CSV après enrichissement
    
    ## 🆘 Support
    
    En cas de problème:
    1. Vérifiez que le fichier JSON est bien chargé
    2. Vérifiez que les numéros de commande sont présents dans le XML
    3. Consultez le rapport CSV pour voir quels contrats ont été enrichis
    4. Les fichiers XML de grande taille (15 000+ lignes) sont supportés
    
    ## 📞 Contact
    
    Pour toute question ou support technique, contactez l'équipe PIXID Automation.
    """)

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("**PIXID Automation Platform**")
st.sidebar.caption("v2.1 - Multi-Contrats - STMicroelectronics")
