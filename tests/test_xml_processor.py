"""
Tests unitaires pour le module xml_processor
"""

import pytest
from pathlib import Path
import tempfile
from datetime import datetime
import sys
import os
import xml.etree.ElementTree as ET
from lxml import etree

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.xml_processor import XMLProcessor
from src import XML_FIELD_MAPPING


class TestXMLProcessor:
    """Tests pour la classe XMLProcessor"""
    
    @pytest.fixture
    def processor(self):
        """Fixture pour créer une instance du processeur"""
        return XMLProcessor()
    
    @pytest.fixture
    def sample_xml(self):
        """XML simple pour les tests"""
        return """<?xml version="1.0" encoding="UTF-8"?>
<PixidOrder>
    <OrderId>12345</OrderId>
    <CreationDate>2024-01-15</CreationDate>
    <Customer>
        <Name>Entreprise Test</Name>
        <Contact>contact@entreprise.com</Contact>
    </Customer>
</PixidOrder>"""
    
    @pytest.fixture
    def sample_xml_with_namespace(self):
        """XML avec namespace pour les tests"""
        return """<?xml version="1.0" encoding="UTF-8"?>
<ns:PixidOrder xmlns:ns="http://pixid.fr/schema">
    <ns:OrderId>67890</ns:OrderId>
    <ns:Status>Active</ns:Status>
</ns:PixidOrder>"""
    
    @pytest.fixture
    def enrichment_data(self):
        """Données d'enrichissement pour les tests"""
        return {
            'numero_commande': '12345',
            'code_agence': 'AG-75-001',
            'code_unite': 'UN-92-100',
            'statut': 'Confirmée',
            'niveau_convention_collective': 'Niveau IV - Technicien',
            'classification_interimaire': 'Technicien spécialisé',
            'personne_absente': 'Marie DUPONT'
        }
    
    def test_initialization(self, processor):
        """Test l'initialisation du processeur"""
        assert processor is not None
        assert hasattr(processor, 'field_mapping')
        assert processor.field_mapping == XML_FIELD_MAPPING
    
    def test_parse_xml_string(self, processor, sample_xml):
        """Test le parsing d'une string XML"""
        result = processor.parse_xml(sample_xml)
        
        assert result is not None
        assert 'PixidOrder' in result
        assert result['PixidOrder']['OrderId'] == '12345'
        assert result['PixidOrder']['Customer']['Name'] == 'Entreprise Test'
    
    def test_parse_xml_bytes(self, processor, sample_xml):
        """Test le parsing de bytes XML"""
        xml_bytes = sample_xml.encode('utf-8')
        result = processor.parse_xml(xml_bytes)
        
        assert result is not None
        assert 'PixidOrder' in result
        assert result['PixidOrder']['OrderId'] == '12345'
    
    def test_parse_xml_file(self, processor, sample_xml):
        """Test le parsing depuis un fichier"""
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as tmp:
            tmp.write(sample_xml.encode('utf-8'))
            tmp_path = Path(tmp.name)
        
        try:
            result = processor.parse_xml(tmp_path)
            assert result is not None
            assert 'PixidOrder' in result
        finally:
            tmp_path.unlink()
    
    def test_extract_order_id_simple(self, processor, sample_xml):
        """Test l'extraction simple de l'OrderId"""
        order_id = processor.extract_order_id(sample_xml)
        assert order_id == '12345'
    
    def test_extract_order_id_with_namespace(self, processor, sample_xml_with_namespace):
        """Test l'extraction de l'OrderId avec namespace"""
        order_id = processor.extract_order_id(sample_xml_with_namespace)
        assert order_id == '67890'
    
    def test_extract_order_id_case_variations(self, processor):
        """Test l'extraction avec différentes casses"""
        variations = [
            '<orderid>11111</orderid>',
            '<OrderID>22222</OrderID>',
            '<order_id>33333</order_id>',
            '<ORDERID>44444</ORDERID>'
        ]
        
        for var in variations:
            xml = f'<?xml version="1.0"?><root>{var}</root>'
            order_id = processor.extract_order_id(xml)
            assert order_id is not None
            assert order_id.isdigit()
    
    def test_extract_order_id_from_attribute(self, processor):
        """Test l'extraction depuis un attribut"""
        xml = """<?xml version="1.0"?>
        <Order orderid="99999">
            <Data>Test</Data>
        </Order>"""
        
        order_id = processor.extract_order_id(xml)
        assert order_id == '99999'
    
    def test_extract_order_id_not_found(self, processor):
        """Test quand l'OrderId n'est pas trouvé"""
        xml = """<?xml version="1.0"?>
        <Order>
            <Reference>12345</Reference>
            <Status>Active</Status>
        </Order>"""
        
        order_id = processor.extract_order_id(xml)
        assert order_id is None
    
    def test_enrich_xml_new_section(self, processor, sample_xml, enrichment_data):
        """Test l'enrichissement avec création de nouvelle section"""
        enriched = processor.enrich_xml(sample_xml, enrichment_data)
        
        assert enriched is not None
        
        # Parser le résultat pour vérifier
        root = etree.fromstring(enriched)
        pixid_section = root.find('.//PIXIDEnrichment')
        
        assert pixid_section is not None
        assert pixid_section.find('AgencyCode').text == 'AG-75-001'
        assert pixid_section.find('UnitCode').text == 'UN-92-100'
        assert pixid_section.find('Status').text == 'Confirmée'
        assert pixid_section.find('CollectiveAgreementLevel').text == 'Niveau IV - Technicien'
        
        # Vérifier les métadonnées
        metadata = pixid_section.find('EnrichmentMetadata')
        assert metadata is not None
        assert metadata.find('Timestamp') is not None
        assert metadata.find('FieldsEnriched').text == '6'  # 6 champs enrichis
        assert metadata.find('Source').text == 'PIXID Google Sheets Sync'
    
    def test_enrich_xml_existing_section(self, processor, enrichment_data):
        """Test l'enrichissement avec section existante"""
        xml_with_section = """<?xml version="1.0"?>
        <Order>
            <OrderId>12345</OrderId>
            <PIXIDEnrichment>
                <AgencyCode>OLD-CODE</AgencyCode>
                <ExistingField>Keep this</ExistingField>
            </PIXIDEnrichment>
        </Order>"""
        
        enriched = processor.enrich_xml(xml_with_section, enrichment_data)
        root = etree.fromstring(enriched)
        pixid_section = root.find('.//PIXIDEnrichment')
        
        # Vérifier que les valeurs sont mises à jour
        assert pixid_section.find('AgencyCode').text == 'AG-75-001'
        # Vérifier que les champs existants sont préservés
        assert pixid_section.find('ExistingField').text == 'Keep this'
    
    def test_enrich_xml_skip_empty_values(self, processor, sample_xml):
        """Test que les valeurs vides ne sont pas ajoutées"""
        data = {
            'code_agence': 'AG-001',
            'code_unite': None,
            'statut': '',
            'niveau_convention_collective': 'nan',
            'classification_interimaire': 'None',
            'personne_absente': 'Jean MARTIN'
        }
        
        enriched = processor.enrich_xml(sample_xml, data)
        root = etree.fromstring(enriched)
        pixid_section = root.find('.//PIXIDEnrichment')
        
        # Seuls les champs valides doivent être présents
        assert pixid_section.find('AgencyCode').text == 'AG-001'
        assert pixid_section.find('AbsentPerson').text == 'Jean MARTIN'
        assert pixid_section.find('UnitCode') is None
        assert pixid_section.find('Status') is None
        
        # Vérifier le compte dans les métadonnées
        metadata = pixid_section.find('EnrichmentMetadata')
        assert metadata.find('FieldsEnriched').text == '2'
    
    def test_validate_xml_valid(self, processor, sample_xml):
        """Test la validation d'un XML valide"""
        validation = processor.validate_xml(sample_xml)
        
        assert validation['valid'] is True
        assert validation['has_order_id'] is True
        assert validation['order_id'] == '12345'
        assert validation['has_pixid_section'] is False
        assert len(validation['errors']) == 0
    
    def test_validate_xml_invalid(self, processor):
        """Test la validation d'un XML invalide"""
        invalid_xml = """<?xml version="1.0"?>
        <Order>
            <OrderId>12345</OrderId>
            <Unclosed>
        </Order>"""
        
        validation = processor.validate_xml(invalid_xml)
        
        assert validation['valid'] is False
        assert len(validation['errors']) > 0
        assert 'Erreur de syntaxe XML' in validation['errors'][0]
    
    def test_validate_enriched_xml(self, processor, sample_xml, enrichment_data):
        """Test la validation d'un XML enrichi"""
        # Enrichir d'abord
        enriched = processor.enrich_xml(sample_xml, enrichment_data)
        
        # Valider
        validation = processor.validate_xml(enriched)
        
        assert validation['valid'] is True
        assert validation['has_order_id'] is True
        assert validation['has_pixid_section'] is True
        assert len(validation['enriched_fields']) == 6
        
        # Vérifier que les champs enrichis sont corrects
        fields_dict = {f['field']: f['value'] for f in validation['enriched_fields']}
        assert fields_dict['code_agence'] == 'AG-75-001'
        assert fields_dict['statut'] == 'Confirmée'
    
    def test_prettify_xml(self, processor):
        """Test le formatage du XML"""
        ugly_xml = '<?xml version="1.0"?><Order><OrderId>12345</OrderId><Status>Active</Status></Order>'
        
        pretty = processor.prettify_xml(ugly_xml)
        
        assert '\n' in pretty
        assert '  ' in pretty  # Indentation
        assert '<OrderId>12345</OrderId>' in pretty
        assert '<?xml version' in pretty
    
    def test_prettify_xml_invalid(self, processor):
        """Test le formatage avec XML invalide"""
        invalid = "Not XML at all"
        
        # Ne doit pas crasher
        result = processor.prettify_xml(invalid)
        assert result == invalid
    
    def test_compare_xml(self, processor, sample_xml, enrichment_data):
        """Test la comparaison avant/après enrichissement"""
        # Enrichir
        enriched = processor.enrich_xml(sample_xml, enrichment_data)
        
        # Comparer
        comparison = processor.compare_xml(sample_xml, enriched)
        
        assert 'new_count' in comparison
        assert comparison['new_count'] > 0
        assert 'new_elements' in comparison
        
        # Vérifier que les nouveaux éléments sont détectés
        new_paths = [elem['path'] for elem in comparison['new_elements']]
        assert any('PIXIDEnrichment' in path for path in new_paths)
        assert any('AgencyCode' in path for path in new_paths)
    
    def test_complex_xml_structure(self, processor):
        """Test avec une structure XML complexe"""
        complex_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <Root>
            <Header>
                <Meta>
                    <OrderId>88888</OrderId>
                </Meta>
            </Header>
            <Body>
                <Orders>
                    <Order id="1">
                        <Details>Test</Details>
                    </Order>
                </Orders>
            </Body>
        </Root>"""
        
        # Extraction OrderId
        order_id = processor.extract_order_id(complex_xml)
        assert order_id == '88888'
        
        # Enrichissement
        data = {'code_agence': 'AG-COMPLEX', 'statut': 'Test'}
        enriched = processor.enrich_xml(complex_xml, data)
        
        root = etree.fromstring(enriched)
        pixid_section = root.find('.//PIXIDEnrichment')
        assert pixid_section is not None
        assert pixid_section.find('AgencyCode').text == 'AG-COMPLEX'
    
    def test_xml_with_cdata(self, processor):
        """Test avec des sections CDATA"""
        xml_with_cdata = """<?xml version="1.0"?>
        <Order>
            <OrderId>12345</OrderId>
            <Description><![CDATA[Description avec <caractères> spéciaux & autres]]></Description>
        </Order>"""
        
        # Parse et enrichir
        parsed = processor.parse_xml(xml_with_cdata)
        assert parsed is not None
        
        order_id = processor.extract_order_id(xml_with_cdata)
        assert order_id == '12345'
    
    def test_unicode_handling(self, processor):
        """Test la gestion des caractères Unicode"""
        unicode_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <Order>
            <OrderId>12345</OrderId>
            <Customer>José García - 北京</Customer>
        </Order>"""
        
        data = {
            'personne_absente': 'François Müller - 東京',
            'statut': 'Confirmé ✓'
        }
        
        enriched = processor.enrich_xml(unicode_xml, data)
        assert enriched is not None
        
        # Vérifier que les caractères Unicode sont préservés
        root = etree.fromstring(enriched)
        assert '北京' in etree.tostring(root, encoding='unicode')
        
        pixid_section = root.find('.//PIXIDEnrichment')
        assert '東京' in pixid_section.find('AbsentPerson').text
    
    @pytest.mark.parametrize("order_id", [
        "12345",
        "00001",
        "999999999",
        "2024001"
    ])
    def test_various_order_id_formats(self, processor, order_id):
        """Test avec différents formats d'OrderId"""
        xml = f"""<?xml version="1.0"?>
        <Order>
            <OrderId>{order_id}</OrderId>
        </Order>"""
        
        extracted = processor.extract_order_id(xml)
        assert extracted == order_id
    
    def test_performance_large_xml(self, processor):
        """Test de performance avec un gros XML"""
        # Créer un gros XML
        large_xml = """<?xml version="1.0"?>
        <Orders>
            <OrderId>99999</OrderId>"""
        
        # Ajouter beaucoup d'éléments
        for i in range(1000):
            large_xml += f"""
            <Item id="{i}">
                <Name>Product {i}</Name>
                <Price>{i * 10}</Price>
                <Description>Long description for item {i}</Description>
            </Item>"""
        
        large_xml += "</Orders>"
        
        import time
        
        # Test extraction
        start = time.time()
        order_id = processor.extract_order_id(large_xml)
        extract_time = time.time() - start
        
        assert order_id == '99999'
        assert extract_time < 0.5  # Devrait être rapide
        
        # Test enrichissement
        start = time.time()
        enriched = processor.enrich_xml(large_xml, {'code_agence': 'AG-PERF'})
        enrich_time = time.time() - start
        
        assert enriched is not None
        assert enrich_time < 1.0  # Devrait prendre moins d'1 seconde


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
