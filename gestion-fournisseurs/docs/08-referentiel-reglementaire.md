# Référentiel réglementaire et comptable

**Relevé effectué le 07/11/2026.** Les valeurs ci-dessous sont livrées comme **paramètres modifiables** (table `tax_rates`, écran *Paramètres › Taux*), toutes marquées « à vérifier ». Les sources secondaires consultées divergent sur certains points : l'expert-comptable de l'entreprise doit confirmer chaque valeur avant mise en production.

## 1. Obligations tunisiennes (référentiel obligatoire)

| Domaine | Texte | Traitement dans le logiciel |
|---|---|---|
| Cadre comptable | Loi n° 96-112 du 30/12/1996, Système comptable des entreprises (SCE), NC 01 (norme générale) | Comptabilité d'engagement, journaux, pièces justificatives, irréversibilité des écritures validées, contre-passation |
| Stocks | NC 04 | Achats ventilés par compte (classe 6 ou 3) paramétrable par ligne |
| Opérations en devises | NC 15 | Conversion au cours du jour de l'opération ; différences réalisées en 655/755 ; actualisation à la clôture |
| Charges à payer / factures non parvenues | NC 01, plan SCE (408) | État FNP et écriture extournée |
| TVA déductible | Code de la TVA (taux 19 %, 13 %, 7 %, exonérations) | Taux datés, contrôle de cohérence, comptes 43661 / 43662 |
| Retenue à la source | Code de l'IRPP et de l'IS, art. 52 | Taux par nature, seuil, base TTC, opérée au paiement ; état des retenues (déclaration mensuelle, certificats) |
| Droit de timbre sur factures | Code des droits d'enregistrement et de timbre | Montant fixe paramétré, appliqué par défaut aux factures de résidents |
| Factures | Code de la TVA (mentions obligatoires), facturation électronique (El Fatoora) | Numéro, date, matricule fiscal, HT, TVA, TTC ; pièce jointe obligatoire (paramétrable) |
| Paiements en espèces | LF 2019 art. 45 (paiement non-espèces > 5 000 DT), abrogé par la LF 2026 selon la presse | Alerte au-delà du seuil paramétré |
| Conservation | Code de commerce, art. 11 ; CDPF | Aucune suppression ; journal d'audit ; sauvegardes horodatées et contrôlées |

### Taux livrés

| Code | Libellé | Valeur | Seuil | Statut |
|---|---|---|---|---|
| TVA19 / TVA13 / TVA7 / TVA0 | TVA | 19 % / 13 % / 7 % / 0 % | — | Cohérent entre sources ; aucune modification LF 2026 relevée |
| TIMBRE_FACTURE | Droit de timbre | 1,000 DT | — | Montant usuel cité ; montants spécifiques grandes surfaces (LF 2026) non intégrés |
| RS_ACHATS_1_5 | Acquisitions de biens et services | 1,5 % | 1 000 DT TTC | Le plus cohérent entre sources |
| RS_ACHATS_REDUIT | Acquisitions (fournisseurs à taux d'IS réduit) | 1 % | 1 000 DT TTC | **Sources divergentes — à confirmer** |
| RS_HONO_3 | Honoraires (personnes morales, BNC au réel) | 3 % | — | À confirmer |
| RS_HONO_10 | Honoraires (BNC forfaitaire) | 10 % | — | À confirmer |
| RS_LOYERS_10 | Loyers | 10 % | — | À confirmer |
| RS_NON_RESIDENT_15 | Non-résidents (hors convention) | 15 % | — | Vérifier la convention fiscale applicable |

### Points d'actualité 2026 à suivre

- **Facturation électronique** : extension aux prestataires de services assujettis à la TVA à compter du 01/01/2026 (art. 53 LF 2026 selon la presse), plateforme El Fatoora (TTN) ; statut des sanctions incertain (report discuté en 2026). Impact : prévoir la réception des factures électroniques (XML) en entrée.
- **Espèces** : abrogation annoncée de l'article 45 de la LF 2019 ; les règles de déductibilité et de pénalité restent à confirmer.

## 2. Référentiels internationaux (IFRS — information de gestion / groupes)

| Norme | Application dans le logiciel |
|---|---|
| IAS 1 | Distinction courant / non courant des dettes (échéancier), présentation des dettes fournisseurs |
| IAS 2 | Coût d'acquisition des stocks incluant les taxes non récupérables (timbre, autres taxes ventilés) |
| IAS 21 | Cours au jour de la transaction, conversion des éléments monétaires au cours de clôture, écarts en résultat |
| IAS 37 | Litiges : montants contestés isolés ; la décision de provisionner reste du ressort du comptable |
| IFRS 9 | Dettes fournisseurs au coût amorti (sans effet d'actualisation pour les dettes à court terme) ; décomptabilisation au paiement ou à l'extinction (avoir) |
| IFRS 7 | Risque de liquidité : échéancier, prévisions de décaissement, concentration (top 5, indice HHI) |

## 3. Distinction systématique

Le logiciel produit des écritures **conformes au SCE tunisien** (référentiel légal). Les éléments IFRS sont fournis sous forme d'**informations de gestion** (échéancier, concentration, actualisation devises) exploitables pour un reporting groupe, sans écriture de retraitement automatique.

## 4. Sources consultées le 07/11/2026

- hesabi.tn — Taux de retenue à la source en Tunisie 2026
- finco.tn — Retenue à la source en Tunisie : taux 2026
- efacturetn.com — Certificat de retenue à la source
- lapresse.tn (07/01/2026) — Facture électronique 2026
- challenges.tn — Facturation électronique obligatoire pour les services en 2026
- compta.tn — Loi de finances 2026 : mesures fiscales
- managers.tn (23/03/2026) — Levée de la restriction sur les transactions en espèces
- businessnews.com.tn (04/02/2026) — Transactions en espèces

Ces sources sont secondaires : elles ne remplacent ni le Journal officiel (JORT) ni le Code de l'IRPP et de l'IS.
