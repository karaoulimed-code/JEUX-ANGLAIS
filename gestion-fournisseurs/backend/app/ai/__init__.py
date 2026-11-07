"""Module 12 — Architecture d'intelligence artificielle (intégration progressive).

Principes retenus :
1. Chaque fonction « intelligente » est derrière une interface (`Protocol`) : la version actuelle
   est une implémentation déterministe et explicable (règles, statistiques) ; un modèle d'IA
   (LLM, apprentissage automatique) pourra la remplacer sans toucher au reste du logiciel.
2. Toute sortie comporte une justification lisible (`raisons`).
3. Aucune sortie de l'IA ne déclenche d'opération sensible : elle produit des PROPOSITIONS
   (brouillon de facture, alerte, priorité de paiement) soumises à un utilisateur habilité.

Fonctions déjà opérationnelles (règles explicables) :
- détection des doublons de factures et de fournisseurs (services.invoices / services.suppliers) ;
- détection des variations anormales de prix (contrôle PRIX_ANORMAL + score statistique ci-dessous) ;
- priorisation des paiements (services.analytics.payment_plan) ;
- score de risque et de dépendance fournisseurs (services.analytics.supplier_risk) ;
- prévisions de décaissements (services.analytics.forecast).

Points d'extension non encore activés (renvoient « non activé », jamais un faux résultat) :
- lecture automatique de factures (OCR / extraction) : `InvoiceExtractor` ;
- assistance à l'analyse des contrats et génération de commentaires de rapports : `TextAssistant`.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ExtractedInvoice:
    """Brouillon issu d'une lecture automatique : toujours à valider par un agent."""
    supplier_tax_id: str | None = None
    supplier_number: str | None = None
    invoice_date: str | None = None
    total_ht: str | None = None
    total_tva: str | None = None
    total_ttc: str | None = None
    confidence: float = 0.0
    raisons: list[str] = field(default_factory=list)


class InvoiceExtractor(Protocol):
    def extract(self, content: bytes, filename: str) -> ExtractedInvoice: ...


class TextAssistant(Protocol):
    def summarize_contract(self, text: str) -> dict: ...


class NotEnabledExtractor:
    enabled = False

    def extract(self, content: bytes, filename: str) -> ExtractedInvoice:
        raise NotImplementedError(
            "Lecture automatique non activée : brancher un moteur OCR/IA (voir docs/02-conception-technique.md §IA).")


def price_zscore(history: list[float], value: float) -> dict:
    """Score d'anomalie de prix explicable (écart en nombre d'écarts-types)."""
    if len(history) < 3:
        return {"score": None, "raisons": ["Historique insuffisant (moins de 3 prix)."]}
    mu = statistics.mean(history)
    sd = statistics.pstdev(history) or (mu * 0.01) or 1.0
    z = (value - mu) / sd
    raisons = [f"Prix moyen historique {mu:.3f}, écart-type {sd:.3f}, prix analysé {value:.3f} (z = {z:.2f})."]
    if z > 3:
        raisons.append("Hausse très inhabituelle : vérifier le contrat et demander une justification.")
    return {"score": round(z, 2), "anormal": z > 3, "raisons": raisons}


extractor: InvoiceExtractor = NotEnabledExtractor()
