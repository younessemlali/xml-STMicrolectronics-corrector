"""
Tests unitaires pour le module email_parser
"""

import pytest
from pathlib import Path
import tempfile
from datetime import datetime
import sys
import os

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.email_parser import EmailParser
from src import FIELDS_TO_EXTRACT


class TestEmailParser:
    """Tests pour la classe EmailParser"""
    
    @pytest.fixture
    def parser(self):
        """Fixture pour créer une instance du parser"""
        return EmailParser()
    
    @pytest.fixture
    def sample_eml_content(self):
        """Fixture avec un contenu EML exemple"""
        return b"""From: noreply@pixid.fr
To: rh@entreprise.com
Subject: Confirmation commande PIXID #12345
Date: Mon, 15 Jan 2024 10:30:00 +0100
Content-Type: text/plain; charset=UTF-8

Bonjour,

Votre commande a ete confirmee avec les details suivants :

Numero de commande : 12345
Code agence : AG-75-001
Statut : Confirmee
Niveau convention collective : Niveau IV - Technicien
Classification de l'interimaire : Technicien specialise maintenance
Personne absente : Marie DUPONT

Cordialement,
L'equipe PIXID
"""
    
    @pytest.fixture
    def sample_txt_content(self):
        """Fixture avec un contenu TXT exemple"""
        return """
PIXID - Confirmation de commande

Order ID: 67890
Code unite: UN-92-100
Status: En cours
Niveau CC: Cadre niveau 3
Classification interimaire: Ingenieur projet
Remplace: Jean MARTIN
Date: 2024-01-15
"""
    
    def test_initialization(self, parser):
        """Test l'initialisation du parser"""
        assert parser is not None
        assert hasattr(parser, 'patterns')
        assert len(parser.patterns) == len(FIELDS_TO_EXTRACT)
    
    def test_extract_field_single_match(self, parser):
        """Test l'extraction d'un champ avec une seule correspondance"""
        text = "Numéro de commande : 12345"
        patterns = parser.patterns['numero_commande']
        
        result = parser._extract_fields(text)
        assert result['numero_commande'] == '12345'
    
    def test_extract_field_multiple_patterns(self, parser):
        """Test avec plusieurs patterns pour le même champ"""
        texts = [
            "Commande n° : 99999",
            "Order ID : 88888",
            "Commande PIXID #77777",
            "Référence : 66666"
        ]
        
        for text in texts:
            result = parser._extract_fields(text)
            assert result['numero_commande'] is not None
            assert result['numero_commande'].isdigit()
    
    def test_extract_all_fields(self, parser):
        """Test l'extraction de tous les champs"""
        text = """
        Numéro de commande : 12345
        Code agence : AG-001
        Code unité : UN-002
        Statut : Validé
        Niveau convention collective : Niveau III
        Classification de l'intérimaire : Technicien senior
        Personne absente : Paul DURAND
        """
        
        result = parser._extract_fields(text)
        
        assert result['numero_commande'] == '12345'
        assert result['code_agence'] == 'AG-001'
        assert result['code_unite'] == 'UN-002'
        assert result['statut'] == 'Validé'
        assert result['niveau_convention_collective'] == 'Niveau III'
        assert result['classification_interimaire'] == 'Technicien senior'
        assert result['personne_absente'] == 'Paul DURAND'
    
    def test_parse_eml_file(self, parser, sample_eml_content):
        """Test le parsing d'un fichier EML"""
        with tempfile.NamedTemporaryFile(suffix='.eml', delete=False) as tmp:
            tmp.write(sample_eml_content)
            tmp_path = Path(tmp.name)
        
        try:
            result = parser.parse_file(tmp_path)
            
            assert result['numero_commande'] == '12345'
            assert result['code_agence'] == 'AG-75-001'
            assert result['statut'] == 'Confirmee'
            assert result['niveau_convention_collective'] == 'Niveau IV - Technicien'
            assert result['classification_interimaire'] == 'Technicien specialise maintenance'
            assert result['personne_absente'] == 'Marie DUPONT'
            
        finally:
            tmp_path.unlink()
    
    def test_parse_txt_file(self, parser, sample_txt_content):
        """Test le parsing d'un fichier TXT"""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
            tmp.write(sample_txt_content.encode('utf-8'))
            tmp_path = Path(tmp.name)
        
        try:
            result = parser.parse_file(tmp_path)
            
            assert result['numero_commande'] == '67890'
            assert result['code_unite'] == 'UN-92-100'
            assert result['statut'] == 'En cours'
            assert result['niveau_convention_collective'] == 'Cadre niveau 3'
            assert result['classification_interimaire'] == 'Ingenieur projet'
            assert result['personne_absente'] == 'Jean MARTIN'
            
        finally:
            tmp_path.unlink()
    
    def test_parse_file_with_content(self, parser, sample_eml_content):
        """Test le parsing avec contenu déjà chargé"""
        result = parser.parse_file('test.eml', content=sample_eml_content)
        
        assert result['numero_commande'] == '12345'
        assert result['code_agence'] == 'AG-75-001'
    
    def test_validate_and_clean(self, parser):
        """Test la validation et le nettoyage des données"""
        data = {
            'numero_commande': 'CMD-12345-X',  # Devrait extraire que les chiffres
            'code_agence': 'AG@001!',  # Devrait nettoyer les caractères spéciaux
            'code_unite': 'UN-123',  # Devrait rester intact
            'statut': 'A' * 150,  # Devrait être tronqué
            'niveau_convention_collective': None,  # Devrait rester None
            'classification_interimaire': 'nan',  # Devrait devenir None
            'personne_absente': '   Jean   '  # Devrait être nettoyé
        }
        
        cleaned = parser._validate_and_clean(data)
        
        assert cleaned['numero_commande'] == '12345'
        assert cleaned['code_agence'] == 'AG001'
        assert cleaned['code_unite'] == 'UN-123'
        assert len(cleaned['statut']) <= 103  # 100 + '...'
        assert cleaned['niveau_convention_collective'] is None
        assert cleaned['classification_interimaire'] is None
        assert cleaned['personne_absente'] == 'Jean'
    
    def test_extract_summary(self, parser):
        """Test la génération du résumé"""
        data = {
            'numero_commande': '12345',
            'code_agence': 'AG-001',
            'statut': 'Confirmé'
        }
        
        summary = parser.extract_summary(data)
        
        assert 'Commande #12345' in summary
        assert 'Agence: AG-001' in summary
        assert 'Statut: Confirmé' in summary
    
    def test_multipart_email(self, parser):
        """Test avec un email multipart (text + html)"""
        multipart_eml = b"""From: test@pixid.fr
To: test@company.com
Subject: Test multipart
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="boundary123"

--boundary123
Content-Type: text/plain; charset="utf-8"

Numero de commande : 11111
Code agence : AG-001

--boundary123
Content-Type: text/html; charset="utf-8"

<html>
<body>
<p>Numero de commande : 11111</p>
<p>Code agence : AG-001</p>
</body>
</html>

--boundary123--
"""
        
        result = parser._parse_eml('test.eml', multipart_eml)
        
        assert result['numero_commande'] == '11111'
        assert result['code_agence'] == 'AG-001'
    
    def test_invalid_email_content(self, parser):
        """Test avec un contenu email invalide"""
        invalid_content = b"This is not a valid email format"
        
        result = parser._parse_eml('invalid.eml', invalid_content)
        
        # Devrait retourner des valeurs None sans crasher
        assert all(v is None for v in result.values() if v != 'invalid.eml')
    
    def test_missing_fields(self, parser):
        """Test avec des champs manquants"""
        text = """
        Numero de commande : 99999
        Statut : Actif
        """
        
        result = parser._extract_fields(text)
        
        assert result['numero_commande'] == '99999'
        assert result['statut'] == 'Actif'
        assert result['code_agence'] is None
        assert result['code_unite'] is None
        assert result['niveau_convention_collective'] is None
    
    def test_special_characters_handling(self, parser):
        """Test la gestion des caractères spéciaux"""
        text = """
        Numéro de commande : 12345
        Code agence : AG-75-001
        Niveau CC : Employé/Technicien (niveau 2)
        Classification intérimaire : Développeur C++/Java
        Personne absente : François D'ALEMBERT
        """
        
        result = parser._extract_fields(text)
        
        assert result['numero_commande'] == '12345'
        assert result['code_agence'] == 'AG-75-001'
        assert 'niveau 2' in result['niveau_convention_collective']
        assert 'C++/Java' in result['classification_interimaire']
        assert result['personne_absente'] == "François D'ALEMBERT"
    
    def test_case_insensitive_patterns(self, parser):
        """Test que les patterns sont insensibles à la casse"""
        text = """
        NUMERO DE COMMANDE : 54321
        code Agence : ag-002
        STATUT : confirmé
        """
        
        result = parser._extract_fields(text)
        
        assert result['numero_commande'] == '54321'
        assert result['code_agence'] == 'ag-002'
        assert result['statut'] == 'confirmé'
    
    @pytest.mark.parametrize("encoding", ['utf-8', 'latin-1', 'cp1252'])
    def test_different_encodings(self, parser, encoding):
        """Test avec différents encodages"""
        text = f"Numéro de commande : 12345\nPersonne absente : José García"
        encoded = text.encode(encoding)
        
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
            tmp.write(encoded)
            tmp_path = Path(tmp.name)
        
        try:
            result = parser.parse_file(tmp_path)
            assert result['numero_commande'] == '12345'
            # Le nom peut varier selon l'encodage mais devrait être extrait
            assert result['personne_absente'] is not None
            
        finally:
            tmp_path.unlink()
    
    def test_performance_large_file(self, parser):
        """Test de performance avec un gros fichier"""
        # Créer un gros contenu avec beaucoup de lignes
        lines = ["Ligne de remplissage"] * 1000
        lines.insert(500, "Numero de commande : 99999")
        lines.insert(600, "Code agence : AG-PERF")
        
        large_content = "\n".join(lines)
        
        import time
        start = time.time()
        result = parser._extract_fields(large_content)
        duration = time.time() - start
        
        assert result['numero_commande'] == '99999'
        assert result['code_agence'] == 'AG-PERF'
        assert duration < 1.0  # Devrait prendre moins d'1 seconde


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
