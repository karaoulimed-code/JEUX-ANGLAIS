import { useState } from "react";
import { today } from "../format";
import { Card, ExportButtons, Field, useCan } from "../components/ui";

const REPORTS: [string, string, string][] = [
  ["balance-auxiliaire", "Balance auxiliaire fournisseurs", "Solde initial, mouvements et solde final par fournisseur sur la période."],
  ["grand-livre", "Grand livre auxiliaire fournisseurs", "Toutes les pièces par fournisseur avec solde cumulé."],
  ["balance-agee", "Balance âgée fournisseurs", "Ventilation par ancienneté à la date d'arrêté."],
  ["journal-achats", "Journal des achats", "Factures, avoirs et acomptes validés de la période."],
  ["journal-reglements", "Journal des règlements", "Décaissements de la période (y compris rejets)."],
  ["factures-non-reglees", "État des factures non réglées", "Factures validées avec solde restant dû."],
  ["factures-litigieuses", "État des factures litigieuses", "Factures faisant l'objet d'un litige ouvert."],
  ["engagements", "État des engagements", "Commandes approuvées non encore facturées."],
  ["avances", "État des avances fournisseurs", "Avances versées et reste à imputer."],
  ["retenues-source", "État des retenues à la source", "Base pour la déclaration mensuelle et les certificats de retenue."],
  ["echeancier", "Échéancier des paiements", "Factures à payer triées par échéance."],
  ["previsions", "Prévisions de décaissements", "Décaissements certains, probables et conditionnels."],
  ["risques", "Analyse des risques fournisseurs", "Score explicable par fournisseur."],
];

export default function Reports() {
  const [from, setFrom] = useState(today().slice(0, 4) + "-01-01");
  const [to, setTo] = useState(today());
  const can = useCan();
  return (
    <div>
      <h2>États et exports</h2>
      <Card><div className="row gap">
        <Field label="Du"><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="Au / date d'arrêté"><input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
      </div></Card>
      <div className="grid g2">{REPORTS.filter(([k]) => k !== "previsions" || can("treasury.read")).map(([k, title, desc]) => (
        <Card key={k} title={title} actions={<ExportButtons name={k} params={`&date_from=${from}&as_of=${to}`} />}><p className="muted">{desc}</p></Card>))}</div>
    </div>
  );
}
