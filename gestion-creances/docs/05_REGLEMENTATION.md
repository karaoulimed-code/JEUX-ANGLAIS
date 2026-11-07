---
title: "Cadre comptable et fiscal — traitements retenus et points à valider"
subtitle: "Gestion intégrée du poste clients — version 1.0 — état au 07/11/2026"
---

> **Avertissement.** Ce document décrit les traitements paramétrés dans le logiciel. Il ne constitue pas un avis juridique ou fiscal. Les taux et seuils tunisiens changent souvent (loi de finances annuelle) : chaque valeur est **datée** et marquée « à valider » dans le paramétrage tant qu'un expert-comptable tunisien ne l'a pas confirmée.

# 1. Règles tunisiennes (obligations)

| Sujet | Texte | Traitement dans le logiciel | Statut |
|---|---|---|---|
| Système comptable | Loi n° 96-112 du 30/12/1996 ; NC 01 (norme générale) | Suivi auxiliaire des créances, écritures proposées, comptes paramétrables (plan par défaut : 411, 413, 416, 419, 491…) | Plan de comptes **à valider** |
| Intangibilité, chronologie | Loi 96-112, principes de tenue | Numérotation continue par année, pièces validées intangibles, corrections par avoir, journal d'audit inaltérable | Conforme au principe ; à confirmer |
| Conservation | Délai légal de conservation des pièces comptables (10 ans, à confirmer) | Aucune suppression d'opération validée ; sauvegardes avec empreintes ; pièces jointes conservées | Politique d'archivage à définir |
| TVA | Code de la TVA : taux général 19 % ; taux réduits 13 % et 7 % selon les opérations ; exonérations / suspensions | Codes TVA19, TVA13, TVA7, TVA0, datés et paramétrables ; TVA calculée par taux | Taux généraux constatés au 07/11/2026 ; **listes d'opérations par taux à vérifier** (la LF 2026 a modifié certains taux sectoriels) |
| FODEC | 1 % sur le chiffre d'affaires des produits industriels, inclus dans l'assiette TVA | Taxe « AUTRE » optionnelle, incluse dans l'assiette TVA | Applicabilité selon l'activité, **à valider** |
| Droit de timbre sur factures | Code des droits d'enregistrement et de timbre | 1,000 TND par facture (montant en vigueur depuis la LF 2022) | **À confirmer** : le projet de LF 2026 prévoyait une hausse ; vérifier le texte publié (loi n° 2025-17 du 12/12/2025) |
| Retenue à la source | Code de l'IRPP et de l'IS (art. 52) et Code de la TVA (retenue de TVA par l'État et certains organismes) | Moyen de paiement « Retenue à la source » justifié par un certificat ; montant saisi (pas de taux codé en dur) | Écriture au compte d'État paramétrable **à valider** |
| Provisions pour créances douteuses (comptable) | NC 01 (prudence) | Provision individuelle à hauteur de la perte probable, justifiée ; grille indicative paramétrable | Grille = politique interne, **à valider** |
| Provisions (fiscal) | Code de l'IRPP et de l'IS, art. 48 : provisions pour créances douteuses déductibles dans la limite de 50 % du bénéfice imposable (régime général), sous conditions | Indicateur « déductible » par ligne, note de rappel ; le logiciel ne calcule pas le plafond fiscal | **Conditions exactes à valider** (notamment l'exigence d'une action en justice) |
| Créances irrécouvrables | Code de l'IRPP et de l'IS ; Code de la TVA pour la récupération de la TVA | Passage en perte avec approbation et justificatifs ; régularisation de TVA désactivée par défaut (paramètre) | **À valider** (jugement, procédure collective, PV de carence…) |
| Facturation électronique | Réglementation tunisienne (TTN / El Fatoora), en évolution (proposition de loi examinée en 2026) | Hors périmètre : le logiciel n'est pas une plateforme homologuée ; les factures émises ailleurs peuvent être importées | **À vérifier** selon l'activité de chaque client |
| Mentions obligatoires des factures | Code de la TVA (art. 18) | Matricule fiscal client et fournisseur, numéro, date, détail HT/TVA/TTC, timbre sur le PDF | Mentions complémentaires à compléter dans le modèle (RNE, conditions, pénalités) |

# 2. Référentiels internationaux (optionnels)

| Norme | Usage dans le logiciel | Ce n'est **pas** |
|---|---|---|
| IFRS 9 — pertes de crédit attendues | Campagne « IFRS9 » : approche simplifiée (créances commerciales), matrice de taux par tranche d'ancienneté appliquée à toutes les créances ; aide au calibrage par les taux de perte historiques | Une obligation pour les comptes sociaux tunisiens ; par défaut, aucune écriture n'est générée (paramètre `provision.statutory_method = NCT`) |
| IFRS 15 | Reconnaissance du chiffre d'affaires : hors périmètre (le logiciel part de factures émises) ; les avoirs traduisent les ajustements de prix | Un moteur de reconnaissance du revenu |
| IFRS 7 | Les états balance âgée, concentration et provisions fournissent les données d'annexe sur le risque de crédit | Une annexe rédigée |
| IAS 1 | Distinction créances / avances clients (crédits non affectés présentés séparément) | — |

La matrice IFRS 9 par défaut (0,5 % ; 1,5 % ; 4 % ; 8 % ; 20 % ; 50 %) est **illustrative** : elle doit être calibrée sur l'historique de l'entreprise et ajustée des informations prospectives (IFRS 9 § 5.5.17).

# 3. Liste des points à faire valider par l'expert-comptable

1. Plan de comptes utilisé pour les écritures proposées (paramètre `accounts`).
2. Montant du droit de timbre en vigueur et sa date d'effet.
3. Liste des opérations soumises aux taux de TVA de 13 % et 7 % pour l'activité du client ; applicabilité du FODEC.
4. Traitement comptable de la retenue à la source subie (compte, imputation).
5. Base de la provision NCT (HT ou TTC) et grille indicative par ancienneté.
6. Conditions de déductibilité fiscale des provisions et des pertes (art. 48) et suivi du plafond de 50 %.
7. Conditions de récupération de la TVA sur créances irrécouvrables (paramètre `writeoff.recover_vat`).
8. Obligation éventuelle de facturation électronique et mentions obligatoires des factures.
9. Durée de conservation et politique d'archivage.

# 4. Sources consultées (vérification du 07/11/2026)

- PwC, *Tunisia — Corporate — Other taxes* (taux de TVA et mesures de la LF 2026) : taxsummaries.pwc.com/tunisia/corporate/other-taxes
- Ministère des Finances, *Aperçu général sur la fiscalité* (provisions pour créances douteuses, limite de 50 %) : finances.gov.tn/fr/apercu-general-sur-la-fiscalite
- La Presse, *Toutes les nouvelles taxes prévues par le projet de loi de finances pour 2026* (19/10/2025) : lapresse.tn
- African Manager, *La loi de finances 2026 publiée au JORT* : africanmanager.com
- Tunisie Numérique, *Vers un amendement du cadre de la facturation électronique* (2026) : tunisienumerique.com

Les sources secondaires ci-dessus ne remplacent pas le texte officiel (JORT, notes communes de la DGI).
