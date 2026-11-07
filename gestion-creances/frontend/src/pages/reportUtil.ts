import { date, money, pct } from "../format";
export function fmtCell(v: any, kind?: string) {
  if (v === null || v === undefined || v === "") return "";
  if (kind === "amount") return money(v);
  if (kind === "date") return date(v);
  if (kind === "pct") return pct(v);
  return String(v);
}
