import { useState } from "react";
import { Alert, Badge, Button, Card, Grid, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Switch, Table, Text, Textarea, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconInfoCircle } from "@tabler/icons-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useQ } from "../hooks";
import { date, datetime, iso, money } from "../format";
import { Amount, DataTable, ExportMenu, Kpi, PageHeader, StatusBadge, useAction } from "../components/ui";

function LineEditor({ line, onClose }: { line: any; onClose: () => void }) {
  const [rate, setRate] = useState<number | string>(Number(line?.rate || 0));
  const [just, setJust] = useState(line?.justification || "");
  const [fisc, setFisc] = useState(!!line?.fiscal_deductible);
  const save = useAction(() => api(`/provisions/lines/${line.id}`, { method: "PUT", body: { rate: String(rate), justification: just, fiscal_deductible: fisc } }), "Ligne mise à jour", onClose);
  if (!line) return null;
  return (
    <Modal opened onClose={onClose} title={`Provision — facture ${line.invoice_number}`} size="lg">
      <Stack>
        <SimpleGrid cols={3}><Kpi label="Encours TTC" value={money(line.outstanding_tnd)} /><Kpi label="Base" value={money(line.base_tnd)} /><Kpi label="Taux suggéré" value={`${Number(line.suggested_rate)} %`} /></SimpleGrid>
        <NumberInput label="Taux retenu (%)" min={0} max={100} decimalScale={2} value={rate} onChange={setRate} />
        <Text size="sm">Provision : <b>{money((Number(line.base_tnd) * Number(rate || 0)) / 100)} TND</b></Text>
        <Textarea label="Justification (obligatoire si le taux diffère de la suggestion)" value={just} onChange={(e) => setJust(e.currentTarget.value)} autosize minRows={3}
                  placeholder="ex. : déclaration de créance déposée le …, redressement judiciaire, garanties, dividende attendu…" />
        <Switch label="Conditions fiscales de déductibilité réunies (à confirmer par l'expert-comptable)" checked={fisc} onChange={(e) => setFisc(e.currentTarget.checked)} />
        {line.fiscal_note && <Alert color="blue" icon={<IconInfoCircle size={16} />}>{line.fiscal_note}</Alert>}
        <Group justify="flex-end"><Button onClick={() => save.mutate(undefined)} loading={save.isPending}>Enregistrer</Button></Group>
      </Stack>
    </Modal>
  );
}

export default function Provisions() {
  const { can, user } = useAuth();
  const list = useQ<any[]>(["campaigns"], "/provisions/campaigns");
  const [sel, setSel] = useState<number | null>(null);
  const camp = useQ<any>(["campaign", sel], sel ? `/provisions/campaigns/${sel}` : null);
  const loss = useQ<any>(["loss-rates"], "/provisions/loss-rates");
  const [asOf, setAsOf] = useState<Date | null>(new Date());
  const [method, setMethod] = useState<string>("NCT");
  const [edit, setEdit] = useState<any>(null);
  const [comment, setComment] = useState("");
  const propose = useAction(() => api("/provisions/campaigns", { body: { as_of: iso(asOf), method } }), (r) => `Campagne proposée : ${money(r.total_amount_tnd)} TND`, (r) => setSel(r.id));
  const decide = useAction((approve: boolean) => api(`/provisions/campaigns/${sel}/decide`, { body: { approve, comment } }), (r) => `Campagne ${r.status.toLowerCase()}`);
  const c = camp.data;
  return (
    <>
      <PageHeader title="Créances douteuses et provisions" subtitle="Deux référentiels distincts : NCT (comptes sociaux tunisiens) et IFRS 9 (pertes de crédit attendues)"
                  actions={<><ExportMenu path="/reports/creances-douteuses" label="Créances douteuses" /><ExportMenu path={`/reports/provisions?method=${method}`} label="État des provisions" /></>} />
      <Alert color="blue" mb="md" icon={<IconInfoCircle />}>
        <b>NCT</b> : provision individuelle à hauteur de la perte probable ; la grille par ancienneté n'est qu'une aide, chaque taux doit être justifié. La déductibilité fiscale
        (art. 48 du Code de l'IRPP et de l'IS) est suivie séparément. <b>IFRS 9</b> : matrice de pertes attendues (approche simplifiée), pour un reporting IFRS ; elle ne génère pas
        d'écriture dans les comptes sociaux sauf paramétrage contraire. Chaque campagne est validée par une autre personne que son auteur.
      </Alert>
      <Grid>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          {can("provisions.propose") && (
            <Card withBorder radius="md" mb="md">
              <Title order={5} mb="sm">Nouvelle campagne</Title>
              <Stack gap="xs">
                <DateInput label="Date d'arrêté" value={asOf} onChange={setAsOf} valueFormat="DD/MM/YYYY" />
                <Select label="Référentiel" data={[{ value: "NCT", label: "NCT – comptes sociaux tunisiens" }, { value: "IFRS9", label: "IFRS 9 – pertes attendues" }]} value={method} onChange={(v) => setMethod(v || "NCT")} />
                <Button onClick={() => propose.mutate(undefined)} loading={propose.isPending}>Calculer la proposition</Button>
              </Stack>
            </Card>)}
          <Card withBorder radius="md" mb="md">
            <Title order={5} mb="sm">Campagnes</Title>
            <Stack gap={6}>{(list.data || []).map((x) => (
              <Card key={x.id} withBorder p="xs" radius="sm" style={{ cursor: "pointer", borderColor: sel === x.id ? "var(--mantine-color-brand-6)" : undefined }} onClick={() => setSel(x.id)}>
                <Group justify="space-between"><Text size="sm" fw={600}>{x.method} · {date(x.as_of)}</Text><StatusBadge code={x.status} /></Group>
                <Text size="xs" c="dimmed">{x.line_count} ligne(s) · {money(x.total_amount_tnd)} TND · par {x.created_by}</Text>
              </Card>))}
              {!list.data?.length && <Text size="sm" c="dimmed">Aucune campagne.</Text>}</Stack>
          </Card>
          <Card withBorder radius="md">
            <Title order={6} mb="xs">Taux de perte historiques observés</Title>
            <Table fz="xs"><Table.Tbody>{(loss.data?.years || []).map((y: any) => <Table.Tr key={y.year}><Table.Td>{y.year}</Table.Td><Table.Td ta="right">{money(y.written_off_tnd)}</Table.Td>
              <Table.Td ta="right">{y.loss_rate_pct ?? "—"} %</Table.Td></Table.Tr>)}</Table.Tbody></Table>
            <Text size="xs" c="dimmed" mt={4}>{loss.data?.note}</Text>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 8 }}>
          {!c ? <Card withBorder radius="md"><Text c="dimmed">Sélectionnez ou calculez une campagne.</Text></Card> : (
            <Card withBorder radius="md">
              <Group justify="space-between" mb="sm">
                <div><Title order={4}>Campagne {c.method} au {date(c.as_of)}</Title>
                  <Text size="xs" c="dimmed">Proposée par {c.created_by} le {datetime(c.created_at)}{c.validated_by && ` · décidée par ${c.validated_by} le ${datetime(c.validated_at)}`}</Text></div>
                <StatusBadge code={c.status} />
              </Group>
              <SimpleGrid cols={3} mb="md"><Kpi label="Provision totale" value={money(c.total_amount_tnd)} /><Kpi label="Dotations" value={money(c.dotation)} color="red.7" /><Kpi label="Reprises" value={money(c.reprise)} color="teal.7" /></SimpleGrid>
              <DataTable rows={c.lines} onRowClick={(r) => c.status === "PROPOSEE" && can("provisions.propose") && setEdit(r)} columns={[
                { key: "invoice_number", label: "Facture" }, { key: "customer_name", label: "Client" },
                { key: "classification", label: "Classement", render: (r) => (r.classification !== "NORMALE" ? <Badge size="sm" color="grape">{r.classification.toLowerCase()}</Badge> : "—") },
                { key: "days_overdue", label: "Retard", align: "right", render: (r) => `${r.days_overdue} j` },
                { key: "base_tnd", label: "Base", align: "right", render: (r) => <Amount v={r.base_tnd} /> },
                { key: "rate", label: "Taux", align: "right", render: (r) => <Text size="sm" c={Number(r.rate) !== Number(r.suggested_rate) ? "orange.8" : undefined}>{Number(r.rate)} %</Text> },
                { key: "amount_tnd", label: "Provision", align: "right", render: (r) => <Amount v={r.amount_tnd} strong /> },
                { key: "movement_tnd", label: "Dotation / (reprise)", align: "right", render: (r) => <Amount v={r.movement_tnd} /> },
                { key: "justification", label: "Justification", render: (r) => <Text size="xs" lineClamp={2}>{r.justification || "—"}</Text> },
              ]} />
              {c.status === "PROPOSEE" && can("provisions.validate") && (
                <Group mt="md" align="flex-end">
                  <Textarea label="Commentaire de décision" value={comment} onChange={(e) => setComment(e.currentTarget.value)} style={{ flex: 1 }} autosize />
                  <Button color="red" variant="light" onClick={() => decide.mutate(false)} loading={decide.isPending}>Rejeter</Button>
                  <Button onClick={() => decide.mutate(true)} loading={decide.isPending} disabled={c.created_by === user?.full_name}>Valider</Button>
                </Group>)}
              {c.status === "PROPOSEE" && c.created_by === user?.full_name && <Text size="xs" c="orange.8" mt="xs">Vous êtes l'auteur de cette campagne : sa validation revient à une autre personne habilitée.</Text>}
            </Card>)}
        </Grid.Col>
      </Grid>
      {edit && <LineEditor line={edit} onClose={() => setEdit(null)} />}
    </>
  );
}
