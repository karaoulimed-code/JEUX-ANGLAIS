import { useState } from "react";
import { Button, Card, Group, Modal, Select, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconFileSpreadsheet, IconFileTypeCsv, IconFileTypePdf, IconEye } from "@tabler/icons-react";
import { download, qs, api } from "../api";
import { useQ } from "../hooks";
import { fmtCell } from "./reportUtil";
import { iso } from "../format";
import { DataTable, PageHeader, notifyError } from "../components/ui";

const DESC: Record<string, string> = {
  "grand-livre": "Mouvements débit/crédit d'un client et solde progressif.", "balance-auxiliaire": "Soldes d'ouverture, mouvements et soldes de clôture par client.",
  "etat-creances": "Toutes les factures ouvertes avec reste dû et retard.", "balance-agee": "Ventilation des restes dus par tranche d'ancienneté.",
  "journal-ventes": "Factures et avoirs validés, HT / TVA / timbre / TTC.", "journal-encaissements": "Règlements reçus, tous moyens et statuts.",
  "factures-impayees": "Factures échues non soldées.", "creances-douteuses": "Créances douteuses, litigieuses et irrécouvrables, avec justification.",
  provisions: "Dernière campagne de provisions validée.", "depassements-plafond": "Clients au-delà de leur plafond ou de leur encours maximal.",
  "prevision-encaissements": "Prévision hebdomadaire sur 13 semaines.", "historique-relances": "Toutes les actions de recouvrement tracées.",
};

export default function Reports() {
  const { data = [] } = useQ<any[]>(["reports"], "/reports");
  const customers = useQ<any>(["customers", "all-light"], "/customers?limit=2000&with_balance=false");
  const [from, setFrom] = useState<Date | null>(null);
  const [to, setTo] = useState<Date | null>(new Date());
  const [cust, setCust] = useState<string | null>(null);
  const [view, setView] = useState<any>(null);
  const params = (code: string) => qs({ date_from: iso(from), date_to: iso(to), customer_id: cust || undefined, ...(code === "provisions" ? { method: "NCT" } : {}) });
  const go = (code: string, fmt: string) => download(`/reports/${code}${params(code)}${params(code) ? "&" : "?"}format=${fmt}`).catch(notifyError);
  const show = (code: string) => api(`/reports/${code}${params(code)}`).then(setView).catch(notifyError);
  return (
    <>
      <PageHeader title="États et exports" subtitle="Tous les états sont calculés à partir des mêmes données que les écrans (aucune double saisie)" />
      <Card withBorder radius="md" mb="md">
        <Group align="flex-end">
          <DateInput label="Du" value={from} onChange={setFrom} valueFormat="DD/MM/YYYY" clearable w={150} />
          <DateInput label="Au / date d'arrêté" value={to} onChange={setTo} valueFormat="DD/MM/YYYY" w={170} />
          <Select label="Client (grand livre, état détaillé, relances)" searchable clearable w={340} value={cust} onChange={setCust}
                  data={(customers.data?.rows || []).map((c: any) => ({ value: String(c.id), label: `${c.code} – ${c.legal_name}` }))} />
        </Group>
      </Card>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {data.map((r) => (
          <Card key={r.code} withBorder radius="md">
            <Title order={5}>{r.label}</Title>
            <Text size="sm" c="dimmed" mb="sm" mih={40}>{DESC[r.code]}</Text>
            <Group gap={6}>
              <Button size="xs" variant="light" leftSection={<IconEye size={14} />} disabled={r.code === "grand-livre" && !cust} onClick={() => show(r.code)}>Afficher</Button>
              <Button size="xs" variant="default" leftSection={<IconFileSpreadsheet size={14} />} disabled={r.code === "grand-livre" && !cust} onClick={() => go(r.code, "xlsx")}>Excel</Button>
              <Button size="xs" variant="default" leftSection={<IconFileTypePdf size={14} />} disabled={r.code === "grand-livre" && !cust} onClick={() => go(r.code, "pdf")}>PDF</Button>
              <Button size="xs" variant="default" leftSection={<IconFileTypeCsv size={14} />} disabled={r.code === "grand-livre" && !cust} onClick={() => go(r.code, "csv")}>CSV</Button>
            </Group>
          </Card>))}
      </SimpleGrid>
      <Modal opened={!!view} onClose={() => setView(null)} title={view?.title} size="95%">
        {view && <Stack>
          {view.subtitle && <Text size="xs" c="dimmed">{view.subtitle}</Text>}
          <DataTable rows={view.rows.map((r: any, i: number) => ({ ...r, __i: i }))} rowKey="__i" pageSize={50}
                     columns={view.columns.map((c: any) => ({ key: c.key, label: c.label, align: ["amount", "pct", "int"].includes(c.kind) ? "right" : "left", render: (r: any) => fmtCell(r[c.key], c.kind) }))} />
          {view.totals && <Text size="sm" fw={600}>Totaux : {view.columns.filter((c: any) => view.totals[c.key] !== undefined && c.kind === "amount").map((c: any) => `${c.label} ${fmtCell(view.totals[c.key], "amount")}`).join(" · ")}</Text>}
        </Stack>}
      </Modal>
    </>
  );
}
