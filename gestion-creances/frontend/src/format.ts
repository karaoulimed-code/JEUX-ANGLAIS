import dayjs from "dayjs";

// Montants : 3 décimales (millimes), séparateur de milliers espace, virgule décimale.
const nf3 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const nf0 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });

export function money(v: any, currency?: string): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v) || 0;
  if (Number.isNaN(Number(v))) return String(v);
  return nf3.format(n) + (currency ? ` ${currency}` : "");
}
export function int(v: any): string {
  if (v === null || v === undefined) return "—";
  return nf0.format(Number(v));
}
export function pct(v: any, digits = 1): string {
  if (v === null || v === undefined) return "n.d.";
  return `${Number(v).toFixed(digits).replace(".", ",")} %`;
}
export function date(v: any): string {
  if (!v) return "—";
  return dayjs(v).format("DD/MM/YYYY");
}
export function datetime(v: any): string {
  if (!v) return "—";
  return dayjs(v).format("DD/MM/YYYY HH:mm");
}
export function iso(d: Date | string | null | undefined): string | undefined {
  if (!d) return undefined;
  return dayjs(d).format("YYYY-MM-DD");
}
export function today(): string {
  return dayjs().format("YYYY-MM-DD");
}
export const STATUS_COLORS: Record<string, string> = {
  BROUILLON: "gray", VALIDEE: "blue", NON_ECHUE: "blue", PARTIELLEMENT_REGLEE: "cyan", REGLEE: "green", EN_RETARD: "orange",
  LITIGIEUSE: "grape", DOUTEUSE: "red", IRRECOUVRABLE: "dark", IMPUTE: "green", NON_IMPUTE: "yellow", PARTIELLEMENT_IMPUTE: "cyan",
  EN_PORTEFEUILLE: "yellow", REMIS: "cyan", ENCAISSE: "green", REJETE: "red", ANNULE: "gray",
  FAIBLE: "green", MODERE: "yellow", ELEVE: "orange", CRITIQUE: "red",
  PROPOSEE: "yellow", EXPORTEE: "gray", EN_ATTENTE: "yellow", APPROUVEE: "green", REJETEE: "red",
};
export const RISK_LABELS: Record<string, string> = { FAIBLE: "Faible", MODERE: "Modéré", ELEVE: "Élevé", CRITIQUE: "Critique" };
export const PAYMENT_STATUS: Record<string, string> = {
  EN_PORTEFEUILLE: "En portefeuille", REMIS: "Remis en banque", ENCAISSE: "Encaissé", REJETE: "Rejeté", ANNULE: "Annulé",
};
export const CLASSIFICATIONS: Record<string, string> = { NORMALE: "Normale", LITIGIEUSE: "Litigieuse", DOUTEUSE: "Douteuse", IRRECOUVRABLE: "Irrécouvrable" };
export const STATUS_LABELS: Record<string, string> = {
  FAIBLE: "faible", MODERE: "modéré", ELEVE: "élevé", CRITIQUE: "critique", PROPOSEE: "proposée", VALIDEE: "validée", EXPORTEE: "exportée",
  REJETEE: "rejetée", EN_ATTENTE: "en attente", APPROUVEE: "approuvée", EN_PORTEFEUILLE: "en portefeuille", REMIS: "remis", ENCAISSE: "encaissé",
  REJETE: "rejeté", ANNULE: "annulé",
};
