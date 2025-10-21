import streamlit as st
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import tempfile
from datetime import datetime
from xml_enricher import XMLEnricher
import os

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
        # Charger directement depuis le fichier
        st.session_state.enricher = XMLEnricher('commandes_stm.json')
        st.sidebar.success(f"✅ {len(st.session_state.enricher.commandes_data)} commandes chargées")
    except FileNotFoundError:
        st.session_state.enricher = None
        st.sidebar.error("❌ Fichier commandes_stm.json introuvable dans le repo")
    except Exception as e:
        st.session_state.enricher = None
        st.sidebar.error(f"❌ Erreur: {e}")
else:
    # L'enrichisseur est déjà chargé
    if st.session_state.enricher:
        st.sidebar.info(f"✅ {len(st.session_state.enricher.commandes_data)} commandes disponibles")

# ============= PAGE 1: ENRICHISSEMENT XML =============
if page == "🔧 Enrichissement XML":
    st.header("🔧 Enrichissement XML")
    
    if not st.session_state.enricher:
        st.warning("⚠️ Veuillez d'abord charger le fichier commandes_stm.json dans la barre latérale")
        st.info("""
        **Comment obtenir le fichier commandes_stm.json ?**
        
        Ce fichier est généré automatiquement par le système Google Apps Script qui analyse
        les emails PIXID et extrait les données. Il contient toutes les commandes avec leur
        statut et classification.
        """)
        st.stop()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📤 Upload du fichier XML")
        xml_file = st.file_uploader(
            "Sélectionnez votre fichier XML à enrichir",
            type=['xml'],
            help="Le fichier XML doit contenir un numéro de commande (CR, CD ou RT)"
        )
    
    with col2:
        st.subheader("📊 Informations")
        if st.session_state.enricher:
            total_commandes = len(st.session_state.enricher.commandes_data)
            st.metric("Commandes disponibles", total_commandes)
    
    if xml_file:
        # Sauvegarder temporairement le XML
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xml', mode='wb') as tmp_xml:
            tmp_xml.write(xml_file.getvalue())
            tmp_xml_path = tmp_xml.name
        
        # Afficher un aperçu
        st.subheader("🔍 Analyse du fichier XML")
        
        # Trouver le numéro de commande
        order_id = st.session_state.enricher.find_order_id_in_xml(tmp_xml_path)
        
        if order_id:
            st.success(f"✅ Numéro de commande détecté: **{order_id}**")
            
            # Récupérer les données de la commande
            commande = st.session_state.enricher.get_commande_info(order_id)
            
            if commande:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown("**🏢 Agence**")
                    st.info(commande.get('code_agence', 'N/A'))
                
                with col2:
                    st.markdown("**🔧 Unité**")
                    st.info(commande.get('code_unite', 'N/A'))
                
                with col3:
                    st.markdown("**📅 Date extraction**")
                    date_str = commande.get('date_extraction', 'N/A')
                    if date_str != 'N/A':
                        try:
                            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            st.info(date_obj.strftime('%d/%m/%Y %H:%M'))
                        except:
                            st.info(date_str)
                    else:
                        st.info(date_str)
                
                st.markdown("---")
                
                # Afficher les données qui seront enrichies
                st.subheader("📝 Données d'enrichissement")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**👔 Statut**")
                    statut = commande.get('statut', 'Non disponible')
                    if statut and statut != 'Non disponible':
                        code_statut = statut.split('-')[0].strip() if '-' in statut else statut
                        st.success(f"Code: `{code_statut}`")
                        st.caption(f"Description complète: {statut}")
                    else:
                        st.warning("⚠️ Statut non disponible")
                
                with col2:
                    st.markdown("**🎯 Classification**")
                    classification = commande.get('classification_interimaire', 'Non disponible')
                    if classification and classification != 'Non disponible':
                        st.success(f"Coefficient: `{classification}`")
                    else:
                        st.warning("⚠️ Classification non disponible")
                
                st.markdown("---")
                
                # Bouton d'enrichissement
                if st.button("🚀 Enrichir le fichier XML", type="primary", use_container_width=True):
                    with st.spinner("Enrichissement en cours..."):
                        # Créer le fichier de sortie
                        output_path = tempfile.NamedTemporaryFile(delete=False, suffix='_enrichi.xml').name
                        
                        # Enrichir
                        success, message = st.session_state.enricher.enrich_xml(
                            tmp_xml_path,
                            output_path
                        )
                        
                        if success:
                            # Lire le fichier enrichi
                            with open(output_path, 'rb') as f:
                                st.session_state.enriched_xml = f.read()
                            
                            st.balloons()
                            st.success("✅ Fichier XML enrichi avec succès!")
                            
                            # Afficher les modifications
                            with st.expander("📋 Détails des modifications"):
                                st.text(message)
                            
                        else:
                            st.error(f"❌ {message}")
                
                # Téléchargement si enrichissement effectué
                if st.session_state.enriched_xml:
                    st.markdown("---")
                    st.subheader("📥 Télécharger le fichier enrichi")
                    
                    # Générer le nom du fichier
                    original_name = xml_file.name
                    base_name = Path(original_name).stem
                    new_name = f"{base_name}_enrichi_{order_id}.xml"
                    
                    st.download_button(
                        label="⬇️ Télécharger le XML enrichi",
                        data=st.session_state.enriched_xml,
                        file_name=new_name,
                        mime="application/xml",
                        use_container_width=True
                    )
            else:
                st.error(f"❌ Commande {order_id} introuvable dans la base de données")
                st.info("💡 Vérifiez que le fichier commandes_stm.json est à jour")
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
        st.warning("⚠️ Veuillez d'abord charger le fichier commandes_stm.json dans la barre latérale")
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
        st.warning("⚠️ Veuillez d'abord charger le fichier commandes_stm.json dans la barre latérale")
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
    
    Cette application permet d'enrichir automatiquement vos fichiers XML avec les données extraites
    des emails de confirmation de commande PIXID de STMicroelectronics.
    
    ## 🔧 Fonctionnement
    
    ### 1. Chargement des données
    - Uploadez le fichier `commandes_stm.json` dans la barre latérale
    - Ce fichier contient toutes les commandes extraites des emails
    
    ### 2. Enrichissement XML
    - Uploadez votre fichier XML à enrichir
    - L'application détecte automatiquement le numéro de commande
    - Les balises suivantes sont enrichies:
      - `<Code>` dans `<PositionStatus>` → Statut (ex: "OP", "VAC")
      - `<PositionCoefficient>` → Classification (ex: "A2", "B1")
    
    ### 3. Téléchargement
    - Téléchargez votre fichier XML enrichi
    - Le nom inclut le numéro de commande pour faciliter l'identification
    
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
    - Le numéro de commande doit exister dans la base de données
    - Vérifiez toujours le fichier enrichi avant utilisation
    
    ## 🆘 Support
    
    En cas de problème:
    1. Vérifiez que le fichier JSON est bien chargé
    2. Vérifiez que le numéro de commande est présent dans le XML
    3. Vérifiez que la commande existe dans la base de données
    
    ## 📞 Contact
    
    Pour toute question ou support technique, contactez l'équipe PIXID Automation.
    """)

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("**PIXID Automation Platform**")
st.sidebar.caption("v2.0 - STMicroelectronics")
