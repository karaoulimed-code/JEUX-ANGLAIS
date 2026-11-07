---
title: "Guide utilisateur"
subtitle: "Gestion intégrée du poste clients — version 1.0"
---

# 1. Prise en main

- **Connexion** : identifiant et mot de passe fournis par l'administrateur ; changement obligatoire à la première connexion. Après 5 erreurs, le compte est verrouillé 15 minutes. La session se ferme après 30 minutes d'inactivité.
- **Menu** (à gauche) : *Pilotage* (tableau de bord, prévisions), *Cycle client* (clients, factures, encaissements, recouvrement, balance âgée, risque, provisions), *Contrôle* (états, comptabilité, approbations, imports), *Administration*. Chaque utilisateur ne voit que les menus de son rôle.
- **Recherche globale** (en haut) : tapez un nom de client, un code, un numéro de facture.
- **Cloche** : alertes du moment (plafonds dépassés, chèques à remettre, relances à faire, demandes à valider, écritures à valider, échéances proches, clients en risque critique).
- **Formats** : dates JJ/MM/AAAA ; montants en TND avec 3 décimales.
- **Tableaux** : clic sur un en-tête pour trier, zone « Filtrer le tableau » pour chercher dans les lignes affichées, clic sur une ligne pour ouvrir le détail.

# 2. Clients

*Clients › Nouveau client* : identification (raison sociale, matricule fiscal, RNE), contacts, banque, conditions (délai, devise), plafond de crédit et encours maximal (DAF), classification (catégorie, secteur, zone, groupe, commercial).

La **fiche client** présente : créances ouvertes, échu, effets/chèques en cours d'encaissement, crédits non affectés, plafond disponible ; onglets factures, règlements, **grand livre** (exportable), relances, **risque** (score détaillé critère par critère), fiche, incidents de paiement, documents, historique des modifications.

Modifier le plafond crée une **demande d'approbation** : la nouvelle valeur ne s'applique qu'après validation par une autre personne habilitée. Même principe pour bloquer ou archiver un client.

# 3. Factures et avoirs

1. *Factures › Nouvelle facture* : choisir le client (devise et échéance proposées selon ses conditions), saisir les lignes (quantité, prix HT, remise, code TVA), cocher les autres taxes (FODEC) et le timbre, éventuellement un **échéancier** (paiement en plusieurs fois : le total des échéances doit égaler le TTC).
2. *Enregistrer le brouillon* : modifiable et supprimable.
3. *Valider* : numéro définitif, contrôle du plafond (alerte, ou blocage si le paramètre est activé ; le DAF peut alors « valider par dérogation »), détection des doublons, écriture comptable proposée. **Une facture validée ne se modifie plus** : émettre un avoir (*Actions › Émettre un avoir*).
4. Le **PDF** reprend les mentions principales (matricules fiscaux, détail des taxes, échéancier).

Statuts : brouillon, non échue, partiellement réglée, réglée, en retard, litigieuse, douteuse, irrécouvrable.

*Actions* sur une facture validée : saisir un règlement, émettre un avoir, classer en litigieuse ou douteuse (justification obligatoire), revenir en créance normale, demander le passage en perte (avec justificatifs en pièce jointe), solder un petit écart de règlement.

# 4. Encaissements

*Encaissements › Saisir un règlement* : client, moyen (espèces, chèque, virement, effet, retenue à la source…), date de réception, date de valeur (échéance pour un effet), montant, devise, référence (n° de chèque, d'effet ou de certificat de retenue), banque, tireur.

**Affectation** :
- *Automatique* : les factures les plus anciennes sont soldées en premier (sauf litigieuses) ;
- *Manuelle* : indiquer le montant par facture (case à cocher = solde complet) ;
- *Avance* : aucune affectation, le montant reste disponible.

Sur la fiche du règlement : imprimer le **reçu**, affecter le solde non affecté, **délettrer** une affectation (motif obligatoire), faire évoluer un chèque ou un effet (*remis en banque*, *encaissé*, *rejeté*). Un **rejet** remet automatiquement les factures en « dû » et compte comme incident dans la notation du client. Une erreur de saisie se corrige par *Demander l'annulation* (validation par une seconde personne) : le règlement n'est jamais effacé.

Vue *Chèques / effets à encaisser* : portefeuille à remettre en banque ; la cloche signale ceux arrivés à date.

# 5. Recouvrement

*Recouvrement* propose :

- **À relancer** : clients en retard pour lesquels un niveau de relance est dû (niveau suivant le dernier atteint, délai de 8 jours entre deux relances) ou un suivi est arrivé à date ;
- **Échéances prochaines** : rappels préventifs ;
- **Suivis à faire**, **Priorités** (classement explicable), **Historique**.

Bouton *Agir* : choisir l'action, le niveau, le canal, les factures, puis *Générer* le courrier à partir du modèle (texte modifiable, copiable, imprimable). Enregistrer le résultat (promesse de paiement avec date et montant, contestation, sans réponse…) et la prochaine action. Une promesse en cours suspend les propositions jusqu'à sa date. La transmission au service juridique marque le client « en contentieux ».

# 6. Balance âgée

Choisir la **date d'arrêté** (une date passée donne la situation exacte à cette date), le regroupement (client, groupe, commercial, niveau de risque, devise) et les filtres. Les montants en devise sont en TND au cours historique, ou dans la devise si elle est filtrée. *Exporter* en Excel, PDF ou CSV.

# 7. Risque client

Score de 0 à 100 et classe (faible, modéré, élevé, critique) calculés chaque nuit et à l'ouverture de la fiche ; *Recalculer toutes les notations* à la demande. Le détail des critères (valeur constatée, points, règle) rend la note vérifiable. Les dépassements de plafond et les dégradations sont signalés.

# 8. Créances douteuses et provisions

1. *Calculer la proposition* à une date d'arrêté, en **NCT** (comptes sociaux) ou **IFRS 9** (reporting IFRS).
2. Ouvrir une ligne pour ajuster le taux : la **justification est obligatoire** si le taux diffère de la suggestion ; cocher la déductibilité fiscale si les conditions sont réunies (à confirmer avec l'expert-comptable).
3. Une **autre personne** habilitée valide ou rejette la campagne. La validation d'une campagne NCT génère les écritures de dotation et de reprise proposées.

# 9. Prévisions et aide à la décision

Prévision hebdomadaire sur 13 semaines et mensuelle (factures + chèques/effets), date probable de paiement de chaque échéance avec la règle appliquée et un indice de fiabilité, anomalies détectées, synthèse rédigée automatiquement. Ce sont des **aides** : aucune action n'est déclenchée automatiquement.

# 10. États et exports

Choisir la période et, si besoin, le client, puis *Afficher* ou exporter en Excel, PDF ou CSV : grand livre auxiliaire, balance auxiliaire, état détaillé des créances, balance âgée, journal des ventes, journal des encaissements, factures impayées, créances douteuses, provisions, dépassements de plafond, prévision des encaissements, historique des relances. Chaque export est tracé.

# 11. Intégration comptable

Les écritures sont **proposées** automatiquement. Le comptable les sélectionne et les **valide**, puis *Exporter les écritures validées* produit un fichier CSV (journal, date, pièce, compte, compte auxiliaire, libellé, débit, crédit) à importer dans le logiciel comptable. Une écriture exportée ne peut plus être modifiée. Le bandeau de **concordance** confirme en permanence que grand livre auxiliaire et postes ouverts sont égaux.

# 12. Approbations

Liste des demandes (plafond, blocage, passage en perte, annulation de règlement) avec leur objet et leur motif. Un utilisateur ne peut jamais approuver sa propre demande. Le commentaire de décision est conservé.

# 13. Imports

Télécharger le **modèle Excel**, le compléter, lancer une **simulation** (contrôle ligne par ligne, rien n'est enregistré), corriger les erreurs, puis *Importer* (tout ou rien). Importer d'abord les clients, puis les factures ouvertes.

# 14. Administration

- *Paramétrage* : règles de gestion datées (une modification s'applique à partir de sa date d'effet), taxes, moyens de paiement, devises et cours, listes de valeurs, niveaux et modèles de relance. Les valeurs fiscales marquées « à valider » doivent être confirmées par l'expert-comptable.
- *Utilisateurs* : création, rôle, réinitialisation du mot de passe, désactivation (ferme les sessions ouvertes), matrice des droits.
- *Journal d'audit* : toutes les opérations (qui, quand, quoi, avant/après) ; *Vérifier l'intégrité* contrôle la chaîne d'empreintes.
