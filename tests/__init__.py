"""
Package de tests pour PIXID Automation

Organisation des tests:
- test_email_parser.py : Tests du module d'extraction des emails
- test_xml_processor.py : Tests du module de traitement XML
- test_fixtures/ : Fichiers d'exemple pour les tests
"""

import os
import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour faciliter les imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configuration commune pour les tests
TEST_FIXTURES_DIR = Path(__file__).parent / "test_fixtures"
TEST_TEMP_DIR = Path(__file__).parent / "temp"

# Créer les répertoires s'ils n'existent pas
TEST_FIXTURES_DIR.mkdir(exist_ok=True)
TEST_TEMP_DIR.mkdir(exist_ok=True)

# Variables d'environnement pour les tests
os.environ.setdefault('TESTING', 'true')
os.environ.setdefault('LOG_LEVEL', 'DEBUG')

# Désactiver les logs Streamlit pendant les tests
os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'

# Configuration pytest communes
pytest_plugins = []

def cleanup_temp_files():
    """Nettoie les fichiers temporaires créés pendant les tests"""
    if TEST_TEMP_DIR.exists():
        for file in TEST_TEMP_DIR.glob("*"):
            try:
                if file.is_file():
                    file.unlink()
            except:
                pass
