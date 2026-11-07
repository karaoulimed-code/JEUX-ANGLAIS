import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Badge, Card, Grid, Group, HoverCard, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { BarChart, CompositeChart, DonutChart } from "@mantine/charts";
import { IconCheck, IconInfoCircle, IconAlertTriangle } from "@tabler/icons-react";
import { useQ } from "../hooks";
import { iso, money, pct, RISK_LABELS } from "../format";
import { Amount, Kpi, PageHeader } from "../components/ui";
import { useAuth } from "../auth";

function Formula({ text }: { text: string }) {
  return (
    <HoverCard width={320} shadow="md" withArrow>
      <HoverCard.Target><IconInfoCircle size={14} style={{ cursor: "help" }} color="gray" /></HoverCard.Target>
      <HoverCard.Dropdown><Text size="xs">{text}</Text></HoverCard.Dropdown>
    </HoverCard>
  );
}

const compact = (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1).replace(".", ",")} M` : Math.abs(v) >= 1e3 ? `${Math.round(v / 1e3)} k` : String(v));
const BUCKET_COLORS = ["teal.6", "yellow.5", "orange.5", "orange.7", "red.6", "red.9"];
const RISK_COLORS: Record<string, string> = { FAIBLE: "teal.6", MODERE: "yellow.5", ELEVE: "orange.6", CRITIQUE: "red.7", NON_EVALUE: "gray.4" };

export default function Dashboard() {
  const nav = useNavigate();
  const { can } = useAuth();
  const [asOf, setAsOf] = useState<Date | null>(new Date());
  const { data: d, isLoading } = useQ<any>(["dashboard", iso(asOf)], `/dashboard?as_of=${iso(asOf)}`);
  const coh = useQ<any>(["coherence"], can("accounting.read") ? "/coherence" : null);
  const syn = useQ<any>(["synthesis"], "/ai/synthesis");
  if (isLoading || !d) return <Text>Chargement du tableau de bord…</Text>;
  const t = d.totals;
  const aging = d.aging.buckets.map((b: any, i: number) => ({ tranche: b.label, montant: Number(d.aging.totals[b.code]), color: BUCKET_COLORS[i] }));
  const trend = d.trend.map((m: any) => ({ mois: m.month.slice(5) + "/" + m.month.slice(2, 4), Encours: Number(m.receivables), "Dont échu": Number(m.overdue),
    Facturé: Number(m.sales), Encaissé: Number(m.collections) }));
  const risk = Object.entries(d.risk_distribution).map(([k, v]) => ({ name: RISK_LABELS[k] || "Non évalué", value: v as number, color: RISK_COLORS[k] || "gray.4" }));
  return (
    <>
      <PageHeader title="Tableau de bord du poste clients" subtitle={`Situation au ${new Date(d.as_of).toLocaleDateString("fr-FR")} — période depuis le ${new Date(d.period_start).toLocaleDateString("fr-FR")}`}
                  actions={<DateInput value={asOf} onChange={setAsOf} valueFormat="DD/MM/YYYY" label="Date d'arrêté" maxDate={new Date()} w={160} />} />
      {coh.data && (
        <Alert mb="md" color={coh.data.ok ? "teal" : "red"} icon={coh.data.ok ? <IconCheck /> : <IconAlertTriangle />} p="xs">
          {coh.data.ok
            ? `Contrôle de concordance : grand livre auxiliaire = postes ouverts (${money(coh.data.total_ledger_tnd)} TND). Factures, règlements et soldes cohérents.`
            : `${coh.data.anomalies.length} anomalie(s) de concordance détectée(s) — voir Intégration comptable.`}
        </Alert>
      )}
      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} mb="md">
        <Kpi label="Total des créances" value={money(t.receivables)} hint={`Net des crédits non affectés : ${money(t.net_receivables)}`} />
        <Kpi label="Non échues" value={money(t.not_due)} color="teal.7" />
        <Kpi label="Échues" value={money(t.overdue)} color="orange.7" hint={`Taux d'impayés : ${pct(d.unpaid_rate.value)}`} />
        <Kpi label="Douteuses / litigieuses" value={money(Number(t.doubtful) + Number(t.disputed))} color="red.7"
             hint={`Douteuses ${money(t.doubtful)} · litigieuses ${money(t.disputed)}`} />
        <Kpi label={`Encaissements de la période`} value={money(t.collections_period)} hint={`Facturé sur la période : ${money(t.sales_period)}`} />
        <Kpi label="DSO" value={d.dso.value !== null ? `${String(d.dso.value).replace(".", ",")} j` : "n.d."}
             icon={<Formula text={d.dso.formula} />} hint={`Méthode ${d.dso.method === "COMPTABLE" ? "comptable" : "par épuisement"}`} />
        <Kpi label="Taux de recouvrement" value={pct(d.recovery_rate.value)} icon={<Formula text={d.recovery_rate.formula} />}
             hint={`Exigible : ${money(d.recovery_rate.exigible)}`} />
        <Kpi label="Concentration" value={pct(d.concentration.top_share_pct)} icon={<Formula text={d.concentration.formula} />}
             hint={`Top ${d.concentration.top_n} débiteurs · HHI ${d.concentration.hhi}`} />
      </SimpleGrid>
      <Grid mb="md">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Card withBorder radius="md" h="100%">
            <Title order={5} mb="sm">Évolution mensuelle (12 mois, TND)</Title>
            <CompositeChart h={280} data={trend} dataKey="mois" withLegend valueFormatter={(v) => money(v)} yAxisProps={{ width: 70, tickFormatter: compact }}
                            series={[{ name: "Encours", color: "brand.7", type: "area" }, { name: "Dont échu", color: "orange.6", type: "line" },
                                     { name: "Facturé", color: "gray.5", type: "bar" }, { name: "Encaissé", color: "teal.6", type: "bar" }]} />
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Card withBorder radius="md" h="100%">
            <Title order={5} mb="sm">Répartition par ancienneté</Title>
            <BarChart h={220} data={aging} dataKey="tranche" series={[{ name: "montant", label: "Montant", color: "brand.6" }]} yAxisProps={{ width: 60, tickFormatter: compact }}
                      valueFormatter={(v) => money(v)} getBarColor={(v) => aging.find((a: any) => a.montant === v)?.color || "brand.6"} />
            <Group gap={6} mt="xs">{d.aging.buckets.map((b: any) => (
              <Badge key={b.code} variant="light" color="gray" size="sm">{b.label} : {pct(d.aging.percentages[b.code], 0)}</Badge>))}</Group>
          </Card>
        </Grid.Col>
      </Grid>
      <Grid>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card withBorder radius="md" h="100%">
            <Title order={5} mb="sm">Principaux débiteurs</Title>
            <Table fz="sm" highlightOnHover>
              <Table.Thead><Table.Tr><Table.Th>Client</Table.Th><Table.Th ta="right">Encours</Table.Th><Table.Th ta="right">Part</Table.Th><Table.Th>Risque</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{d.concentration.top.slice(0, 10).map((r: any) => (
                <Table.Tr key={r.customer_id} style={{ cursor: "pointer" }} onClick={() => nav(`/clients/${r.customer_id}`)}>
                  <Table.Td>{r.name}</Table.Td><Table.Td ta="right"><Amount v={r.amount} /></Table.Td><Table.Td ta="right" style={{ whiteSpace: "nowrap" }}>{pct(r.share_pct)}</Table.Td>
                  <Table.Td>{r.risk_class ? <Text size="xs" fw={700} c={RISK_COLORS[r.risk_class]}>{RISK_LABELS[r.risk_class]}</Text> : "—"}</Table.Td>
                </Table.Tr>))}</Table.Tbody>
            </Table>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6, lg: 4 }}>
          <Card withBorder radius="md" h="100%">
            <Title order={5} mb="sm">Dépassements de plafond</Title>
            {!d.over_limit.length && <Text size="sm" c="dimmed">Aucun client au-delà de son plafond.</Text>}
            <Stack gap={6}>{d.over_limit.slice(0, 8).map((r: any) => (
              <Group key={r.customer_id} justify="space-between" wrap="nowrap" style={{ cursor: "pointer" }} onClick={() => nav(`/clients/${r.customer_id}`)}>
                <Text size="sm" lineClamp={1}>{r.name}</Text><Amount v={r.overrun} color="red.7" />
              </Group>))}</Stack>
            <Text size="xs" c="dimmed" mt="sm">Chèques / effets en portefeuille : {money(t.instruments_pending)} ({t.instruments_pending_count})</Text>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6, lg: 3 }}>
          <Card withBorder radius="md" h="100%">
            <Title order={5} mb="sm">Clients par niveau de risque</Title>
            <DonutChart data={risk} h={180} withLabelsLine withLabels mx="auto" />
          </Card>
        </Grid.Col>
      </Grid>
      {syn.data && (
        <Card withBorder radius="md" mt="md">
          <Group justify="space-between"><Title order={5}>Synthèse automatique</Title><Text size="xs" c="dimmed">{syn.data.generated_by}</Text></Group>
          <Text size="sm" mt="xs" style={{ whiteSpace: "pre-line" }}>{syn.data.text}</Text>
        </Card>
      )}
    </>
  );
}
