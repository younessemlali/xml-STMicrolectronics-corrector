#!/bin/bash

# Script pour créer la structure complète du projet PIXID Automation

echo "📁 Création de la structure du projet PIXID Automation..."

# Créer les dossiers principaux
mkdir -p src
mkdir -p tests/test_fixtures
mkdir -p .github/workflows
mkdir -p .streamlit
mkdir -p logs

# Créer les fichiers vides qui seront complétés plus tard
touch src/email_parser.py
touch src/google_client.py
touch src/xml_processor.py
touch src/monitoring.py

touch tests/test_email_parser.py
touch tests/test_xml_processor.py
touch tests/__init__.py

touch .streamlit/config.toml
touch .gitignore

# Créer des fichiers de test exemple
echo "📧 Création d'un fichier .eml exemple pour les tests..."
cat > tests/test_fixtures/sample.eml << 'EOF'
From: noreply@pixid.fr
To: rh@entreprise.com
Subject: Confirmation commande PIXID #12345
Date: Mon, 15 Jan 2024 10:30:00 +0100
Content-Type: text/plain; charset=UTF-8

Bonjour,

Votre commande a été confirmée avec les détails suivants :

Numéro de commande : 12345
Code agence : AG-75-001
Statut : Confirmée
Niveau convention collective : Niveau IV - Technicien
Classification de l'intérimaire : Technicien spécialisé maintenance
Personne absente : Marie DUPONT

Cordialement,
L'équipe PIXID
EOF

echo "📄 Création d'un fichier XML exemple pour les tests..."
cat > tests/test_fixtures/sample.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<PixidOrder>
    <OrderId>12345</OrderId>
    <CreationDate>2024-01-15</CreationDate>
    <Customer>
        <Name>Entreprise Test</Name>
        <Contact>contact@entreprise.com</Contact>
    </Customer>
</PixidOrder>
EOF

echo "✅ Structure créée avec succès!"
echo ""
echo "📂 Arborescence créée :"
tree -a -I '__pycache__|.git'
