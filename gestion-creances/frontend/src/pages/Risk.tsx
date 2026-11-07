import { useNavigate } from "react-router-dom";
import { Alert, Badge, Button, Card, Grid, Group, Progress, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { LineChart } from "@mantine/charts";
import { useAuth } from "../auth";
import { useQ } from "../hooks";
import { date, money, pct, RISK_LABELS } from "../format";
import { Amount, DataTable, ExportMenu, Kpi, PageHeader, StatusBadge, useAction } from "../components/ui";
import { api } from "../api";

export function RiskPanel({ customerId, history }: { customerId: number; history?: any[] }) {
  const { data: r } = useQ<any>(["risk", customerId], `/risk/customers/${customerId}`);
  if (!r) return <Text size="sm">Calcul…</Text>;
  return (
    <Grid>
      <Grid.Col span={{ base: 12, md: 7 }}>
        <Group mb="sm"><Title order={3}>{r.score}/100</Title><StatusBadge code={r.risk_class} label={r.risk_label} />
          {r.degraded && <Badge color="red">Dégradation</Badge>}</Group>
        {r.flags.map((f: string, i: number) => <Alert key={i} color="orange" p="xs" mb={4}>{f}</Alert>)}
        <Table fz="sm" mt="sm">
          <Table.Thead><Table.Tr><Table.Th>Critère</Table.Th><Table.Th>Valeur constatée</Table.Th><Table.Th w={160}>Points</Table.Th><Table.Th>Règle</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{r.criteria.map((c: any) => (
            <Table.Tr key={c.criterion}><Table.Td>{c.label}</Table.Td><Table.Td>{c.value}</Table.Td>
              <Table.Td><Group gap={6} wrap="nowrap"><Progress value={c.max_points ? (c.points / c.max_points) * 100 : 0} w={70} color={c.points / (c.max_points || 1) > 0.6 ? "red" : "orange"} />
                <Text size="xs">{c.points} / {c.max_points}</Text></Group></Table.Td><Table.Td><Text size="xs" c="dimmed">{c.rule}</Text></Table.Td></Table.Tr>))}</Table.Tbody>
        </Table>
        <Text size="xs" c="dimmed" mt="xs">Score explicable : somme des points de chaque critère, calculés uniquement à partir des données enregistrées ({r.metrics.observations} règlements analysés sur 12 mois). Pondérations paramétrables.</Text>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 5 }}>
        <Title order={6} mb="xs">Historique de notation</Title>
        {history && history.length > 1 ? (
          <LineChart h={200} data={[...history].reverse().map((h) => ({ date: date(h.as_of), Score: h.score }))} dataKey="date" series={[{ name: "Score", color: "red.6" }]} yAxisProps={{ domain: [0, 100] }} />
        ) : <Text size="sm" c="dimmed">Pas encore d'historique (la notation est enregistrée à chaque recalcul).</Text>}
      </Grid.Col>
    </Grid>
  );
}

export default function Risk() {
  const nav = useNavigate();
  const { can } = useAuth();
  const { data = [], isLoading } = useQ<any[]>(["risk-overview"], "/risk/overview");
  const rec = useAction(() => api("/risk/recompute", { method: "POST" }), (r) => `${r.count} clients notés — ${r.degraded.length} dégradation(s)`);
  const count = (k: string) => data.filter((d) => d.risk_class === k).length;
  return (
    <>
      <PageHeader title="Analyse du risque client" subtitle="Notation explicable, dépassements de plafond et dégradations"
                  actions={<><ExportMenu path="/reports/depassements-plafond" label="Dépassements" />{can("risk.compute") && <Button onClick={() => rec.mutate(undefined)} loading={rec.isPending}>Recalculer toutes les notations</Button>}</>} />
      <SimpleGrid cols={{ base: 2, md: 5 }} mb="md">
        {Object.entries(RISK_LABELS).map(([k, l]) => <Kpi key={k} label={`Risque ${l.toLowerCase()}`} value={count(k)} color={k === "CRITIQUE" ? "red.7" : k === "ELEVE" ? "orange.7" : undefined} />)}
        <Kpi label="Plafonds dépassés" value={data.filter((d) => d.over_limit).length} color="red.7" />
      </SimpleGrid>
      <Card withBorder radius="md">
        <DataTable rows={data} loading={isLoading} rowKey="customer_id" onRowClick={(r) => nav(`/clients/${r.customer_id}`)} columns={[
          { key: "name", label: "Client" }, { key: "risk_score", label: "Score", align: "right" },
          { key: "risk_class", label: "Classe", render: (r) => <StatusBadge code={r.risk_class} label={r.risk_class ? RISK_LABELS[r.risk_class] : null} /> },
          { key: "open_tnd", label: "Encours", align: "right", render: (r) => <Amount v={r.open_tnd} /> },
          { key: "overdue_tnd", label: "Échu", align: "right", render: (r) => <Amount v={r.overdue_tnd} /> },
          { key: "pending_instruments_tnd", label: "Effets / chèques", align: "right", render: (r) => <Amount v={r.pending_instruments_tnd} /> },
          { key: "credit_limit", label: "Plafond", align: "right", render: (r) => (Number(r.credit_limit) ? <Amount v={r.credit_limit} /> : "—") },
          { key: "limit_usage_pct", label: "Utilisation", align: "right", render: (r) => (r.limit_usage_pct !== null ? <Text size="sm" c={r.over_limit ? "red" : undefined}>{pct(r.limit_usage_pct, 0)}</Text> : "—") },
          { key: "risk_computed_at", label: "Calculé le", render: (r) => date(r.risk_computed_at) },
        ]} />
      </Card>
    </>
  );
}
