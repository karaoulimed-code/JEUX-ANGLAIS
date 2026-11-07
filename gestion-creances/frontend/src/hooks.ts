import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export const useQ = <T = any>(key: any[], path: string | null, opts: { enabled?: boolean } = {}) =>
  useQuery<T>({ queryKey: key, queryFn: () => api<T>(path as string), enabled: !!path && opts.enabled !== false });

export const useRefs = () => {
  const methods = useQ<any[]>(["payment-methods"], "/payment-methods");
  const taxes = useQ<any[]>(["tax-rates"], "/tax-rates");
  const refs = useQ<any[]>(["reference-values"], "/reference-values");
  const users = useQ<any[]>(["users"], "/users");
  const currencies = useQ<any[]>(["currencies"], "/currencies");
  const opt = (kind: string) => (refs.data || []).filter((r) => r.kind === kind && r.active).map((r) => ({ value: r.code, label: r.label }));
  return {
    methods: (methods.data || []).filter((m) => m.active),
    taxes: taxes.data || [],
    vatOptions: (taxes.data || []).filter((t) => t.kind === "TVA" && t.active).map((t) => ({ value: t.code, label: t.label })),
    otherTaxOptions: (taxes.data || []).filter((t) => t.kind === "AUTRE" && t.active).map((t) => ({ value: t.code, label: t.label })),
    zones: opt("ZONE"), categories: opt("CATEGORY"), sectors: opt("SECTOR"), groups: opt("GROUP"),
    users: users.data || [],
    salespeople: (users.data || []).filter((u) => u.role === "COMMERCIAL").map((u) => ({ value: String(u.id), label: u.full_name })),
    currencies: (currencies.data || []).filter((c) => c.active).map((c) => ({ value: c.code, label: `${c.code} – ${c.label}` })),
  };
};
