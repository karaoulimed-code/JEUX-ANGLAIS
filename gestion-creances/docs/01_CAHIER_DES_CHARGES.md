---
title: "Gestion intégrée du poste clients"
subtitle: "Cahier des charges fonctionnel et technique — version 1.0"
date: "Novembre 2026"
---

# 1. Objet et périmètre

## 1.1 Objet

Le logiciel est un système **intégré** de gestion du poste clients (*Accounts Receivable Management*) destiné en priorité aux PME tunisiennes. Il couvre le cycle complet :

> Client → (commande) → Facture → Échéance → Encaissement → Affectation du règlement → Solde client → Balance âgée → Recouvrement → Analyse du risque → Prévision de trésorerie → Reporting financier.

Il ne s'agit pas d'une juxtaposition de modules : **toutes les vues sont calculées à partir des mêmes données de base** (factures, échéances, règlements, affectations). Une opération saisie une seule fois met à jour, dans la même transaction, le solde du client, la balance âgée, l'encours, la notation de risque (au prochain calcul), les prévisions et les écritures comptables proposées.

Analogie bancaire : comme dans un *core banking*, il n'existe qu'un seul « livre » des opérations ; les états (balance âgée, encours, risque) sont des vues de ce livre et non des fichiers parallèles à rapprocher.

## 1.2 Ce que le logiciel n'est pas

- Ce n'est **pas un logiciel de comptabilité générale** : il tient le suivi auxiliaire des créances et **propose** des écritures, validées puis exportées vers le logiciel comptable de l'entreprise.
- Ce n'est pas un logiciel de facturation électronique homologué : il peut créer des factures, mais l'éventuelle obligation de facturation électronique (TTN / El Fatoora) relève du logiciel de facturation de l'entreprise (voir § 9, points à valider).
- La gestion des commandes est hors périmètre de la version 1.0 : la référence de commande est conservée sur la facture.

## 1.3 Utilisateurs et profils

| Profil | Rôle dans le processus | Ce qu'il ne peut pas faire |
|---|---|---|
| Administrateur | Utilisateurs, paramètres, journal d'audit | Valider des opérations financières (écritures, provisions, approbations) |
| Directeur financier (DAF) | Pilotage, plafonds de crédit, validation des provisions, passages en perte, dérogations | Approuver ses propres demandes |
| Responsable comptable | Factures, règlements, lettrage, propositions de provisions, validation et export des écritures | Valider sa propre campagne de provisions ; modifier un plafond sans approbation |
| Agent de recouvrement | Relances, actions, classement en litige, demande de passage en perte | Saisir des règlements, voir la comptabilité |
| Commercial | Consultation de **son** portefeuille, création de fiches prospects | Voir les autres clients, saisir des règlements, accéder au tableau de bord global |
| Consultation seule | Lecture de toutes les données de gestion | Toute modification |

La matrice détaillée des droits est affichée dans l'écran *Utilisateurs* et définie dans `backend/app/permissions.py`.

# 2. Processus métier

## 2.1 Création et gestion du client

1. Création de la fiche (code automatique ou manuel, raison sociale, matricule fiscal unique, coordonnées, conditions de règlement, classification).
2. Le **plafond de crédit** (créances ouvertes maximales) et l'**encours maximal** (créances + chèques et effets reçus non encore encaissés) ne peuvent être fixés que par le DAF à la création ; toute modification ultérieure crée une **demande d'approbation** traitée par une autre personne.
3. Le blocage / déblocage / archivage d'un client passe aussi par une approbation.

*Hypothèse retenue* : distinguer plafond et encours maximal reprend la logique bancaire « sauf bonne fin » : un chèque reçu éteint la facture mais le risque subsiste jusqu'à l'encaissement effectif.

## 2.2 Facturation

1. Saisie d'un **brouillon** (lignes, quantités, remises, codes TVA, autres taxes comme le FODEC, droit de timbre, devise, échéancier).
2. Les montants sont calculés par le serveur avec les **taux en vigueur à la date de la facture** (moteur de paramétrage daté).
3. **Validation** : attribution d'un numéro chronologique continu par type et par année (FAC-AAAA-NNNNN, AV-AAAA-NNNNN), conversion en TND, contrôle du plafond, détection des doublons, génération de l'écriture de vente proposée.
4. Une pièce validée est **intangible** (contrôle applicatif + déclencheur PostgreSQL) : toute correction passe par un **avoir**.
5. Un avoir lié à une facture est imputé automatiquement sur celle-ci à sa validation ; sinon il reste « non imputé » et peut être imputé ensuite.

## 2.3 Encaissement et lettrage

1. Saisie du règlement (espèces, chèque, virement, effet, **retenue à la source**, autres moyens paramétrables).
2. **Affectation** dans la même opération : automatique (échéance la plus ancienne d'abord, factures litigieuses exclues par défaut), manuelle (montant par facture), ou aucune (avance).
3. L'affectation se fait au niveau de l'**échéance**. Chaque affectation met à jour : l'échéance, la facture, le crédit source, l'écart de change, et propose les écritures nécessaires.
4. La partie non affectée constitue une **avance / règlement non affecté**, visible sur la fiche client et en déduction dans la balance âgée.
5. **Chèques et effets** : statuts *en portefeuille → remis en banque → encaissé* ou *rejeté*. Un rejet annule automatiquement les affectations (la facture redevient due), enregistre l'incident et alimente la notation de risque.
6. **Annulation** d'un règlement (erreur de saisie) : jamais de suppression ; demande d'approbation puis contre-passation tracée.
7. **Écart de règlement** (frais bancaires, arrondi) : soldé par une OD si l'écart est inférieur à la tolérance paramétrée (1,000 TND par défaut).
8. **Différences de change** : calculées à chaque affectation entre le cours de la facture et celui du règlement, et portées au grand livre auxiliaire et en écriture (gain 755 / perte 655 par défaut).

## 2.4 Échéances et recouvrement

1. Le système identifie : échéances à 7 jours (paramétrable), factures échues, retards, clients en retard récurrent (notation), créances nécessitant une action.
2. **Niveaux de relance** paramétrables (par défaut : J+7 relance amiable, J+30 deuxième relance, J+60 mise en demeure, J+90 transmission juridique).
3. **Escalade progressive** : le niveau proposé est le niveau suivant le dernier niveau atteint, à condition que son seuil de retard soit atteint et qu'un délai minimal (8 jours) se soit écoulé depuis la dernière action. Une promesse de paiement en cours suspend la proposition.
4. Chaque action est **historisée** : date, client, factures et montants dus à la date de l'action, canal, responsable, résultat, promesse, prochaine action, commentaires, texte du courrier.
5. Modèles de lettres et courriels personnalisables avec variables. **Aucun envoi automatique** : le courrier est généré, relu, imprimé ou copié par l'agent.
6. La transmission au service juridique marque le client « en contentieux ».

## 2.5 Créances douteuses, provisions et pertes

1. **Classement** d'une facture en litigieuse ou douteuse : justification obligatoire (10 caractères minimum), tracée, écriture de reclassement 411 → 416 proposée ; retour possible en créance normale.
2. **Campagne de provisions** à une date d'arrêté, selon l'un des deux référentiels (voir § 6) ; proposée par une personne, **validée par une autre** ; tout écart avec le taux suggéré doit être justifié ; seule une campagne validée du référentiel statutaire génère des écritures (dotation / reprise).
3. **Passage en perte** (irrécouvrable / abandon de créance) : demande motivée, approbation par une seconde personne habilitée, OD de passage en perte, reprise de la provision existante, statut « Irrécouvrable ».

## 2.6 Intégration comptable

Chaque événement produit une écriture **proposée**, équilibrée, avec compte auxiliaire client ; le comptable la **valide**, puis l'**exporte** (CSV générique). Une écriture exportée devient intangible (déclencheur). Les numéros de comptes sont paramétrables.

# 3. Règles de gestion

| N° | Règle |
|---|---|
| RG01 | Tous les montants sont stockés en décimal exact (18,3) ; arrondi « au plus proche, 0,5 vers le haut » à 3 décimales (millime). Jamais de nombre à virgule flottante. |
| RG02 | Le TTC d'une facture = HT + TVA (par taux, sur assiette incluant les taxes « dans l'assiette » comme le FODEC) + autres taxes + droit de timbre. |
| RG03 | La somme des échéances est égale au TTC ; la contre-valeur TND de la dernière échéance absorbe l'arrondi de conversion. |
| RG04 | Une affectation ne peut excéder ni le reste dû de l'échéance, ni le disponible du crédit ; crédit et facture doivent appartenir au même client et être dans la même devise. |
| RG05 | La dernière affectation d'une échéance (resp. d'un règlement) solde exactement sa contre-valeur TND : aucune poussière d'arrondi ne subsiste. |
| RG06 | Statut de règlement calculé (jamais périmé) : Brouillon > Irrécouvrable > Réglée > Douteuse > Litigieuse > En retard > Partiellement réglée > Non échue. « Validée » est l'état de cycle de vie de toute pièce non brouillon. |
| RG07 | Aucune suppression d'une pièce validée, d'un règlement, d'une affectation ou d'une OD : uniquement contre-passation tracée. |
| RG08 | Les opérations sensibles (plafond, blocage, passage en perte, annulation de règlement, validation de provisions) exigent deux personnes distinctes. |
| RG09 | La balance âgée est recalculée à partir des affectations **datées** : une balance au 31/12 reste exacte même si la facture a été réglée depuis. |
| RG10 | Concordance permanente : à toute date, solde du grand livre auxiliaire = Σ restes dus des échéances − crédits non affectés (contrôle automatique sur le tableau de bord et chaque nuit). |
| RG11 | Les numéros de pièces sont continus et chronologiques par type et par année (verrou de ligne : pas de doublon même en saisie simultanée). |
| RG12 | Chèque : un même numéro ne peut être enregistré deux fois pour un même client. |
| RG13 | Date de réception d'un règlement dans le futur interdite ; date de rejet antérieure à la réception interdite. |
| RG14 | Les factures importées d'un autre logiciel sont considérées comme émises (validées) et ne génèrent pas d'écriture par défaut (déjà comptabilisées à l'origine). |

# 4. Cas particuliers et risques identifiés

| Cas | Traitement retenu |
|---|---|
| Règlement supérieur aux factures ouvertes | Le surplus reste en avance, lettrable plus tard (automatique ou manuel). |
| Règlement d'une facture en devise par un virement en TND | Refusé (devises différentes) ; saisir le règlement dans la devise de facturation avec le cours du jour. *Évolution possible* : conversion inter-devises. |
| Chèque rejeté après encaissement | Autorisé (impayé tardif) : contre-passation depuis la banque. |
| Retenue à la source opérée par le client | Moyen de paiement « Retenue à la source » justifié par le n° de certificat ; affecté comme un règlement ; écriture au compte d'État (paramétrable). |
| Facture contestée | Classement « litigieuse », exclue du lettrage automatique, suivie dans le recouvrement. |
| Écart minime | OD d'écart de règlement sous la tolérance ; au-delà, passage en perte avec approbation. |
| Saisie simultanée par deux utilisateurs | Verrous de ligne (SELECT … FOR UPDATE) sur factures, règlements et séquences. |
| Paramètre fiscal modifié en cours d'année | Nouvelle version datée ; les pièces antérieures conservent le taux figé à leur validation. |
| Client archivé | Plus de facturation ; historique conservé. |
| Altération directe de la base | Bloquée par déclencheurs ; toute altération du journal d'audit casse la chaîne d'empreintes (détectée par « Vérifier l'intégrité »). |

# 5. Indicateurs

Voir le document *Indicateurs et conventions de calcul* (04_INDICATEURS.md) : DSO (méthode comptable et méthode par épuisement), taux de recouvrement, taux d'impayés, concentration (top N, indice HHI), répartition par ancienneté, évolution mensuelle.

# 6. Référentiels comptables

Le logiciel sépare strictement :

- **les règles tunisiennes** (Système comptable des entreprises, loi n° 96-112, NCT ; fiscalité : Code de la TVA, Code de l'IRPP et de l'IS, droits de timbre) ;
- **les traitements IFRS** (IFRS 9 pertes de crédit attendues, IFRS 15, IFRS 7, IAS 1), proposés pour un reporting groupe ou IFRS, **jamais présentés comme une obligation tunisienne**.

Détail, sources et points à valider : document 05_REGLEMENTATION.md.

# 7. Intelligence artificielle (aide à la décision)

Niveau 1 livré, **entièrement explicable** (aucune boîte noire, aucune donnée transmise à l'extérieur) :

| Fonction | Méthode |
|---|---|
| Date probable de paiement | Échéance + retard médian historique du client (24 mois, ≥ 3 observations), à défaut médiane de tous les clients ; indice de fiabilité. |
| Prévision d'encaissement 13 semaines / 6 mois | Somme des dates probables + chèques/effets en portefeuille à leur date de valeur ; créances douteuses, litigieuses ou > 180 jours exclues. |
| Risque croissant | Critère « tendance » du score + alerte de dégradation de classe. |
| Anomalies | Doublons de factures, règlements anormalement élevés (> moyenne + 3 écarts-types), dégradation du comportement de paiement, règlements non affectés > 30 jours. |
| Priorités de recouvrement | Échu × (1 + score de risque) × facteur d'ancienneté, avec justification. |
| Synthèse financière | Texte généré par règles à partir des indicateurs. |
| Rédaction des relances | Modèles paramétrables avec variables. |

Un point d'extension (`AIProvider`) permet de brancher ultérieurement un modèle de langage ; il est désactivé par défaut, et toute proposition reste validée par un utilisateur habilité.

# 8. Exigences techniques

- **Architecture** : API REST Python/FastAPI, base PostgreSQL 16, interface React/TypeScript (Mantine). Détail : 03_ARCHITECTURE_API_SECURITE.md.
- **Déploiement** : local (serveur de l'entreprise) ou cloud, par Docker Compose ; sauvegardes quotidiennes automatiques avec empreintes SHA-256 ; script de restauration testé.
- **Interface** : français ; architecture de traduction (arabe en écriture de droite à gauche, anglais) ; dates JJ/MM/AAAA ; TND avec 3 décimales ; adaptée ordinateur, tablette et smartphone.
- **Performances constatées** (jeu de démonstration, 10 clients, 175 factures) : tableau de bord < 1 s, balance âgée < 0,1 s.

# 9. Hypothèses retenues et points ouverts

| N° | Ambiguïté | Hypothèse retenue | À valider par |
|---|---|---|---|
| H1 | « Validée » vs autres statuts | Deux axes : cycle de vie (brouillon/validée) et statut de règlement calculé | Utilisateurs clés |
| H2 | Plafond vs encours maximal | Plafond = créances ouvertes ; encours max = créances + chèques/effets non encaissés | DAF |
| H3 | Base de la provision NCT | HT (TVA récupérable en cas de perte définitive) — paramétrable | Expert-comptable |
| H4 | Grille de taux NCT | Aide indicative (25 % / 50 % / 100 % selon ancienneté), justification au cas par cas | Expert-comptable, commissaire aux comptes |
| H5 | Taux de recouvrement | Encaissements / (échu à l'ouverture + échéances de la période) | DAF |
| H6 | DSO | Méthode comptable sur 90 jours par défaut ; méthode par épuisement disponible | DAF |
| H7 | Comptes comptables | Plan par défaut (411, 413, 416, 419, 4366, 491, 6817, 7817, 634, 655, 755…) | Expert-comptable |
| H8 | Facturation électronique | Hors périmètre : le logiciel n'est pas une plateforme homologuée | Expert-comptable / conseil fiscal |
| H9 | Montant du droit de timbre | 1,000 TND par facture, marqué « à confirmer » (révision envisagée par la LF 2026) | Expert-comptable |
