"""
STMicroelectronics XML Corrector - Streamlit App
Version sans lxml pour éviter les problèmes d'installation
"""

import streamlit as st
import pandas as pd
import json
import requests
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import io

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

# Cache pour les données
@st.cache_data(ttl=300)  # Cache 5 minutes
def load_commandes_data():
    """Charge les données des commandes depuis GitHub"""
    try:
        response = requests.get(GITHUB_RAW_URL)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Erreur lors du chargement des données: {str(e)}")
        return {"commandes": [], "lastUpdate": None, "metadata": {}}

def extract_order_id_from_xml(xml_content):
    """Extrait l'OrderId du fichier XML"""
    try:
        # Parser le XML
        root = ET.fromstring(xml_content)
        
        # Recherche spécifique dans la structure ReferenceInformation > OrderId > IdValue
        # Méthode 1: Recherche directe avec XPath-like
        for ref_info in root.iter('ReferenceInformation'):
            for order_id in ref_info.iter('OrderId'):
                id_value = order_id.find('IdValue')
                if id_value is not None and id_value.text and id_value.text.strip():
                    return id_value.text.strip()
        
        # Méthode 2: Si la structure n'est pas trouvée, chercher OrderId/IdValue n'importe où
        for order_id in root.iter('OrderId'):
            id_value = order_id.find('IdValue')
            if id_value is not None and id_value.text and id_value.text.strip():
                return id_value.text.strip()
        
        # Méthode 3: Recherche alternative si les balises ont des majuscules différentes
        for elem in root.iter():
            if elem.tag.lower() == 'orderid':
                # Chercher IdValue comme enfant direct
                for child in elem:
                    if child.tag.lower() == 'idvalue' and child.text and child.text.strip():
                        return child.text.strip()
        
        return None
        
    except Exception as e:
        st.error(f"Erreur lors de l'extraction de l'OrderId: {str(e)}")
        return None

def enrich_xml(xml_content, commande_data):
    """Enrichit le XML avec les données de la commande"""
    try:
        # Parser le XML avec ElementTree standard
        root = ET.fromstring(xml_content)
        
        # Créer ou trouver la section STMicroelectronics
        stm_section = root.find('.//STMicroelectronicsData')
        if stm_section is None:
            # Ajouter à la fin du root
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
                # Chercher si l'élément existe déjà
                elem = stm_section.find(xml_tag)
                if elem is None:
                    elem = ET.SubElement(stm_section, xml_tag)
                elem.text = str(commande_data[field_key])
                fields_added += 1
        
        # Ajouter les métadonnées d'enrichissement
        metadata = stm_section.find('EnrichmentMetadata')
        if metadata is None:
            metadata = ET.SubElement(stm_section, 'EnrichmentMetadata')
        
        # Timestamp
        timestamp_elem = metadata.find('Timestamp')
        if timestamp_elem is None:
            timestamp_elem = ET.SubElement(metadata, 'Timestamp')
        timestamp_elem.text = datetime.now().isoformat()
        
        # Source
        source_elem = metadata.find('Source')
        if source_elem is None:
            source_elem = ET.SubElement(metadata, 'Source')
        source_elem.text = 'STMicroelectronics XML Corrector'
        
        # Convertir en string avec formatage
        xml_str = ET.tostring(root, encoding='unicode')
        
        # Formater le XML pour qu'il soit plus lisible
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent='  ')
        
        # Retirer la première ligne (déclaration XML) si elle est dupliquée
        lines = pretty_xml.split('\n')
        if lines[0].startswith('<?xml'):
            lines = lines[1:]
        
        # Retirer les lignes vides
        lines = [line for line in lines if line.strip()]
        
        # Remettre la déclaration XML
        pretty_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + '\n'.join(lines)
        
        return pretty_xml, fields_added
        
    except Exception as e:
        st.error(f"Erreur lors de l'enrichissement: {str(e)}")
        return None, 0

def main():
    # Header avec logo
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🔧 STMicroelectronics XML Corrector")
        st.markdown("**Enrichissez vos fichiers XML avec les données des commandes**")
    with col2:
        # Logo placeholder
        st.markdown("### STMicroelectronics")
    
    # Charger les données
    with st.spinner("Chargement des données depuis GitHub..."):
        data = load_commandes_data()
    
    # Statistiques
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    commandes = data.get('commandes', [])
    
    with col1:
        st.metric("📦 Total commandes", len(commandes))
    with col2:
        if data.get('lastUpdate'):
            try:
                last_update = datetime.fromisoformat(data['lastUpdate'].replace('Z', '+00:00'))
                st.metric("🕐 Dernière MAJ", last_update.strftime('%d/%m %H:%M'))
            except:
                st.metric("🕐 Dernière MAJ", "N/A")
        else:
            st.metric("🕐 Dernière MAJ", "Jamais")
    with col3:
        st.metric("📁 Source", "Google Sheets")
    with col4:
        st.metric("🔄 Sync", "Auto 15min")
    
    st.markdown("---")
    
    # Tabs principaux
    tab1, tab2, tab3 = st.tabs(["📤 Enrichir XML", "📊 Données disponibles", "ℹ️ Guide d'utilisation"])
    
    with tab1:
        st.subheader("Enrichissement de fichier XML")
        
        # Zone d'upload
        uploaded_file = st.file_uploader(
            "Sélectionnez votre fichier XML",
            type=['xml'],
            help="Le fichier doit contenir un OrderId pour permettre la correspondance avec les données"
        )
        
        if uploaded_file is not None:
            # Lire le contenu du fichier
            xml_content = uploaded_file.read()
            
            try:
                xml_content = xml_content.decode('utf-8')
            except:
                try:
                    xml_content = xml_content.decode('latin-1')
                except:
                    st.error("Impossible de décoder le fichier. Assurez-vous qu'il s'agit d'un fichier XML valide.")
                    return
            
            # Extraire l'OrderId
            order_id = extract_order_id_from_xml(xml_content)
            
            # Affichage en colonnes
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.info(f"**📄 Fichier:** {uploaded_file.name}")
                st.info(f"**📏 Taille:** {len(xml_content) / 1024:.1f} KB")
                
                if order_id:
                    st.success(f"**🔍 OrderId détecté:** {order_id}")
                else:
                    st.error("**❌ OrderId:** Non trouvé")
            
            with col2:
                if order_id:
                    # Rechercher dans les données
                    commande_found = None
                    
                    for cmd in commandes:
                        if str(cmd.get('numero_commande', '')).strip() == str(order_id).strip():
                            commande_found = cmd
                            break
                    
                    if commande_found:
                        st.success("✅ **Données trouvées dans la base!**")
                        
                        # Afficher les données trouvées
                        with st.expander("📋 **Voir les données qui seront ajoutées**", expanded=True):
                            # Filtrer les données à afficher
                            display_data = {}
                            field_names = {
                                'code_agence': 'Code Agence',
                                'code_unite': 'Code Unité',
                                'statut': 'Statut',
                                'niveau_convention_collective': 'Niveau Convention Collective',
                                'classification_interimaire': 'Classification Intérimaire',
                                'personne_absente': 'Personne Absente'
                            }
                            
                            for field, display_name in field_names.items():
                                if field in commande_found and commande_found[field]:
                                    display_data[display_name] = commande_found[field]
                            
                            if display_data:
                                for field, value in display_data.items():
                                    st.write(f"**{field}:** {value}")
                            else:
                                st.warning("Aucune donnée supplémentaire disponible pour cette commande")
                        
                        # Bouton pour enrichir
                        if st.button("🚀 **Enrichir le XML**", type="primary", use_container_width=True):
                            with st.spinner("Enrichissement en cours..."):
                                enriched_xml, fields_count = enrich_xml(xml_content, commande_found)
                                
                                if enriched_xml:
                                    st.success(f"✅ **XML enrichi avec succès!** ({fields_count} champs ajoutés)")
                                    
                                    # Prévisualisation
                                    with st.expander("👁️ **Aperçu du XML enrichi**", expanded=False):
                                        st.code(enriched_xml, language='xml')
                                    
                                    # Bouton de téléchargement
                                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                                    filename = f"enriched_{order_id}_{timestamp}.xml"
                                    
                                    st.download_button(
                                        label="📥 **Télécharger le XML enrichi**",
                                        data=enriched_xml,
                                        file_name=filename,
                                        mime="application/xml",
                                        type="primary",
                                        use_container_width=True
                                    )
                                else:
                                    st.error("❌ Erreur lors de l'enrichissement du XML")
                    else:
                        st.warning(f"⚠️ **Aucune donnée trouvée pour la commande {order_id}**")
                        st.info("Cette commande n'a pas encore été synchronisée depuis les emails STMicroelectronics.")
                        st.info("Vérifiez dans l'onglet 'Données disponibles' si la commande existe.")
                else:
                    st.error("❌ **Impossible de détecter l'OrderId dans le fichier XML**")
                    st.info("Assurez-vous que votre fichier contient une balise OrderId, order_id, numero_commande ou similaire.")
    
    with tab2:
        st.subheader("📊 Commandes disponibles")
        
        if commandes:
            # Créer un DataFrame
            df = pd.DataFrame(commandes)
            
            # Barre de recherche
            search_term = st.text_input("🔍 Rechercher une commande", placeholder="Numéro, agence, unité, statut...")
            
            # Filtrer si recherche
            if search_term:
                mask = df.astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)
                df_filtered = df[mask]
            else:
                df_filtered = df
            
            st.write(f"**{len(df_filtered)} commande(s)** sur {len(df)} au total")
            
            # Afficher le tableau
            if not df_filtered.empty:
                # Configurer l'affichage des colonnes
                column_config = {
                    "numero_commande": st.column_config.TextColumn("N° Commande", width="small"),
                    "code_agence": st.column_config.TextColumn("Code Agence", width="small"),
                    "code_unite": st.column_config.TextColumn("Code Unité", width="small"),
                    "statut": st.column_config.TextColumn("Statut", width="medium"),
                    "niveau_convention_collective": st.column_config.TextColumn("Niveau CC", width="medium"),
                    "classification_interimaire": st.column_config.TextColumn("Classification", width="medium"),
                    "personne_absente": st.column_config.TextColumn("Remplace", width="medium"),
                    "date_extraction": st.column_config.TextColumn("Date extraction", width="small")
                }
                
                # Réorganiser les colonnes
                columns_order = ['numero_commande', 'code_agence', 'code_unite', 'statut', 
                               'niveau_convention_collective', 'classification_interimaire', 
                               'personne_absente', 'date_extraction']
                
                # Afficher seulement les colonnes qui existent
                available_columns = [col for col in columns_order if col in df_filtered.columns]
                
                st.dataframe(
                    df_filtered[available_columns],
                    use_container_width=True,
                    hide_index=True,
                    column_config=column_config
                )
            else:
                st.info("Aucune commande trouvée avec ce critère de recherche")
        else:
            st.warning("Aucune donnée disponible")
            st.info("Les données seront disponibles après la première synchronisation du script Google Apps")
    
    with tab3:
        st.subheader("ℹ️ Guide d'utilisation")
        
        st.markdown("""
        ### 📋 Comment enrichir vos fichiers XML ?
        
        **1. 📤 Uploadez votre fichier XML**
        - Le fichier doit contenir un identifiant de commande (OrderId, numero_commande, etc.)
        - Format supporté : .xml
        
        **2. 🔍 Détection automatique**
        - L'application détecte automatiquement l'identifiant de commande
        - Les données correspondantes sont recherchées dans la base
        
        **3. ✨ Enrichissement**
        - Cliquez sur "Enrichir le XML"
        - Les données manquantes sont ajoutées automatiquement
        - Une section `<STMicroelectronicsData>` est créée ou mise à jour
        
        **4. 📥 Téléchargement**
        - Téléchargez le fichier XML enrichi
        - Le fichier original reste intact
        
        ---
        
        ### 📄 Structure ajoutée au XML
        
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
                <Source>STMicroelectronics XML Corrector</Source>
            </EnrichmentMetadata>
        </STMicroelectronicsData>
        ```
        
        ---
        
        ### 🔄 Flux de données
        
        1. **Emails STMicroelectronics** (dans Google Drive)
        2. **Google Apps Script** (extraction toutes les 15 min)
        3. **Google Sheets** (stockage des données)
        4. **GitHub** (fichier JSON)
        5. **Cette application** (enrichissement XML)
        
        ---
        
        ### ❓ Résolution des problèmes
        
        **"OrderId non trouvé"**
        - Vérifiez que votre XML contient une balise avec l'identifiant
        - Balises supportées : OrderId, order_id, numero_commande, Order, etc.
        
        **"Aucune donnée trouvée"**
        - La commande n'est pas encore dans la base
        - Vérifiez dans l'onglet "Données disponibles"
        - Attendez la prochaine synchronisation (15 min)
        
        **"Erreur lors de l'enrichissement"**
        - Vérifiez que le fichier XML est valide
        - Contactez le support si le problème persiste
        
        ---
        
        ### 📞 Support
        
        En cas de problème : [github.com/younessemlali](https://github.com/younessemlali)
        """)

# Lancer l'application
if __name__ == "__main__":
    main()
