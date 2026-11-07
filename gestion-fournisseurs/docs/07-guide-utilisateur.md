# Guide utilisateur

## Prise en main

1. Connectez-vous avec l'e-mail et le mot de passe fournis par l'administrateur (changez-le dès la première connexion).
2. Le menu de gauche n'affiche que les fonctions autorisées pour votre profil.
3. La barre du haut permet la **recherche globale** (fournisseur, matricule, n° de facture, BC, règlement, n° de chèque), l'accès aux **alertes** (cloche) et le choix de la langue.
4. Les montants s'affichent à 3 décimales ; les dates au format JJ/MM/AAAA. Tous les tableaux se trient en cliquant sur l'en-tête et se filtrent au-delà de 8 lignes.

Environnement de démonstration (données fictives) : comptes `admin@`, `dg@`, `daf@`, `achats@`, `compta@`, `agent@`, `tresor@`, `lecture@demo.tn`, mot de passe `Demo2026pass`.

## Paramétrage initial (administrateur et responsable comptable)

1. **Paramètres › Utilisateurs** : créez un compte par personne (jamais de compte partagé) avec le bon profil.
2. **Paramètres › Taux** : faites confirmer chaque taux par l'expert-comptable, puis décochez « À vérifier ».
3. **Paramètres › Plan de comptes** : alignez les comptes sur votre plan comptable.
4. **Paramètres › Règles de gestion** : tolérances, seuils de validation, seuil de BC obligatoire, double signature.
5. **Trésorerie** : créez vos comptes bancaires et caisses avec leur solde d'ouverture.
6. **Paramètres › Cours de change** : saisissez les cours BCT des devises utilisées.

## Responsable achats

- **Fournisseurs › Nouveau fournisseur** : le logiciel signale les doublons dès la saisie de la raison sociale ou du matricule. Le fournisseur reste « en attente » jusqu'à son approbation par le responsable comptable ou le DAF.
- **Coordonnées bancaires** : saisissez le RIB ; il devra être **vérifié par une autre personne** (contre-appel du fournisseur sur un numéro connu, jamais celui figurant sur le courrier annonçant le changement).
- **Achats › Bon de commande** : saisissez les lignes, soumettez ; le DAF (ou le DG au-delà du seuil) approuve. Une demande d'achat approuvée peut être transformée en BC en un clic.
- **Réception** (depuis le BC) : quantités reçues et rejetées ; une réception partielle laisse le BC ouvert. « Clôturer » abandonne le reliquat.
- **Litiges** : ouvrez un litige depuis la facture ou le menu Avoirs & litiges ; le montant contesté est bloqué au paiement.

## Agent comptable

- **Factures › Saisir une facture** : choisissez le fournisseur puis le BC ; chaque ligne peut être rattachée à une ligne de BC (quantité restante et prix proposés). Le timbre, la retenue et l'échéance sont calculés ; saisissez le total TTC figurant sur la facture pour contrôle.
- **Joignez le justificatif** (PDF ou image) puis **soumettez à validation**. Les anomalies s'affichent en rouge (bloquantes) ou orange (avertissements).
- **Import Excel / CSV** : téléchargez le modèle, remplissez une ligne par facture ; les factures arrivent en brouillon et suivent le circuit normal.
- Avoir : type « Avoir », puis imputation sur la facture concernée. Facture d'acompte : type « Facture d'acompte », réglée puis imputée sur la facture définitive.

## Responsable comptable, DAF, DG — validation

- **Factures** filtrées sur « En attente de validation » : ouvrez la facture, examinez les contrôles, validez votre niveau. Au-delà des seuils, un second (DAF) ou troisième niveau (DG) est requis.
- Une anomalie bloquante ne peut être levée que par le DAF, avec **justification écrite** conservée (bouton « Forcer (dérogation DAF) »). À réserver aux cas réellement justifiés.
- **Rejeter** renvoie la facture en brouillon à l'agent avec le motif.

## Trésorier — paiements

1. **Règlements › Préparation & optimisation** : indiquez l'horizon et la trésorerie mobilisable. Le logiciel classe les factures (échues, escomptes intéressants, échéances, fournisseurs stratégiques) et explique chaque recommandation. Les factures qui ne peuvent être payées sont marquées « report à négocier » : un report ne se décide **qu'avec l'accord écrit du fournisseur**.
2. Cochez, choisissez le moyen, **créez la campagne** : un règlement par fournisseur est préparé et soumis.
3. Le DAF autorise (et le DG co-signe au-delà du seuil).
4. Ouvrez chaque règlement autorisé et cliquez **Exécuter le décaissement** (n° de chèque ou d'ordre). L'écriture est proposée, la facture est soldée.
5. **Trésorerie › Importer un relevé** : collez les lignes du relevé (`JJ/MM/AAAA;libellé;montant;référence`). Les paiements correspondants passent « débités » ; les autres se rapprochent manuellement.
6. Chèque rejeté ou virement retourné : bouton **Rejet bancaire** sur le règlement — la dette est rétablie et les écritures contre-passées.

## Responsable comptable — comptabilité et clôture mensuelle

1. **Comptabilité › Écritures** : sélectionnez les écritures proposées, contrôlez-les (clic = détail), validez.
2. **Travaux de clôture** : générez l'écriture des factures non parvenues et, le cas échéant, l'actualisation des dettes en devises (extournées automatiquement le lendemain).
3. **Rapprochement auxiliaire / général** : l'écart doit être nul ; saisissez le solde 401 du logiciel comptable pour vérifier la concordance externe.
4. **Exportez** les écritures validées (CSV) vers le logiciel comptable.
5. **Paramètres › Règles de gestion › date de clôture** : avancez-la pour interdire toute opération sur la période close.

## Dirigeant et DAF — pilotage

- **Tableau de bord** : dettes totales, échues, à 7 jours, engagements non facturés, trésorerie disponible, DPO, délai moyen, ponctualité, créanciers principaux, prévisions.
- **Échéancier & balance âgée** : à n'importe quelle date d'arrêté ; export Excel/PDF.
- **Prévisions** : décaissements certains, probables, conditionnels à 7, 30, 60, 90 jours et 12 mois.
- **Risques fournisseurs** : score, niveau et facteurs (dépendance, litiges, retards, évaluation).
- **États & exports** : 13 états réglementaires et de gestion en Excel, PDF ou CSV.

## Auditeur / consultation

Profil « Consultation seule » : accès en lecture à tous les états. Le **Journal d'audit** (DG, DAF, responsable comptable, administrateur) retrace chaque action ; le bouton « Contrôler l'intégrité » détecte toute altération.
