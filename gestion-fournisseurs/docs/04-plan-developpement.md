# Plan de développement et état d'avancement

## Phases réalisées (version 1.0 — 07/11/2026)

| Phase | Livrables | État |
|---|---|---|
| 1. Analyse fonctionnelle | Cahier des charges, processus, profils, règles de gestion, cas particuliers, scénarios, matrice des droits | Fait — `01-cahier-des-charges.md` |
| 2. Conception technique | Architecture, schéma de base (33 tables), API (104 opérations), sécurité, plan de tests, maquettes | Fait — `02`, `03`, `09` |
| 3. Développement | 12 modules backend connectés à PostgreSQL ; interface web complète (16 écrans) | Fait |
| 4. Tests | 54 tests automatisés, verts sur SQLite et PostgreSQL ; parcours navigateur vérifié | Fait |
| 5. Déploiement | Migrations Alembic et installation directe testées sur PostgreSQL 16 ; sauvegarde/restauration testées ; données de démonstration ; guides. Fichiers Docker Compose fournis mais **construction de l’image non testée** (refus de téléchargement Docker Hub lors du développement) | Fait — à valider : `docker compose up` sur le serveur cible |

## Feuille de route proposée

| Lot | Contenu | Priorité | Justification |
|---|---|---|---|
| L1 | Validation des paramètres fiscaux par l'expert-comptable ; recette avec une PME pilote sur un mois réel | Haute | Condition de mise en production |
| L2 | Réception des factures électroniques El Fatoora (XML TEIF) | Haute | Obligation étendue en 2026 |
| L3 | Fichiers de virement bancaire et import de relevés au format des banques tunisiennes | Haute | Supprime la ressaisie, réduit le risque de fraude |
| L4 | Certificats de retenue à la source au format officiel, préparation de la déclaration mensuelle | Moyenne | Gain de temps récurrent |
| L5 | Lecture automatique des factures (OCR + IA) branchée sur `InvoiceExtractor` | Moyenne | Gain de saisie ; toujours validée par un agent |
| L6 | Double authentification, sécurité au niveau ligne PostgreSQL | Moyenne | Prérequis SaaS |
| L7 | Console SaaS : abonnements, super-administration, invitation des utilisateurs | Selon stratégie commerciale | Commercialisation multi-entreprises |
| L8 | Traduction complète arabe / anglais des écrans métier | Selon clientèle | Architecture déjà en place |
| L9 | Connecteurs comptables dédiés (formats d'import des logiciels utilisés par les clients) | Selon clientèle | Export CSV générique disponible |

## Limites connues de la version 1.0

- Les écrans arabe et anglais traduisent la navigation ; les libellés métier détaillés restent en français.
- Le rapprochement bancaire automatique repose sur montant + référence (ou montant unique à ± 45 jours) ; les lignes non rapprochées sont traitées manuellement.
- L'évolution mensuelle des dettes est recalculée à partir des pièces (pas d'historisation figée par mois).
- La retenue sur avances se saisit manuellement (`advance_rs_amount`).
