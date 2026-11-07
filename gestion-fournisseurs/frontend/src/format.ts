// Formats tunisiens : montants à 3 décimales (millimes), dates JJ/MM/AAAA.
const nf = new Intl.NumberFormat("fr-TN", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
export function money(v: any, cur?: string): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(n)) return String(v);
  return nf.format(n) + (cur ? " " + cur : "");
}
export function num(v: any, d = 1) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("fr-TN", { maximumFractionDigits: d }).format(Number(v));
}
export function dt(v: any): string {
  if (!v) return "—";
  const s = String(v).slice(0, 10);
  const [y, m, d] = s.split("-");
  return d && m && y ? `${d}/${m}/${y}` : s;
}
export function dtime(v: any): string {
  if (!v) return "—";
  const d = new Date(String(v).endsWith("Z") ? v : v + "Z");
  return d.toLocaleString("fr-TN");
}
export const today = () => new Date().toISOString().slice(0, 10);
