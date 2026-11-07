import { useState } from "react";
import { Alert, Badge, Button, Card, Checkbox, Group, SegmentedControl, Stack, Table, Text } from "@mantine/core";
import { IconCheck, IconDownload, IconAlertTriangle } from "@tabler/icons-react";
import { api, download } from "../api";
import { useAuth } from "../auth";
import { useQ } from "../hooks";
import { date, money } from "../format";
import { DataTable, PageHeader, StatusBadge, notifyError, useAction } from "../components/ui";
import { useQueryClient } from "@tanstack/react-query";

export default function Accounting() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState("PROPOSEE");
  const { data = [], isLoading } = useQ<any[]>(["entries", status], `/accounting/entries?status=${status}&limit=3000`);
  const coh = useQ<any>(["coherence"], "/coherence");
  const [sel, setSel] = useState<number[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const val = useAction(() => api("/accounting/validate", { body: { ids: sel } }), (r) => `${r.validated} écriture(s) validée(s)`, () => setSel([]));
  const exp = async () => {
    try {
      await download("/accounting/export");
      qc.invalidateQueries();
    } catch (e) { notifyError(e); }
  };
  return (
    <>
      <PageHeader title="Intégration comptable" subtitle="Écritures proposées à partir des opérations du poste clients — validation puis export vers le logiciel comptable"
                  actions={<>{can("accounting.validate") && status === "PROPOSEE" && <Button disabled={!sel.length} onClick={() => val.mutate(undefined)} loading={val.isPending} leftSection={<IconCheck size={16} />}>Valider la sélection ({sel.length})</Button>}
                    {can("accounting.export") && <Button variant="default" leftSection={<IconDownload size={16} />} onClick={exp}>Exporter les écritures validées</Button>}</>} />
      {coh.data && (
        <Alert mb="md" color={coh.data.ok ? "teal" : "red"} icon={coh.data.ok ? <IconCheck /> : <IconAlertTriangle />} title="Contrôle de concordance du poste clients">
          {coh.data.ok ? <>Grand livre auxiliaire ({money(coh.data.total_ledger_tnd)} TND) = postes ouverts ({money(coh.data.total_open_items_tnd)}) − crédits non affectés ({money(coh.data.total_unallocated_tnd)}). Aucune anomalie.</>
            : <Stack gap={2}>{coh.data.anomalies.slice(0, 20).map((a: any, i: number) => <Text key={i} size="sm">{a.type} : {JSON.stringify(a)}</Text>)}</Stack>}
        </Alert>)}
      <Alert color="gray" mb="md">Ce module tient le suivi auxiliaire des créances ; il ne remplace pas la comptabilité générale. Les numéros de comptes sont paramétrables (Paramétrage › accounts) et doivent être validés par l'expert-comptable. Une écriture exportée devient intangible.</Alert>
      <Card withBorder radius="md">
        <SegmentedControl mb="sm" value={status} onChange={(v) => { setStatus(v); setSel([]); }} data={[{ value: "PROPOSEE", label: "Proposées" }, { value: "VALIDEE", label: "Validées" }, { value: "EXPORTEE", label: "Exportées" }]} />
        <DataTable rows={data} loading={isLoading} pageSize={50} onRowClick={(r) => setOpen(open === r.id ? null : r.id)} columns={[
          ...(status === "PROPOSEE" && can("accounting.validate") ? [{ key: "sel", label: "", sortable: false, render: (r: any) => (
            <Checkbox checked={sel.includes(r.id)} onClick={(e) => e.stopPropagation()} onChange={(e) => setSel((s) => (e.currentTarget.checked ? [...s, r.id] : s.filter((x) => x !== r.id)))} />) }] : []),
          { key: "number", label: "N°" }, { key: "journal", label: "Journal", render: (r) => <Badge variant="light">{r.journal}</Badge> },
          { key: "entry_date", label: "Date", render: (r) => date(r.entry_date) }, { key: "label", label: "Libellé", render: (r) => (
            <div><Text size="sm">{r.label}</Text>{open === r.id && <Table fz="xs" mt={4} withTableBorder><Table.Tbody>{r.lines.map((l: any, i: number) => (
              <Table.Tr key={i}><Table.Td>{l.account}</Table.Td><Table.Td>{l.aux_account}</Table.Td><Table.Td>{l.label}</Table.Td><Table.Td ta="right">{Number(l.debit) ? money(l.debit) : ""}</Table.Td><Table.Td ta="right">{Number(l.credit) ? money(l.credit) : ""}</Table.Td></Table.Tr>))}</Table.Tbody></Table>}</div>) },
          { key: "total", label: "Montant", align: "right", render: (r) => money(r.total) }, { key: "status", label: "Statut", render: (r) => <StatusBadge code={r.status} /> },
          { key: "export_batch", label: "Lot d'export" },
        ]} />
        {status === "PROPOSEE" && can("accounting.validate") && data.length > 0 && <Button mt="xs" size="xs" variant="subtle" onClick={() => setSel(data.map((d) => d.id))}>Tout sélectionner</Button>}
      </Card>
    </>
  );
}
