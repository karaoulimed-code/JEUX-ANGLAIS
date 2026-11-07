import { useNavigate } from "react-router-dom";
import { Alert, Badge, Card, Grid, SimpleGrid, Stack, Tabs, Text, Title } from "@mantine/core";
import { BarChart } from "@mantine/charts";
import { IconSparkles } from "@tabler/icons-react";
import { useQ } from "../hooks";
import { date, money } from "../format";
import { Amount, DataTable, ExportMenu, Kpi, PageHeader } from "../components/ui";

export default function Forecast() {
  const nav = useNavigate();
  const f = useQ<any>(["forecast"], "/ai/forecast");
  const an = useQ<any[]>(["anomalies"], "/ai/anomalies");
  const syn = useQ<any>(["synthesis"], "/ai/synthesis");
  const d = f.data;
  const weeks = (d?.weeks || []).map((w: any) => ({ semaine: date(w.week_start).slice(0, 5), Factures: Number(w.invoices), "Chèques / effets": Number(w.instruments), Contractuel: Number(w.contractual) }));
  const total13 = (d?.weeks || []).reduce((s: number, w: any) => s + Number(w.total), 0);
  return (
    <>
      <PageHeader title="Prévisions d'encaissement et aide à la décision" subtitle="Modèles statistiques explicables, fondés sur l'historique réel des règlements de chaque client"
                  actions={<ExportMenu path="/reports/prevision-encaissements" />} />
      <Alert color="violet" mb="md" icon={<IconSparkles />}>{d?.method} Les propositions sont indicatives : toute action sensible reste décidée par un utilisateur habilité.</Alert>
      <SimpleGrid cols={{ base: 1, sm: 4 }} mb="md">
        <Kpi label="Encaissements prévus (13 sem.)" value={money(total13)} />
        <Kpi label="Au-delà de 13 semaines" value={money(d?.beyond_horizon)} />
        <Kpi label="Exclus (recouvrement incertain)" value={money(d?.excluded_uncertain)} color="red.7" hint="Douteux, litigieux ou > 180 j" />
        <Kpi label="Anomalies détectées" value={an.data?.length ?? "…"} color={an.data?.length ? "orange.7" : undefined} />
      </SimpleGrid>
      <Grid>
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Card withBorder radius="md">
            <Title order={5} mb="sm">Prévision hebdomadaire (TND)</Title>
            <BarChart h={300} data={weeks} dataKey="semaine" type="stacked" withLegend valueFormatter={(v) => money(v)}
                      series={[{ name: "Factures", color: "brand.6" }, { name: "Chèques / effets", color: "teal.6" }]} />
            <Text size="xs" c="dimmed" mt="xs">Comparaison : selon les seules échéances contractuelles, {money((d?.weeks || []).reduce((s: number, w: any) => s + Number(w.contractual), 0))} TND seraient attendus sur la période.</Text>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Card withBorder radius="md" h="100%">
            <Title order={5} mb="sm">Synthèse rédigée</Title>
            <Text size="sm" style={{ whiteSpace: "pre-line" }}>{syn.data?.text}</Text>
            <Text size="xs" c="dimmed" mt="sm">Générée par {syn.data?.generated_by}.</Text>
          </Card>
        </Grid.Col>
      </Grid>
      <Card withBorder radius="md" mt="md">
        <Tabs defaultValue="details">
          <Tabs.List><Tabs.Tab value="details">Date probable de paiement par échéance</Tabs.Tab><Tabs.Tab value="anomalies">Anomalies et comportements inhabituels</Tabs.Tab><Tabs.Tab value="mois">Vue mensuelle</Tabs.Tab></Tabs.List>
          <Tabs.Panel value="details" pt="md">
            <DataTable rowKey="installment_id" rows={d?.details || []} onRowClick={(r) => nav(`/factures/${r.invoice_id}`)} columns={[
              { key: "number", label: "Facture" }, { key: "due_date", label: "Échéance", render: (r) => date(r.due_date) },
              { key: "remaining_tnd", label: "Reste dû", align: "right", render: (r) => <Amount v={r.remaining_tnd} /> },
              { key: "predicted_date", label: "Date probable", render: (r) => (r.predicted_date ? date(r.predicted_date) : <Badge color="red" variant="light">exclu</Badge>) },
              { key: "confidence", label: "Fiabilité", render: (r) => <Badge variant="light" color={r.confidence === "BONNE" ? "teal" : r.confidence === "MOYENNE" ? "yellow" : r.confidence === "EXCLU" ? "red" : "gray"}>{r.confidence.toLowerCase()}</Badge> },
              { key: "rule", label: "Règle appliquée", render: (r) => <Text size="xs">{r.rule}</Text> },
            ]} />
          </Tabs.Panel>
          <Tabs.Panel value="anomalies" pt="md">
            <Stack gap={6}>{(an.data || []).map((a, i) => (
              <Alert key={i} color={a.severity === "ELEVEE" ? "red" : "orange"} title={`${a.type.replaceAll("_", " ").toLowerCase()} — ${a.customer_name || ""}`}
                     style={{ cursor: "pointer" }} onClick={() => nav(`/clients/${a.customer_id}`)}>{a.message}</Alert>))}
              {!an.data?.length && <Text c="dimmed" size="sm">Aucune anomalie détectée.</Text>}</Stack>
          </Tabs.Panel>
          <Tabs.Panel value="mois" pt="md">
            <DataTable rowKey="month" rows={d?.months || []} searchable={false} columns={[
              { key: "month", label: "Mois" }, { key: "invoices", label: "Factures", align: "right", render: (r) => <Amount v={r.invoices} /> },
              { key: "instruments", label: "Chèques / effets", align: "right", render: (r) => <Amount v={r.instruments} /> }, { key: "total", label: "Total", align: "right", render: (r) => <Amount v={r.total} strong /> },
            ]} />
          </Tabs.Panel>
        </Tabs>
      </Card>
    </>
  );
}
