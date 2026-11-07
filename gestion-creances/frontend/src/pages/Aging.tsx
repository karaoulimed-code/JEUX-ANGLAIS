import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Group, Select, Table, Text } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { qs } from "../api";
import { useQ, useRefs } from "../hooks";
import { iso, money, pct, RISK_LABELS } from "../format";
import { Amount, DataTable, ExportMenu, PageHeader, StatusBadge } from "../components/ui";

export default function Aging() {
  const nav = useNavigate();
  const refs = useRefs();
  const [asOf, setAsOf] = useState<Date | null>(new Date());
  const [f, setF] = useState<any>({ group_by: "customer" });
  const params = { ...f, as_of: iso(asOf) };
  const { data, isLoading } = useQ<any>(["aging", params], `/aging${qs(params)}`);
  const set = (k: string) => (v: any) => setF((x: any) => ({ ...x, [k]: v || undefined }));
  const buckets = data?.buckets || [];
  const cols: any[] = [
    { key: "name", label: f.group_by === "customer" ? "Client" : "Regroupement", render: (r: any) => <Text size="sm" fw={500} miw={220}>{r.name}</Text> },
    ...buckets.map((b: any) => ({ key: b.code, label: b.label, align: "right", render: (r: any) => (Number(r[b.code]) ? <Amount v={r[b.code]} color={b.code === "NON_ECHU" ? undefined : b.code.startsWith("1-") ? "yellow.9" : "red.7"} /> : <Text size="sm" c="dimmed">—</Text>) })),
    { key: "total", label: "Total", align: "right", render: (r: any) => <Amount v={r.total} strong /> },
    { key: "unallocated", label: "Crédits non affectés", align: "right", render: (r: any) => (Number(r.unallocated) ? <Amount v={-r.unallocated} /> : "—") },
    { key: "net", label: "Solde net", align: "right", render: (r: any) => <Amount v={r.net} /> },
  ];
  if (f.group_by === "customer") cols.push({ key: "risk_class", label: "Risque", render: (r: any) => <StatusBadge code={r.risk_class} label={r.risk_class ? RISK_LABELS[r.risk_class] : null} /> });
  return (
    <>
      <PageHeader title="Balance âgée clients" subtitle={`Calculée à partir des restes dus réels de chaque échéance au ${asOf ? asOf.toLocaleDateString("fr-FR") : ""} — montants en ${data?.currency || "TND"}`}
                  actions={<ExportMenu path={`/reports/balance-agee${qs({ ...f, date_to: iso(asOf) })}`} />} />
      <Card withBorder radius="md">
        <Group mb="md" gap="xs" wrap="wrap" align="flex-end">
          <DateInput label="Date d'arrêté" value={asOf} onChange={setAsOf} valueFormat="DD/MM/YYYY" maxDate={new Date()} w={150} />
          <Select label="Regrouper par" w={170} value={f.group_by} onChange={(v) => setF((x: any) => ({ ...x, group_by: v || "customer" }))}
                  data={[{ value: "customer", label: "Client" }, { value: "group", label: "Groupe de clients" }, { value: "salesperson", label: "Commercial" }, { value: "risk", label: "Niveau de risque" }, { value: "currency", label: "Devise" }]} />
          <Select label="Devise" w={110} clearable data={["TND", "EUR", "USD"]} value={f.currency || null} onChange={set("currency")} />
          <Select label="Niveau de risque" w={150} clearable data={Object.entries(RISK_LABELS).map(([value, label]) => ({ value, label }))} value={f.risk_class || null} onChange={set("risk_class")} />
          <Select label="Catégorie" w={170} clearable data={refs.categories} value={f.category_code || null} onChange={set("category_code")} />
          <Select label="Zone" w={150} clearable searchable data={refs.zones} value={f.zone_code || null} onChange={set("zone_code")} />
          <Select label="Commercial" w={170} clearable data={refs.salespeople} value={f.salesperson_id || null} onChange={set("salesperson_id")} />
        </Group>
        <DataTable rows={data?.rows || []} columns={cols} loading={isLoading} rowKey="key" pageSize={50}
                   onRowClick={(r) => r.customer_id && nav(`/clients/${r.customer_id}`)}
                   footer={data && (
                     <>
                       <Table.Tr style={{ fontWeight: 700 }}><Table.Td>TOTAL</Table.Td>
                         {buckets.map((b: any) => <Table.Td key={b.code} ta="right"><Amount v={data.totals[b.code]} strong /></Table.Td>)}
                         <Table.Td ta="right"><Amount v={data.totals.total} strong /></Table.Td><Table.Td ta="right"><Amount v={-data.totals.unallocated} /></Table.Td>
                         <Table.Td ta="right"><Amount v={data.totals.net} strong /></Table.Td>{f.group_by === "customer" && <Table.Td />}</Table.Tr>
                       <Table.Tr><Table.Td><Text size="xs" c="dimmed">Répartition</Text></Table.Td>
                         {buckets.map((b: any) => <Table.Td key={b.code} ta="right"><Text size="xs">{pct(data.percentages[b.code])}</Text></Table.Td>)}
                         <Table.Td colSpan={f.group_by === "customer" ? 4 : 3} /></Table.Tr>
                     </>)} />
        <Text size="xs" c="dimmed" mt="xs">Les montants en devises sont convertis au cours historique de chaque facture. Total des créances brutes : {money(data?.totals?.total)}.</Text>
      </Card>
    </>
  );
}
