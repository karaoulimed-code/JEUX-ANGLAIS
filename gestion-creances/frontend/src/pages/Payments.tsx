import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, Card, Checkbox, Grid, Group, Modal, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, TextInput, Textarea, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconPlus, IconReceipt } from "@tabler/icons-react";
import { api, download, qs } from "../api";
import { useAuth } from "../auth";
import { useQ, useRefs } from "../hooks";
import { date, iso, money, PAYMENT_STATUS } from "../format";
import { Amount, DataTable, Field, Kpi, PageHeader, ReasonModal, StatusBadge, notifyError, useAction } from "../components/ui";
import { Attachments } from "./Customers";

export default function Payments() {
  const nav = useNavigate();
  const { can } = useAuth();
  const [sp] = useSearchParams();
  const [view, setView] = useState(sp.get("status") === "EN_PORTEFEUILLE" ? "portefeuille" : "tous");
  const [f, setF] = useState<any>({});
  const params = { ...f, date_from: iso(f.date_from), date_to: iso(f.date_to), limit: 2000,
    status: view === "portefeuille" ? "EN_PORTEFEUILLE,REMIS" : view === "rejets" ? "REJETE" : f.status, unallocated: view === "nonaffectes" || undefined };
  const { data, isLoading } = useQ<any>(["payments", params], `/payments${qs(params)}`);
  const rows = data?.rows || [];
  const sum = (k: string) => rows.filter((r: any) => !["REJETE", "ANNULE"].includes(r.status)).reduce((s: number, r: any) => s + Number(r[k]), 0);
  const set = (k: string) => (v: any) => setF((x: any) => ({ ...x, [k]: v?.currentTarget ? v.currentTarget.value : v || undefined }));
  return (
    <>
      <PageHeader title="Encaissements" subtitle="Règlements reçus, lettrage et portefeuille de chèques et effets"
                  actions={can("payments.write") && <Button leftSection={<IconPlus size={16} />} onClick={() => nav("/encaissements/nouveau")}>Saisir un règlement</Button>} />
      <SimpleGrid cols={{ base: 1, sm: 3 }} mb="md">
        <Kpi label="Total affiché (TND)" value={money(sum("amount_tnd"))} hint="Hors rejetés et annulés" />
        <Kpi label="Non affecté" value={money(rows.filter((r: any) => r.currency === "TND").reduce((s: number, r: any) => s + Number(r.unallocated_amount), 0))} hint="Avances et règlements à lettrer" />
        <Kpi label="Nombre de règlements" value={rows.length} />
      </SimpleGrid>
      <Card withBorder radius="md">
        <Group mb="sm" justify="space-between" wrap="wrap">
          <SegmentedControl value={view} onChange={setView} data={[{ value: "tous", label: "Tous" }, { value: "portefeuille", label: "Chèques / effets à encaisser" },
            { value: "nonaffectes", label: "Non affectés" }, { value: "rejets", label: "Rejets" }]} />
          <Group gap="xs">
            <TextInput placeholder="N°, référence, client…" value={f.q || ""} onChange={set("q")} w={200} />
            <Select placeholder="Moyen" data={[["ESPECES", "Espèces"], ["CHEQUE", "Chèque"], ["VIREMENT", "Virement"], ["EFFET", "Effet"], ["RETENUE_SOURCE", "Retenue à la source"]].map(([value, label]) => ({ value, label }))}
                    value={f.method_kind || null} onChange={set("method_kind")} clearable w={150} />
            <DateInput placeholder="Du" value={f.date_from || null} onChange={set("date_from")} valueFormat="DD/MM/YYYY" clearable w={130} />
            <DateInput placeholder="Au" value={f.date_to || null} onChange={set("date_to")} valueFormat="DD/MM/YYYY" clearable w={130} />
          </Group>
        </Group>
        <DataTable rows={rows} loading={isLoading} onRowClick={(r) => nav(`/encaissements/${r.id}`)} columns={[
          { key: "number", label: "N°" }, { key: "receipt_date", label: "Reçu le", render: (r) => date(r.receipt_date) },
          { key: "customer_name", label: "Client" }, { key: "method_label", label: "Moyen" }, { key: "reference", label: "Référence" },
          { key: "value_date", label: "Date de valeur", render: (r) => date(r.value_date) },
          { key: "amount", label: "Montant", align: "right", render: (r) => <Amount v={r.amount} currency={r.currency !== "TND" ? r.currency : undefined} /> },
          { key: "unallocated_amount", label: "Non affecté", align: "right", render: (r) => (Number(r.unallocated_amount) ? <Amount v={r.unallocated_amount} color="orange.8" /> : "—") },
          { key: "status", label: "Statut", render: (r) => <StatusBadge code={r.status} label={PAYMENT_STATUS[r.status]} /> },
        ]} />
      </Card>
    </>
  );
}

export function PaymentForm() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const refs = useRefs();
  const customers = useQ<any>(["customers", "all-light"], "/customers?limit=2000&with_balance=false");
  const [customerId, setCustomerId] = useState<string | null>(sp.get("customer_id"));
  const [methodId, setMethodId] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<Date | null>(new Date());
  const [valueDate, setValueDate] = useState<Date | null>(null);
  const [amount, setAmount] = useState<number | string>("");
  const [currency, setCurrency] = useState("TND");
  const [rate, setRate] = useState<number | string>("");
  const [ref, setRef] = useState("");
  const [bank, setBank] = useState("");
  const [drawer, setDrawer] = useState("");
  const [notes, setNotes] = useState("");
  const [mode, setMode] = useState("auto");
  const [alloc, setAlloc] = useState<Record<number, number | string>>({});
  const open = useQ<any>(["open-invoices", customerId, currency], customerId ? `/customers/${customerId}/open-invoices?currency=${currency}` : null);
  const method = refs.methods.find((m) => String(m.id) === methodId);
  useEffect(() => {
    const c = (customers.data?.rows || []).find((x: any) => String(x.id) === customerId);
    if (c) setCurrency(c.currency || "TND");
  }, [customerId, customers.data]);
  useEffect(() => {
    const iid = sp.get("invoice_id");
    if (iid && open.data) {
      const inv = open.data.invoices.find((i: any) => String(i.id) === iid);
      if (inv) { setMode("manual"); setAlloc({ [inv.id]: inv.balance }); setAmount(inv.balance); }
    }
  }, [open.data, sp]);
  const allocTotal = useMemo(() => Object.values(alloc).reduce((s: number, v) => s + Number(v || 0), 0), [alloc]);
  const save = useAction((body: any) => api("/payments", { body }), (r) => `Règlement ${r.number} enregistré — ${money(r.allocated_amount)} affectés`, (r) => nav(`/encaissements/${r.id}`));
  const submit = () => {
    const body: any = { customer_id: Number(customerId), method_id: Number(methodId), receipt_date: iso(receipt), value_date: iso(valueDate), amount: String(amount),
      currency, exchange_rate: currency !== "TND" && rate ? String(rate) : null, reference: ref || null, bank_name: bank || null, drawer: drawer || null, notes: notes || null,
      auto_allocate: mode === "auto" };
    if (mode === "manual") body.allocations = Object.entries(alloc).filter(([, v]) => Number(v) > 0).map(([k, v]) => ({ invoice_id: Number(k), amount: String(v) }));
    if (mode === "none") body.auto_allocate = false;
    save.mutate(body);
  };
  const needsRef = method && ["CHEQUE", "EFFET", "RETENUE_SOURCE"].includes(method.kind);
  return (
    <>
      <PageHeader title="Saisie d'un règlement" subtitle="Le règlement est affecté aux factures dans la même opération ; les soldes, la balance âgée et le risque sont mis à jour immédiatement." />
      <Grid>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card withBorder radius="md">
            <Stack>
              <Select label="Client" required searchable data={(customers.data?.rows || []).map((c: any) => ({ value: String(c.id), label: `${c.code} – ${c.legal_name}` }))} value={customerId} onChange={setCustomerId} />
              <Select label="Moyen de paiement" required data={refs.methods.map((m) => ({ value: String(m.id), label: m.label }))} value={methodId} onChange={setMethodId} />
              <SimpleGrid cols={2}>
                <DateInput label="Date de réception" required value={receipt} onChange={setReceipt} valueFormat="DD/MM/YYYY" maxDate={new Date()} />
                <DateInput label={method?.kind === "EFFET" ? "Échéance de l'effet" : "Date de valeur prévue"} required={method?.kind === "EFFET"} value={valueDate} onChange={setValueDate} valueFormat="DD/MM/YYYY" />
                <NumberInput label="Montant" required decimalScale={3} min={0} thousandSeparator=" " decimalSeparator="," value={amount} onChange={setAmount} />
                <Select label="Devise" data={refs.currencies} value={currency} onChange={(v) => setCurrency(v || "TND")} />
                {currency !== "TND" && <NumberInput label="Cours du jour (TND)" description="Vide = cours enregistré" decimalScale={6} value={rate} onChange={setRate} />}
              </SimpleGrid>
              <SimpleGrid cols={2}>
                <TextInput label={method?.kind === "RETENUE_SOURCE" ? "N° du certificat" : "N° chèque / effet / référence"} required={!!needsRef} value={ref} onChange={(e) => setRef(e.currentTarget.value)} />
                <TextInput label="Banque" value={bank} onChange={(e) => setBank(e.currentTarget.value)} />
                <TextInput label="Tireur" value={drawer} onChange={(e) => setDrawer(e.currentTarget.value)} />
              </SimpleGrid>
              <Textarea label="Notes" value={notes} onChange={(e) => setNotes(e.currentTarget.value)} autosize />
              {method?.kind === "RETENUE_SOURCE" && <Alert color="blue">La retenue à la source opérée par le client est enregistrée comme un règlement justifié par le certificat ; conservez-le en pièce jointe.</Alert>}
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card withBorder radius="md">
            <Group justify="space-between" mb="sm">
              <Title order={5}>Affectation</Title>
              <SegmentedControl size="xs" value={mode} onChange={setMode} data={[{ value: "auto", label: "Automatique (plus ancienne échéance)" }, { value: "manual", label: "Manuelle" }, { value: "none", label: "Avance (sans affectation)" }]} />
            </Group>
            {!customerId && <Text c="dimmed" size="sm">Choisissez un client pour afficher ses factures ouvertes.</Text>}
            {open.data && (
              <>
                <Table fz="sm">
                  <Table.Thead><Table.Tr><Table.Th>Facture</Table.Th><Table.Th>Échéance</Table.Th><Table.Th ta="right">Reste dû</Table.Th><Table.Th>Statut</Table.Th>{mode === "manual" && <Table.Th w={150}>À affecter</Table.Th>}</Table.Tr></Table.Thead>
                  <Table.Tbody>{open.data.invoices.map((i: any) => (
                    <Table.Tr key={i.id}><Table.Td>{i.number}</Table.Td><Table.Td>{date(i.due_date)}</Table.Td><Table.Td ta="right"><Amount v={i.balance} /></Table.Td>
                      <Table.Td><StatusBadge code={i.status} label={i.status_label} /></Table.Td>
                      {mode === "manual" && <Table.Td><Group gap={4} wrap="nowrap"><NumberInput size="xs" decimalScale={3} min={0} max={Number(i.balance)} hideControls value={alloc[i.id] ?? ""}
                        onChange={(v) => setAlloc((a) => ({ ...a, [i.id]: v }))} /><Checkbox size="xs" checked={Number(alloc[i.id]) === Number(i.balance)} onChange={(e) => setAlloc((a) => ({ ...a, [i.id]: e.currentTarget.checked ? i.balance : "" }))} /></Group></Table.Td>}
                    </Table.Tr>))}
                    {!open.data.invoices.length && <Table.Tr><Table.Td colSpan={5}><Text size="sm" c="dimmed">Aucune facture ouverte en {currency} : le règlement sera enregistré comme avance.</Text></Table.Td></Table.Tr>}
                  </Table.Tbody>
                </Table>
                {mode === "manual" && <Text size="sm" mt="xs" c={allocTotal > Number(amount || 0) ? "red" : undefined}>Total affecté : {money(allocTotal)} / {money(amount || 0)} — reste en avance : {money(Math.max(0, Number(amount || 0) - allocTotal))}</Text>}
                {mode === "auto" && <Text size="xs" c="dimmed" mt="xs">Les factures litigieuses sont exclues de l'affectation automatique (paramétrable).</Text>}
              </>
            )}
          </Card>
        </Grid.Col>
      </Grid>
      <Group justify="flex-end" mt="md">
        <Button variant="default" onClick={() => nav(-1)}>Annuler</Button>
        <Button onClick={submit} loading={save.isPending} disabled={!customerId || !methodId || !amount || (mode === "manual" && allocTotal > Number(amount))}>Enregistrer le règlement</Button>
      </Group>
    </>
  );
}

export function PaymentDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const { data: p } = useQ<any>(["payment", id], `/payments/${id}`);
  const open = useQ<any>(["open-invoices", p?.customer_id, p?.currency], p ? `/customers/${p.customer_id}/open-invoices?currency=${p.currency}` : null);
  const [statusModal, setStatusModal] = useState<string | null>(null);
  const [sDate, setSDate] = useState<Date | null>(new Date());
  const [reason, setReason] = useState("");
  const [cancel, setCancel] = useState(false);
  const [rev, setRev] = useState<number | null>(null);
  const [alloc, setAlloc] = useState<Record<number, number | string>>({});
  const chg = useAction(() => api(`/payments/${id}/status`, { body: { status: statusModal, date: iso(sDate), reason: reason || null } }), "Statut mis à jour", () => { setStatusModal(null); setReason(""); });
  const cancelReq = useAction((r: string) => api(`/payments/${id}/cancel-request`, { body: { reason: r } }), "Demande d'annulation transmise pour validation", () => setCancel(false));
  const reverse = useAction((r: string) => api(`/allocations/${rev}/reverse`, { body: { reason: r } }), "Affectation annulée", () => setRev(null));
  const auto = useAction(() => api(`/payments/${id}/auto-allocate`, { method: "POST" }), "Affectation automatique effectuée");
  const manual = useAction(() => api(`/payments/${id}/allocate`, { body: { allocations: Object.entries(alloc).filter(([, v]) => Number(v) > 0).map(([k, v]) => ({ invoice_id: Number(k), amount: String(v) })) } }),
    "Affectation enregistrée", () => setAlloc({}));
  if (!p) return <Text>Chargement…</Text>;
  const active = !["REJETE", "ANNULE"].includes(p.status);
  const transitions: Record<string, string[]> = { EN_PORTEFEUILLE: ["REMIS", "ENCAISSE", "REJETE"], REMIS: ["ENCAISSE", "REJETE"], ENCAISSE: ["REJETE"] };
  const labels: Record<string, string> = { REMIS: "Remis en banque", ENCAISSE: "Encaissé", REJETE: "Rejeté (impayé)" };
  return (
    <>
      <PageHeader title={`Règlement ${p.number}`} subtitle={<Group gap="xs"><Text size="sm" c="dimmed" style={{ cursor: "pointer" }} onClick={() => nav(`/clients/${p.customer_id}`)}>{p.customer_code} · {p.customer_name}</Text>
        <StatusBadge code={p.status} label={PAYMENT_STATUS[p.status]} /></Group>}
        actions={<>
          <Button variant="default" leftSection={<IconReceipt size={16} />} onClick={() => download(`/payments/${id}/receipt`).catch(notifyError)}>Reçu PDF</Button>
          {can("payments.status") && ["CHEQUE", "EFFET"].includes(p.method_kind) && (transitions[p.status] || []).map((s) => (
            <Button key={s} variant={s === "REJETE" ? "light" : "filled"} color={s === "REJETE" ? "red" : undefined} onClick={() => setStatusModal(s)}>{labels[s]}</Button>))}
          {can("payments.write") && active && <Button variant="subtle" color="red" onClick={() => setCancel(true)}>Demander l'annulation</Button>}
        </>} />
      <Grid>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Card withBorder radius="md" mb="md">
            <SimpleGrid cols={2} spacing="sm">
              <Field label="Montant"><Amount v={p.amount} currency={p.currency} strong /></Field><Field label="Contre-valeur TND"><Amount v={p.amount_tnd} /></Field>
              <Field label="Moyen">{p.method_label}</Field><Field label="Référence">{p.reference}</Field>
              <Field label="Banque">{p.bank_name}</Field><Field label="Tireur">{p.drawer}</Field>
              <Field label="Reçu le">{date(p.receipt_date)}</Field><Field label="Date de valeur">{date(p.value_date)}</Field>
              <Field label="Remis le">{date(p.deposited_date)}</Field><Field label="Encaissé le">{date(p.cleared_date)}</Field>
              <Field label="Affecté"><Amount v={p.allocated_amount} /></Field><Field label="Non affecté"><Amount v={p.unallocated_amount} color="orange.8" /></Field>
            </SimpleGrid>
            {p.rejected_date && <Alert color="red" mt="md" title={`Rejeté le ${date(p.rejected_date)}`}>{p.rejection_reason}</Alert>}
            {p.cancelled_date && <Alert color="gray" mt="md" title={`Annulé le ${date(p.cancelled_date)}`}>{p.cancel_reason}</Alert>}
            {p.notes && <Text size="sm" mt="sm" c="dimmed">{p.notes}</Text>}
          </Card>
          <Card withBorder radius="md"><Title order={6} mb="xs">Pièces justificatives</Title><Attachments entityType="payment" entityId={p.id} canWrite={can("payments.write")} /></Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Card withBorder radius="md" mb="md">
            <Title order={5} mb="sm">Affectations</Title>
            <Table fz="sm"><Table.Thead><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Facture</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th ta="right">Écart de change</Table.Th><Table.Th>État</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>{p.allocations.map((a: any) => <Table.Tr key={a.id} style={{ opacity: a.reversed ? 0.55 : 1 }}><Table.Td>{date(a.date)}</Table.Td>
                <Table.Td style={{ cursor: "pointer" }} onClick={() => nav(`/factures/${a.invoice_id}`)}>{a.invoice_number} / éch. {a.installment_seq}</Table.Td>
                <Table.Td ta="right"><Amount v={a.amount} /></Table.Td><Table.Td ta="right">{Number(a.fx_difference_tnd) ? <Amount v={a.fx_difference_tnd} /> : "—"}</Table.Td>
                <Table.Td>{a.reversed ? <Text size="xs" c="red">annulée le {date(a.reversed_date)} : {a.reversal_reason}</Text> : "active"}</Table.Td>
                <Table.Td>{!a.reversed && can("allocations.write") && <Button size="compact-xs" variant="subtle" color="red" onClick={() => setRev(a.id)}>Délettrer</Button>}</Table.Td></Table.Tr>)}
                {!p.allocations.length && <Table.Tr><Table.Td colSpan={6}><Text size="sm" c="dimmed">Aucune affectation.</Text></Table.Td></Table.Tr>}</Table.Tbody></Table>
          </Card>
          {active && Number(p.unallocated_amount) > 0 && can("allocations.write") && open.data && (
            <Card withBorder radius="md">
              <Group justify="space-between" mb="sm"><Title order={5}>Affecter le solde ({money(p.unallocated_amount)})</Title>
                <Button size="xs" variant="light" onClick={() => auto.mutate(undefined)} loading={auto.isPending}>Affectation automatique</Button></Group>
              <Table fz="sm"><Table.Tbody>{open.data.invoices.map((i: any) => <Table.Tr key={i.id}><Table.Td>{i.number}</Table.Td><Table.Td>{date(i.due_date)}</Table.Td>
                <Table.Td ta="right"><Amount v={i.balance} /></Table.Td><Table.Td w={160}><NumberInput size="xs" decimalScale={3} min={0} hideControls value={alloc[i.id] ?? ""} onChange={(v) => setAlloc((a) => ({ ...a, [i.id]: v }))} /></Table.Td></Table.Tr>)}</Table.Tbody></Table>
              <Group justify="flex-end" mt="sm"><Button size="xs" onClick={() => manual.mutate(undefined)} loading={manual.isPending}>Affecter</Button></Group>
            </Card>)}
        </Grid.Col>
      </Grid>
      <Modal opened={!!statusModal} onClose={() => setStatusModal(null)} title={labels[statusModal || ""] || ""}>
        <Stack>
          <DateInput label="Date" value={sDate} onChange={setSDate} valueFormat="DD/MM/YYYY" />
          {statusModal === "REJETE" && <><Textarea label="Motif du rejet" value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
            <Alert color="red">Les affectations seront annulées : les factures redeviennent dues et l'incident est pris en compte dans la notation du client.</Alert></>}
          <Group justify="flex-end"><Button onClick={() => chg.mutate(undefined)} loading={chg.isPending} disabled={statusModal === "REJETE" && reason.length < 3}>Confirmer</Button></Group>
        </Stack>
      </Modal>
      <ReasonModal opened={cancel} onClose={() => setCancel(false)} title="Annulation du règlement (erreur de saisie)" color="red" confirm="Transmettre" onSubmit={(r) => cancelReq.mutate(r)} loading={cancelReq.isPending}>
        <Text size="sm">L'annulation est soumise à validation. Le règlement n'est jamais supprimé : il est contre-passé et reste visible dans l'historique.</Text>
      </ReasonModal>
      <ReasonModal opened={!!rev} onClose={() => setRev(null)} title="Annuler cette affectation" color="red" onSubmit={(r) => reverse.mutate(r)} loading={reverse.isPending} />
    </>
  );
}
