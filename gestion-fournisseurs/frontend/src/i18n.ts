// Architecture multilingue : le français est complet ; l'arabe (RTL) et l'anglais couvrent
// la navigation et se complètent clé par clé (repli automatique sur le français).
export type Lang = "fr" | "ar" | "en";

const fr: Record<string, string> = {
  app: "Gestion des dettes fournisseurs", dashboard: "Tableau de bord", suppliers: "Fournisseurs",
  purchasing: "Achats & engagements", invoices: "Factures", payments: "Règlements", treasury: "Trésorerie",
  disputes: "Avoirs & litiges", aging: "Échéancier & balance âgée", forecast: "Prévisions & optimisation",
  accounting: "Comptabilité", reports: "États & exports", risk: "Risques fournisseurs", settings: "Paramètres", audit: "Journal d'audit",
  logout: "Déconnexion", search: "Rechercher (fournisseur, facture, BC, règlement)…",
  brouillon: "Brouillon", en_attente_validation: "En attente de validation", validee: "Validée", en_litige: "En litige",
  partiellement_reglee: "Partiellement réglée", echue: "Échue", non_echue: "Non échue", reglee: "Réglée", annulee: "Annulée",
  a_approuver: "À approuver", approuve: "Autorisé", emis: "Émis", debite: "Débité", rejete: "Rejeté", annule: "Annulé",
  approuvee: "Approuvée", partiellement_recue: "Partiellement reçue", recue: "Reçue", cloturee: "Clôturée", soumise: "Soumise",
  rejetee: "Rejetée", convertie: "Convertie en BC", en_attente: "En attente d'approbation", actif: "Actif", bloque: "Bloqué", inactif: "Inactif",
  ouvert: "Ouvert", en_cours: "En cours", resolu: "Résolu", clos: "Clos", a_verifier: "À vérifier", verifie: "Vérifié", remplace: "Remplacé",
  proposee: "Proposée", conforme: "Conforme", ecarts: "Écarts tolérés", bloquant: "Bloquant", non_controle: "Non contrôlée",
  strategique: "Stratégique", regulier: "Régulier", occasionnel: "Occasionnel", critique: "Critique", a_risque: "À risque",
  faible: "Faible", modere: "Modéré", eleve: "Élevé",
};
const en: Record<string, string> = {
  app: "Accounts Payable", dashboard: "Dashboard", suppliers: "Suppliers", purchasing: "Purchasing", invoices: "Invoices",
  payments: "Payments", treasury: "Treasury", disputes: "Credit notes & disputes", aging: "Aging", forecast: "Forecast",
  accounting: "Accounting", reports: "Reports", risk: "Supplier risk", settings: "Settings", audit: "Audit trail", logout: "Log out",
  search: "Search…",
};
const ar: Record<string, string> = {
  app: "إدارة ديون المزودين", dashboard: "لوحة القيادة", suppliers: "المزودون", purchasing: "المشتريات والالتزامات",
  invoices: "الفواتير", payments: "الخلاص", treasury: "الخزينة", disputes: "الإشعارات الدائنة والنزاعات", aging: "الآجال وأقدمية الديون",
  forecast: "التوقعات", accounting: "المحاسبة", reports: "التقارير", risk: "مخاطر المزودين", settings: "الإعدادات", audit: "سجل التدقيق",
  logout: "خروج", search: "بحث…",
};
const dicts: Record<Lang, Record<string, string>> = { fr, en, ar };
let current: Lang = "fr";
try { current = (localStorage.getItem("ap_lang") as Lang) || "fr"; } catch { /* stockage indisponible */ }

export function setLang(l: Lang) {
  current = l;
  try { localStorage.setItem("ap_lang", l); } catch {}
  document.documentElement.lang = l;
  document.documentElement.dir = l === "ar" ? "rtl" : "ltr";
}
export function lang() { return current; }
export function t(key: string): string { return dicts[current][key] ?? fr[key] ?? key.replace(/_/g, " "); }
setLang(current);
