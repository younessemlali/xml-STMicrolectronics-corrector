"""
STMicroelectronics XML Corrector - Streamlit App
Enrichit les fichiers XML avec les données des commandes
"""

import streamlit as st
import pandas as pd
import json
import requests
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import io
from pathlib import Path

# Configuration
GITHUB_RAW_URL = "https://raw.githubusercontent.com/younessemlali/xml-STMicrolectronics-corrector/main/data/commandes_stm.json"

# Configuration Streamlit
st.set_page_config(
    page_title="STMicroelectronics XML Corrector",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Style CSS
st.markdown("""
<style>
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        margin: 1rem 0;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        margin: 1rem 0;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# Cache pour les données GitHub
@st.cache_data(ttl=300)  # Cache 5 minutes
def load_commandes_data():
    """Charge les données des commandes depuis GitHub"""
    try:
        response = requests.get(GITHUB_RAW_URL)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Erreur lors du chargement des données: {str(e)}")
        return None

def extract_order_id_from_xml(xml_content):
    """Extrait l'OrderId du fichier XML"""
    try:
        root = ET.fromstring(xml_content)
        
        # Recherche de l'OrderId (différentes variantes possibles)
        for elem in root.iter():
            if elem.tag.lower() in ['orderid', 'order_id', 'numero_commande', 'commande']:
                return elem.text
        
        # Recherche dans les attributs
        for elem in root.iter():
            for attr, value in elem.attrib.items():
                if attr.lower() in ['orderid', 'order_id', 'numero_commande']:
                    return value
        
        return None
    except Exception as e:
        st.error(f"Erreur lors de l'extraction de l'OrderId: {str(e)}")
        return None

def enrich_xml(xml_content, commande_data):
    """Enrichit le XML avec les données de la commande"""
    try:
        root = ET.fromstring(xml_content)
        
        # Créer ou trouver la section STMicroelectronics
        stm_section = root.find('.//STMicroelectronicsData')
        if stm_section is None:
            stm_section = ET.SubElement(root, 'STMicroelectronicsData')
        
        # Mapping des champs
        field_mapping = {
            'code_agence': 'AgencyCode',
            'code_unite': 'UnitCode',
            'statut': 'Status',
            'niveau_convention_collective': 'CollectiveAgreementLevel',
            'classification_interimaire': 'TempWorkerClassification',
            'personne_absente': 'AbsentPerson'
        }
        
        # Ajouter ou mettre à jour les champs
        fields_added = 0
        for field_key, xml_tag in field_mapping.items():
            if field_key in commande_data and commande_data[field_key]:
                elem = stm_section.find(xml_tag)
                if elem is None:
                    elem = ET.SubElement(stm_section, xml_tag)
                elem.text = str(commande_data[field_key])
                fields_added += 1
        
        # Ajouter les métadonnées
        metadata = stm_section.find('EnrichmentMetadata')
        if metadata is None:
            metadata = ET.SubElement(stm_section, 'EnrichmentMetadata')
        
        timestamp_elem = metadata.find('Timestamp')
        if timestamp_elem is None:
            timestamp_elem = ET.SubElement(metadata, 'Timestamp')
        timestamp_elem.text = datetime.now().isoformat()
        
        # Convertir en string avec formatage
        xml_str = ET.tostring(root, encoding='unicode')
        
        # Formater le XML pour qu'il soit plus lisible
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent='  ')
        
        # Retirer les lignes vides
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        pretty_xml = '\n'.join(lines)
        
        return pretty_xml, fields_added
        
    except Exception as e:
        st.error(f"Erreur lors de l'enrichissement: {str(e)}")
        return None, 0

def main():
    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🔧 STMicroelectronics XML Corrector")
        st.markdown("Enrichissez vos fichiers XML avec les données des commandes")
    with col2:
        st.image("https://www.st.com/content/dam/st-logo.png", width=150)
    
    # Charger les données
    with st.spinner("Chargement des données..."):
        data = load_commandes_data()
    
    if data is None:
        st.error("Impossible de charger les données. Vérifiez votre connexion.")
        return
    
    # Statistiques
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📦 Total commandes", len(data.get('commandes', [])))
    with col2:
        if data.get('lastUpdate'):
            last_update = datetime.fromisoformat(data['lastUpdate'].replace('Z', '+00:00'))
            st.metric("🕐 Dernière MAJ", last_update.strftime('%d/%m %H:%M'))
    with col3:
        st.metric("📁 Source", "Google Sheets")
    with col4:
        st.metric("🔄 Sync", "Auto 15min")
    
    st.markdown("---")
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["📤 Enrichir XML", "📊 Données disponibles", "ℹ️ Guide"])
    
    with tab1:
        st.subheader("Enrichissement de fichier XML")
        
        # Upload
        uploaded_file = st.file_uploader(
            "Sélectionnez votre fichier XML",
            type=['xml'],
            help="Le fichier doit contenir un OrderId pour la correspondance"
        )
        
        if uploaded_file is not None:
            # Lire le contenu
            xml_content = uploaded_file.read().decode('utf-8')
            
            # Extraire l'OrderId
            order_id = extract_order_id_from_xml(xml_content)
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.info(f"**Fichier:** {uploaded_file.name}")
                st.info(f"**Taille:** {len(xml_content) / 1024:.1f} KB")
                
                if order_id:
                    st.success(f"**OrderId détecté:** {order_id}")
                else:
                    st.error("**OrderId:** Non trouvé")
            
            with col2:
                if order_id:
                    # Rechercher dans les données
                    commandes = data.get('commandes', [])
                    commande_found = None
                    
                    for cmd in commandes:
                        if str(cmd.get('numero_commande')) == str(order_id):
                            commande_found = cmd
                            break
                    
                    if commande_found:
                        st.success("✅ Données trouvées!")
                        
                        # Afficher les données
                        with st.expander("📋 Voir les données", expanded=True):
                            # Retirer les champs null/None
                            display_data = {k: v for k, v in commande_found.items() 
                                          if v is not None and k != 'numero_commande'}
                            
                            for field, value in display_data.items():
                                st.write(f"**{field.replace('_', ' ').title()}:** {value}")
                        
                        # Bouton enrichir
                        if st.button("🚀 Enrichir le XML", type="primary", use_container_width=True):
                            enriched_xml, fields_count = enrich_xml(xml_content, commande_found)
                            
                            if enriched_xml:
                                st.success(f"✅ XML enrichi avec {fields_count} champs!")
                                
                                # Preview
                                with st.expander("👁️ Aperçu du XML enrichi"):
                                    st.code(enriched_xml, language='xml')
                                
                                # Download
                                st.download_button(
                                    label="📥 Télécharger le XML enrichi",
                                    data=enriched_xml,
                                    file_name=f"enriched_{order_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml",
                                    mime="application/xml",
                                    type="primary",
                                    use_container_width=True
                                )
                    else:
                        st.warning(f"⚠️ Aucune donnée trouvée pour la commande {order_id}")
                        st.info("Cette commande n'a pas encore été synchronisée depuis Google Sheets")
                else:
                    st.error("Impossible de détecter l'OrderId dans le fichier XML")
                    st.info("Assurez-vous que votre fichier contient une balise OrderId, order_id, ou numero_commande")
    
    with tab2:
        st.subheader("📊 Commandes disponibles")
        
        if data and 'commandes' in data:
            df = pd.DataFrame(data['commandes'])
            
            # Recherche
            search = st.text_input("🔍 Rechercher une commande", placeholder="Numéro, agence, unité...")
            
            if search:
                mask = df.astype(str).apply(lambda x: x.str.contains(search, case=False, na=False)).any(axis=1)
                df = df[mask]
            
            st.write(f"**{len(df)} commandes** affichées")
            
            # Afficher le dataframe
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "numero_commande": st.column_config.TextColumn("N° Commande", width="small"),
                    "code_agence": st.column_config.TextColumn("Agence", width="small"),
                    "code_unite": st.column_config.TextColumn("Unité", width="small"),
                    "statut": st.column_config.TextColumn("Statut"),
                    "date_extraction": st.column_config.DatetimeColumn("Date", format="DD/MM HH:mm")
                }
            )
    
    with tab3:
        st.subheader("ℹ️ Guide d'utilisation")
        
        st.markdown("""
        ### Comment enrichir vos fichiers XML ?
        
        1. **📤 Uploadez votre fichier XML**
           - Le fichier doit contenir un identifiant de commande (OrderId)
           - Formats supportés : .xml
        
        2. **🔍 Détection automatique**
           - L'application détecte automatiquement l'OrderId
           - Les données correspondantes sont recherchées
        
        3. **✨ Enrichissement**
           - Cliquez sur "Enrichir le XML"
           - Les champs manquants sont ajoutés automatiquement
        
        4. **📥 Téléchargement**
           - Téléchargez le fichier XML enrichi
           - Le fichier original n'est pas modifié
        
        ### Structure ajoutée au XML :
        ```xml
        <STMicroelectronicsData>
            <AgencyCode>AG-75-001</AgencyCode>
            <UnitCode>UN-123</UnitCode>
            <Status>Confirmée</Status>
            <CollectiveAgreementLevel>Niveau IV</CollectiveAgreementLevel>
            <TempWorkerClassification>Technicien</TempWorkerClassification>
            <AbsentPerson>Marie DUPONT</AbsentPerson>
            <EnrichmentMetadata>
                <Timestamp>2024-01-15T10:30:00</Timestamp>
            </EnrichmentMetadata>
        </STMicroelectronicsData>
        ```
        
        ### 🔄 Synchronisation des données
        - Les données sont mises à jour automatiquement toutes les 15 minutes
        - Source : Emails STMicroelectronics → Google Sheets → GitHub → Cette application
        
        ### ❓ Support
        - En cas de problème, vérifiez que votre commande existe dans l'onglet "Données disponibles"
        - Contact : [younessemlali](https://github.com/younessemlali)
        """)

if __name__ == "__main__":
    main()
