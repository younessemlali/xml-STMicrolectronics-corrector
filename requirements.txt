Contexte
Je développe une automatisation RH autour de la plateforme PIXID.
J’ai :
• des confirmations de commande en .eml dans un dossier Drive (lien ci‑dessous)
• un Google Sheet (lien ci‑dessous) où je dois consigner certaines données
• des fichiers XML associés aux mêmes commandes à enrichir.

Tâches à automatiser

Toutes les 15 minutes, un script Python doit :
  a. scanner le dossier Drive https://drive.google.com/drive/folders/1YevTmiEAycLE2X0g01juOO-cWm-O6V2F
  b. pour chaque nouveau .eml / .txt : extraire 
     • Numéro de commande
     • Code agence ou code unité
     • Statut
     • Niveau convention collective
     • Classification de l’intérimaire
     • Personne absente
  c. s’assurer que le Google Sheet https://docs.google.com/spreadsheets/d/1eVoS4Pd6RiL-4PLaZWC5s8Yzax6VbT5D9Tz5K2deMs4 contient une colonne pour chaque champ et y ajouter les lignes correspondantes.

Publier ce script sur GitHub, exécutable via GitHub Actions (cron */15 * * * *).

Créer une application Streamlit (hébergée sur ce même dépôt) qui :
  a. charge un fichier XML, détecte son <OrderId>
  b. recherche les informations correspondantes dans le Google Sheet
  c. insère ou met à jour les balises manquantes (statut, niveau CC, classification, personne absente, etc.)
  d. permet de télécharger le XML enrichi.

Contraintes
• La correspondance se fait uniquement via le numéro de commande.
• Utiliser exclusivement les API REST natives de Google (Drive, Sheets) accessibles via authentification par Service Account ; aucun service nécessitant un déploiement dans la Google Cloud Console (Cloud Functions, Cloud Run, Firestore, etc.).
• Code en Python 3.11, packages ouverts (gspread, lxml, streamlit).
• Ajouter un module de monitoring : tableau de bord Streamlit affichant les statistiques clés (nombre de commandes traitées, temps moyen de traitement, erreurs/parses échoués, date/heure de la dernière exécution, etc.).
• Processus itératif exigé :
  1. Fournir d’abord un plan détaillé.
  2. Puis générer fichier par fichier (ex. sync_drive_to_sheet.py, puis workflow.yml, puis app.py, etc.), en attendant et sollicitant explicitement mon retour après chaque fichier avant de poursuivre.
• Sécurité : stocker les credentials via secrets GitHub.
• Documentation et tests unitaires bienvenus.

Livrables attendus
• sync_drive_to_sheet.py – script principal.
• .github/workflows/sync.yml – workflow cron.
• app.py – Streamlit avec tableau de bord monitoring/statistiques.
• requirements.txt, README.md.
Le travail doit se faire étape par étape, avec validation utilisateur entre chaque fichier.
