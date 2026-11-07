---
title: "Plan de développement et état d'avancement"
subtitle: "Gestion intégrée du poste clients — version 1.0 — 07/11/2026"
---

# 1. Démarche suivie

| Phase | Contenu | État |
|---|---|---|
| 1. Analyse fonctionnelle | Utilisateurs, processus, règles de gestion, cas particuliers (01_CAHIER_DES_CHARGES) | Livré |
| 2. Conception | Architecture, modèle de données, API, écrans, sécurité (02, 03) | Livré |
| 3. Développement | Modules développés dans l'ordre des dépendances : socle (paramétrage, sécurité, audit) → clients → factures/échéances → encaissements/lettrage → grand livre/balance âgée → recouvrement → risque → provisions → comptabilité → indicateurs/IA → états → interface | Livré |
| 4. Tests et validation | 38 tests automatisés sur base réelle + parcours navigateur (facture → validation → règlement → statut réglé) + test de sauvegarde/restauration | Livré, tous au vert |
| 5. Déploiement | Docker Compose, sauvegardes, scripts, guides, jeu de démonstration identifié | Livré |

# 2. Couverture des modules du cahier des charges

| Module | Couverture v1.0 |
|---|---|
| 1. Fichier clients | Complet (y compris documents, incidents, historique, classification) |
| 2. Factures | Complet ; import Excel/CSV ; détection des doublons ; devises ; échéanciers |
| 3. Encaissements | Complet ; retenue à la source ; chèques/effets ; rejets ; avances ; écarts de change et de règlement ; reçus |
| 4. Échéances et recouvrement | Complet ; escalade progressive ; modèles ; historique |
| 5. Balance âgée | Complet ; date passée ; regroupements ; exports |
| 6. Risque | Complet ; score explicable ; historique ; alertes |
| 7. Douteuses et provisions | Complet ; NCT et IFRS 9 ; quatre yeux ; passage en perte |
| 8. Tableau de bord | Complet ; formules documentées |
| 9. États | 12 états en JSON / Excel / PDF / CSV |
| 10. Intégration comptable | Écritures proposées, validation, export CSV générique |
| IA | Niveau 1 explicable (statistique) ; point d'extension pour un modèle de langage |
| Sécurité | Complet (voir 03) |

# 3. Limites connues de la version 1.0

1. Pas de module de commandes (référence de commande seulement).
2. Pas d'envoi automatique de courriels ou SMS de relance (génération, copie et impression uniquement) — choix de prudence ; un connecteur de messagerie peut être ajouté.
3. Un règlement doit être dans la devise de la facture qu'il solde (pas de conversion inter-devises au lettrage).
4. Pas de réévaluation de clôture des créances en devises (IAS 21) : contre-valeur au cours historique.
5. Export comptable en CSV générique : un format spécifique au logiciel comptable du client (Sage, Ciel, logiciel local…) est à paramétrer au déploiement.
6. Remboursement d'une avance client : à traiter par avoir ou en comptabilité générale.
7. Traductions arabe et anglaise : architecture en place (y compris l'écriture de droite à gauche), textes à compléter.
8. Le plafond fiscal de 50 % des provisions n'est pas calculé (nécessite le résultat fiscal).
9. Authentification à deux facteurs non incluse (recommandée pour les accès hors réseau de l'entreprise).

# 4. Feuille de route proposée

| Version | Contenu |
|---|---|
| 1.1 | Format d'export propre au logiciel comptable du client ; envoi des relances par courriel (avec validation) ; traduction arabe |
| 1.2 | Réévaluation des créances en devises à la clôture ; lettrage inter-devises ; remboursement d'avances |
| 1.3 | Double authentification ; connecteurs bancaires (relevés pour le rapprochement des virements) |
| 2.0 | Modèle prédictif de retard (apprentissage sur l'historique) avec explication des facteurs ; rédaction assistée des relances par modèle de langage, validée par l'agent |
