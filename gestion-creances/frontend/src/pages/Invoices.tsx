import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ActionIcon, Alert, Button, Card, Checkbox, Divider, Grid, Group, Menu, Modal, MultiSelect, NumberInput, Select, SimpleGrid, Stack, Table, Text,
  TextInput, Textarea, Title,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconAlertTriangle, IconDots, IconFileTypePdf, IconPlus, IconTrash } from "@tabler/icons-react";
import dayjs from "dayjs";
import { api, download, qs } from "../api";
import { useAuth } from "../auth";
import { useQ, useRefs } from "../hooks";
import { CLASSIFICATIONS, date, iso, money } from "../format";
import { Amount, Col, DataTable, Field, PageHeader, ReasonModal, StatusBadge, notifyError, useAction } from "../components/ui";
import { Attachments } from "./Customers";

const STATUSES = [
  ["BROUILLON", "Brouillon"], ["NON_ECHUE", "Non échue"], ["PARTIELLEMENT_REGLEE", "Partiellement réglée"], ["EN_RETARD", "En retard"],
  ["REGLEE", "Réglée"], ["LITIGIEUSE", "Litigieuse"], ["DOUTEUSE", "Douteuse"], ["IRRECOUVRABLE", "Irrécouvrable"], ["OUVERTE", "Toutes les factures ouvertes"],
].map(([value, label]) => ({ value, label }));

export const invoiceCols: Col<any>[] = [
  { key: "number", label: "N°", render: (r) => r.number || <Text size="sm" c="dimmed">brouillon #{r.id}</Text> },
  { key: "doc_type", label: "Type", render: (r) => (r.doc_type === "AVOIR" ? "Avoir" : "Facture") },
  { key: "customer_name", label: "Client" },
  { key: "issue_date", label: "Date", render: (r) => date(r.issue_date) },
  { key: "due_date", label: "Échéance", render: (r) => date(r.due_date) },
  { key: "total_ttc", label: "TTC", align: "right", render: (r) => <Amount v={r.total_ttc} currency={r.currency !== "TND" ? r.currency : undefined} /> },
  { key: "balance", label: "Reste dû", align: "right", render: (r) => <Amount v={r.balance} strong /> },
  { key: "days_overdue", label: "Retard", align: "right", render: (r) => (r.days_overdue ? `${r.days_overdue} j` : "—") },
  { key: "status", label: "Statut", render: (r) => <StatusBadge code={r.status} label={r.status_label} /> },
];

export default function Invoices() {
  const nav = useNavigate();
  const { can } = useAuth();
  const [sp] = useSearchParams();
  const [f, setF] = useState<any>({ status: sp.get("status") || undefined });
  const params = { ...f, date_from: iso(f.date_from), date_to: iso(f.date_to), limit: 2000 };
  const { data, isLoading } = useQ<any>(["invoices", params], `/invoices${qs(params)}`);
  const set = (k: string) => (v: any) => setF((x: any) => ({ ...x, [k]: v?.currentTarget ? v.currentTarget.value : v || undefined }));
  const total = (data?.rows || []).reduce((s: number, r: any) => s + Number(r.balance_tnd || 0), 0);
  return (
    <>
      <PageHeader title="Factures et avoirs" subtitle={`${data?.total ?? "…"} pièce(s) · reste dû affiché : ${money(total)} TND`}
                  actions={can("invoices.write") && <>
                    <Button variant="default" onClick={() => nav("/factures/nouvelle?type=AVOIR")}>Nouvel avoir</Button>
                    <Button leftSection={<IconPlus size={16} />} onClick={() => nav("/factures/nouvelle")}>Nouvelle facture</Button></>} />
      <Card withBorder radius="md">
        <Group mb="sm" gap="xs" wrap="wrap" align="flex-end">
          <TextInput placeholder="N°, client, référence…" value={f.q || ""} onChange={set("q")} w={220} />
          <Select placeholder="Statut" data={STATUSES} value={f.status || null} onChange={set("status")} clearable w={190} />
          <Select placeholder="Type" data={[{ value: "FACTURE", label: "Factures" }, { value: "AVOIR", label: "Avoirs" }]} value={f.doc_type || null} onChange={set("doc_type")} clearable w={120} />
          <Select placeholder="Devise" data={["TND", "EUR", "USD"]} value={f.currency || null} onChange={set("currency")} clearable w={100} />
          <DateInput placeholder="Du" value={f.date_from || null} onChange={set("date_from")} valueFormat="DD/MM/YYYY" clearable w={130} />
          <DateInput placeholder="Au" value={f.date_to || null} onChange={set("date_to")} valueFormat="DD/MM/YYYY" clearable w={130} />
          <Select placeholder="Origine" data={[{ value: "SAISIE", label: "Saisie" }, { value: "IMPORT", label: "Import" }]} value={f.source || null} onChange={set("source")} clearable w={110} />
        </Group>
        <DataTable rows={data?.rows || []} columns={invoiceCols} loading={isLoading} onRowClick={(r) => nav(`/factures/${r.id}`)} />
      </Card>
    </>
  );
}

type Line = { description: string; quantity: number | string; unit_price: number | string; discount_pct: number | string; vat_code: string };

export function InvoiceForm() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const refs = useRefs();
  const existing = useQ<any>(["invoice", id], id ? `/invoices/${id}` : null);
  const customers = useQ<any>(["customers", "all-light"], "/customers?limit=2000&with_balance=false");
  const [docType, setDocType] = useState(sp.get("type") || "FACTURE");
  const [customerId, setCustomerId] = useState<string | null>(sp.get("customer_id"));
  const [issue, setIssue] = useState<Date | null>(new Date());
  const [due, setDue] = useState<Date | null>(null);
  const [currency, setCurrency] = useState("TND");
  const [rate, setRate] = useState<string | number>("");
  const [ext, setExt] = useState("");
  const [order, setOrder] = useState("");
  const [notes, setNotes] = useState("");
  const [related, setRelated] = useState<string | null>(sp.get("related"));
  const [stamp, setStamp] = useState(true);
  const [others, setOthers] = useState<string[]>([]);
  const [lines, setLines] = useState<Line[]>([{ description: "", quantity: 1, unit_price: "", discount_pct: 0, vat_code: "TVA19" }]);
  const [multi, setMulti] = useState(false);
  const [inst, setInst] = useState<{ due_date: Date | null; amount: number | string }[]>([]);
  const cust = (customers.data?.rows || []).find((c: any) => String(c.id) === customerId);
  const relatedInv = useQ<any>(["invoices", "related", customerId], customerId && docType === "AVOIR" ? `/invoices?customer_id=${customerId}&doc_type=FACTURE&limit=500` : null);

  useEffect(() => {
    const e = existing.data;
    if (!e) return;
    setDocType(e.doc_type); setCustomerId(String(e.customer_id)); setIssue(new Date(e.issue_date)); setDue(new Date(e.due_date));
    setCurrency(e.currency); setRate(e.exchange_rate); setExt(e.external_ref || ""); setOrder(e.order_ref || ""); setNotes(e.notes || "");
    setRelated(e.related_invoice_id ? String(e.related_invoice_id) : null);
    setStamp(e.taxes.some((t: any) => t.kind === "TIMBRE"));
    setOthers(e.taxes.filter((t: any) => t.kind === "AUTRE").map((t: any) => t.code));
    setLines(e.lines.map((l: any) => ({ description: l.description, quantity: l.quantity, unit_price: l.unit_price, discount_pct: l.discount_pct, vat_code: l.vat_code })));
    if (e.installments.length > 1) { setMulti(true); setInst(e.installments.map((i: any) => ({ due_date: new Date(i.due_date), amount: i.amount }))); }
  }, [existing.data]);
  useEffect(() => {
    if (cust && !id) {
      setCurrency(cust.currency || "TND");
      setDue(dayjs(issue || new Date()).add(cust.payment_terms_days || 30, "day").toDate());
    }
  }, [customerId]); // eslint-disable-line
  useEffect(() => { if (docType === "AVOIR" && !id) setStamp(false); }, [docType, id]);

  // Aperçu des totaux (le calcul de référence est fait par le serveur)
  const preview = useMemo(() => {
    let ht = 0;
    const vat: Record<string, number> = {};
    const r3 = (x: number) => Math.round(x * 1000) / 1000;
    lines.forEach((l) => {
      const h = r3(Number(l.quantity || 0) * Number(l.unit_price || 0) * (1 - Number(l.discount_pct || 0) / 100));
      ht += h;
      vat[l.vat_code] = (vat[l.vat_code] || 0) + h;
    });
    const otherRates = others.map((c) => refs.taxes.find((t) => t.code === c)).filter(Boolean);
    const inBase = otherRates.filter((t: any) => t.in_vat_base).reduce((s: number, t: any) => s + Number(t.rate || 0), 0);
    const oth = otherRates.reduce((s: number, t: any) => s + (t.rate ? r3((ht * Number(t.rate)) / 100) : Number(t.fixed_amount || 0)), 0);
    const tva = Object.entries(vat).reduce((s, [code, base]) => {
      const t = refs.taxes.find((x) => x.code === code);
      return s + r3(r3(base * (1 + inBase / 100)) * Number(t?.rate || 0) / 100);
    }, 0);
    const st = stamp ? Number(refs.taxes.find((t) => t.code === "TIMBRE")?.fixed_amount || 0) : 0;
    return { ht: r3(ht), tva: r3(tva), oth: r3(oth + st), ttc: r3(ht + tva + oth + st) };
  }, [lines, others, stamp, refs.taxes]);

  const save = useAction((body: any) => (id ? api(`/invoices/${id}`, { method: "PUT", body }) : api("/invoices", { body })), "Brouillon enregistré",
    (r) => nav(`/factures/${r.id}`));
  const submit = () => {
    const body: any = {
      doc_type: docType, customer_id: Number(customerId), issue_date: iso(issue), due_date: iso(due), currency,
      exchange_rate: currency !== "TND" && rate ? String(rate) : null, external_ref: ext || null, order_ref: order || null, notes: notes || null,
      related_invoice_id: related ? Number(related) : null, apply_stamp: stamp, other_taxes: others,
      lines: lines.map((l) => ({ description: l.description || "-", quantity: String(l.quantity || 0), unit_price: String(l.unit_price || 0),
        discount_pct: String(l.discount_pct || 0), vat_code: l.vat_code })),
    };
    if (docType === "FACTURE" && multi && inst.length) body.installments = inst.map((i) => ({ due_date: iso(i.due_date), amount: String(i.amount) }));
    save.mutate(body);
  };
  const setLine = (i: number, k: keyof Line, v: any) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const instTotal = inst.reduce((s, i) => s + Number(i.amount || 0), 0);
  return (
    <>
      <PageHeader title={id ? "Modifier le brouillon" : docType === "AVOIR" ? "Nouvel avoir" : "Nouvelle facture"}
                  subtitle="Le numéro définitif est attribué à la validation ; une pièce validée n'est plus modifiable." />
      <Card withBorder radius="md" mb="md">
        <Grid>
          <Grid.Col span={{ base: 12, md: 3 }}><Select label="Type de pièce" data={[{ value: "FACTURE", label: "Facture" }, { value: "AVOIR", label: "Avoir" }]} value={docType} onChange={(v) => setDocType(v || "FACTURE")} disabled={!!id} /></Grid.Col>
          <Grid.Col span={{ base: 12, md: 5 }}><Select label="Client" required searchable data={(customers.data?.rows || []).filter((c: any) => c.status !== "ARCHIVE").map((c: any) => ({ value: String(c.id), label: `${c.code} – ${c.legal_name}` }))}
                                                       value={customerId} onChange={setCustomerId} /></Grid.Col>
          <Grid.Col span={{ base: 6, md: 2 }}><DateInput label="Date" required value={issue} onChange={setIssue} valueFormat="DD/MM/YYYY" /></Grid.Col>
          <Grid.Col span={{ base: 6, md: 2 }}><DateInput label="Échéance" value={due} onChange={setDue} valueFormat="DD/MM/YYYY" minDate={issue || undefined} /></Grid.Col>
          <Grid.Col span={{ base: 6, md: 2 }}><Select label="Devise" data={refs.currencies} value={currency} onChange={(v) => setCurrency(v || "TND")} /></Grid.Col>
          {currency !== "TND" && <Grid.Col span={{ base: 6, md: 2 }}><NumberInput label="Cours (TND)" description="Vide = cours enregistré" decimalScale={6} value={rate} onChange={setRate} /></Grid.Col>}
          <Grid.Col span={{ base: 6, md: 2 }}><TextInput label="Référence externe" value={ext} onChange={(e) => setExt(e.currentTarget.value)} /></Grid.Col>
          <Grid.Col span={{ base: 6, md: 2 }}><TextInput label="Bon de commande" value={order} onChange={(e) => setOrder(e.currentTarget.value)} /></Grid.Col>
          {docType === "AVOIR" && <Grid.Col span={{ base: 12, md: 4 }}><Select label="Facture d'origine (imputation automatique)" clearable searchable
              data={(relatedInv.data?.rows || []).filter((r: any) => r.lifecycle === "VALIDEE").map((r: any) => ({ value: String(r.id), label: `${r.number} – reste ${money(r.balance)}` }))}
              value={related} onChange={setRelated} /></Grid.Col>}
        </Grid>
        {cust && Number(cust.credit_limit) > 0 && docType === "FACTURE" && Number(cust.open_tnd || 0) + preview.ttc > Number(cust.credit_limit) && (
          <Alert color="orange" mt="sm" icon={<IconAlertTriangle size={16} />}>Cette facture porterait l'encours au-delà du plafond de crédit du client.</Alert>)}
      </Card>
      <Card withBorder radius="md" mb="md">
        <Title order={5} mb="sm">Lignes</Title>
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Désignation</Table.Th><Table.Th w={90}>Qté</Table.Th><Table.Th w={140}>P.U. HT</Table.Th><Table.Th w={90}>Remise %</Table.Th><Table.Th w={170}>TVA</Table.Th><Table.Th w={130} ta="right">Total HT</Table.Th><Table.Th w={40} /></Table.Tr></Table.Thead>
          <Table.Tbody>{lines.map((l, i) => (
            <Table.Tr key={i}>
              <Table.Td><TextInput value={l.description} onChange={(e) => setLine(i, "description", e.currentTarget.value)} /></Table.Td>
              <Table.Td><NumberInput value={l.quantity} onChange={(v) => setLine(i, "quantity", v)} decimalScale={3} min={0} hideControls /></Table.Td>
              <Table.Td><NumberInput value={l.unit_price} onChange={(v) => setLine(i, "unit_price", v)} decimalScale={3} min={0} hideControls thousandSeparator=" " decimalSeparator="," /></Table.Td>
              <Table.Td><NumberInput value={l.discount_pct} onChange={(v) => setLine(i, "discount_pct", v)} min={0} max={100} hideControls /></Table.Td>
              <Table.Td><Select data={refs.vatOptions} value={l.vat_code} onChange={(v) => setLine(i, "vat_code", v || "TVA19")} /></Table.Td>
              <Table.Td ta="right"><Amount v={Number(l.quantity || 0) * Number(l.unit_price || 0) * (1 - Number(l.discount_pct || 0) / 100)} /></Table.Td>
              <Table.Td><ActionIcon variant="subtle" color="red" disabled={lines.length === 1} onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}><IconTrash size={16} /></ActionIcon></Table.Td>
            </Table.Tr>))}
          </Table.Tbody>
        </Table>
        <Button variant="subtle" mt="xs" leftSection={<IconPlus size={14} />} onClick={() => setLines((ls) => [...ls, { description: "", quantity: 1, unit_price: "", discount_pct: 0, vat_code: "TVA19" }])}>Ajouter une ligne</Button>
        <Divider my="md" />
        <Grid>
          <Grid.Col span={{ base: 12, md: 6 }}>
            <Stack gap="xs">
              <MultiSelect label="Autres taxes (ex. FODEC)" data={refs.otherTaxOptions} value={others} onChange={setOthers} clearable />
              <Checkbox label="Appliquer le droit de timbre" checked={stamp} onChange={(e) => setStamp(e.currentTarget.checked)} />
              <Textarea label="Notes" value={notes} onChange={(e) => setNotes(e.currentTarget.value)} autosize />
            </Stack>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 6 }}>
            <Card bg="gray.0" radius="md">
              <Group justify="space-between"><Text>Total HT</Text><Amount v={preview.ht} /></Group>
              <Group justify="space-between"><Text>TVA</Text><Amount v={preview.tva} /></Group>
              <Group justify="space-between"><Text>Timbre et autres taxes</Text><Amount v={preview.oth} /></Group>
              <Divider my={6} />
              <Group justify="space-between"><Text fw={700}>Total TTC ({currency})</Text><Amount v={preview.ttc} strong /></Group>
              <Text size="xs" c="dimmed" mt={4}>Aperçu : le calcul définitif (taux en vigueur à la date de la pièce) est effectué par le serveur.</Text>
            </Card>
          </Grid.Col>
        </Grid>
      </Card>
      {docType === "FACTURE" && (
        <Card withBorder radius="md" mb="md">
          <Checkbox label="Paiement en plusieurs échéances" checked={multi} onChange={(e) => {
            setMulti(e.currentTarget.checked);
            if (e.currentTarget.checked && !inst.length) setInst([{ due_date: due, amount: (preview.ttc / 2).toFixed(3) }, { due_date: dayjs(due || new Date()).add(30, "day").toDate(), amount: (preview.ttc - Number((preview.ttc / 2).toFixed(3))).toFixed(3) }]);
          }} />
          {multi && (
            <Stack mt="sm" gap="xs">
              {inst.map((x, i) => (
                <Group key={i}>
                  <DateInput value={x.due_date} onChange={(v) => setInst((s) => s.map((y, j) => (j === i ? { ...y, due_date: v } : y)))} valueFormat="DD/MM/YYYY" w={150} />
                  <NumberInput value={x.amount} onChange={(v) => setInst((s) => s.map((y, j) => (j === i ? { ...y, amount: v } : y)))} decimalScale={3} w={160} hideControls />
                  <ActionIcon color="red" variant="subtle" onClick={() => setInst((s) => s.filter((_, j) => j !== i))}><IconTrash size={16} /></ActionIcon>
                </Group>))}
              <Group><Button size="xs" variant="subtle" onClick={() => setInst((s) => [...s, { due_date: due, amount: 0 }])}>Ajouter une échéance</Button>
                <Text size="sm" c={Math.abs(instTotal - preview.ttc) > 0.0005 ? "red" : "teal"}>Total des échéances : {money(instTotal)} / {money(preview.ttc)}</Text></Group>
            </Stack>
          )}
        </Card>
      )}
      <Group justify="flex-end">
        <Button variant="default" onClick={() => nav(-1)}>Annuler</Button>
        <Button onClick={submit} loading={save.isPending} disabled={!customerId || !issue}>Enregistrer le brouillon</Button>
      </Group>
    </>
  );
}

export function InvoiceDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const { data: inv } = useQ<any>(["invoice", id], `/invoices/${id}`);
  const [classify, setClassify] = useState<string | null>(null);
  const [wo, setWo] = useState(false);
  const [diff, setDiff] = useState(false);
  const [warn, setWarn] = useState<string[]>([]);
  const [rev, setRev] = useState<number | null>(null);
  const validate = useAction((force: boolean) => api(`/invoices/${id}/validate${force ? "?force=true" : ""}`, { method: "POST" }), (r) => `Pièce validée sous le n° ${r.number}`,
    (r) => setWarn(r.warnings || []));
  const del = useAction(() => api(`/invoices/${id}`, { method: "DELETE" }), "Brouillon supprimé", () => nav("/factures"));
  const cls = useAction((reason: string) => api(`/invoices/${id}/classify`, { body: { classification: classify, reason } }), "Classement enregistré", () => setClassify(null));
  const woReq = useAction((reason: string) => api(`/invoices/${id}/write-off-request`, { body: { reason } }), (r) => r.message, () => setWo(false));
  const settle = useAction((reason: string) => api(`/invoices/${id}/settle-difference`, { body: { reason } }), "Écart soldé", () => setDiff(false));
  const reverse = useAction((reason: string) => api(`/allocations/${rev}/reverse`, { body: { reason } }), "Affectation annulée", () => setRev(null));
  if (!inv) return <Text>Chargement…</Text>;
  const draft = inv.lifecycle === "BROUILLON";
  return (
    <>
      <PageHeader title={`${inv.doc_type === "AVOIR" ? "Avoir" : "Facture"} ${inv.number || "(brouillon)"}`}
        subtitle={<Group gap="xs"><Text size="sm" c="dimmed" style={{ cursor: "pointer" }} onClick={() => nav(`/clients/${inv.customer_id}`)}>{inv.customer_code} · {inv.customer_name}</Text>
          <StatusBadge code={inv.status} label={inv.status_label} />{inv.classification !== "NORMALE" && <StatusBadge code={inv.classification} label={CLASSIFICATIONS[inv.classification]} />}
          {inv.source === "IMPORT" && <StatusBadge code="VALIDEE" label="importée" />}</Group>}
        actions={<>
          <Button variant="default" leftSection={<IconFileTypePdf size={16} />} onClick={() => download(`/invoices/${id}/pdf`).catch(notifyError)}>PDF</Button>
          {draft && can("invoices.write") && <Button variant="default" onClick={() => nav(`/factures/${id}/modifier`)}>Modifier</Button>}
          {draft && can("invoices.write") && <Button variant="default" color="red" onClick={() => del.mutate(undefined)}>Supprimer</Button>}
          {draft && can("invoices.validate") && <Button onClick={() => validate.mutate(false)} loading={validate.isPending}>Valider</Button>}
          {draft && can("customers.credit_limit") && <Button color="orange" variant="light" onClick={() => validate.mutate(true)}>Valider (dérogation DAF)</Button>}
          {!draft && inv.doc_type === "FACTURE" && (
            <Menu position="bottom-end">
              <Menu.Target><Button rightSection={<IconDots size={16} />}>Actions</Button></Menu.Target>
              <Menu.Dropdown>
                {can("payments.write") && Number(inv.balance) > 0 && <Menu.Item onClick={() => nav(`/encaissements/nouveau?customer_id=${inv.customer_id}&invoice_id=${inv.id}`)}>Saisir un règlement</Menu.Item>}
                {can("invoices.write") && <Menu.Item onClick={() => nav(`/factures/nouvelle?type=AVOIR&customer_id=${inv.customer_id}&related=${inv.id}`)}>Émettre un avoir</Menu.Item>}
                {can("invoices.classify") && Number(inv.balance) > 0 && <>
                  <Menu.Divider /><Menu.Label>Classement</Menu.Label>
                  {inv.classification !== "LITIGIEUSE" && <Menu.Item onClick={() => setClassify("LITIGIEUSE")}>Classer en litigieuse</Menu.Item>}
                  {inv.classification !== "DOUTEUSE" && <Menu.Item onClick={() => setClassify("DOUTEUSE")}>Classer en douteuse</Menu.Item>}
                  {inv.classification !== "NORMALE" && <Menu.Item onClick={() => setClassify("NORMALE")}>Revenir en créance normale</Menu.Item>}
                  <Menu.Item color="red" onClick={() => setWo(true)}>Demander le passage en perte</Menu.Item></>}
                {can("adjustments.write") && Number(inv.balance) > 0 && <Menu.Item onClick={() => setDiff(true)}>Solder un écart de règlement</Menu.Item>}
              </Menu.Dropdown>
            </Menu>)}
        </>} />
      {warn.map((w, i) => <Alert key={i} color="orange" mb="xs" icon={<IconAlertTriangle size={16} />}>{w}</Alert>)}
      <Grid>
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Card withBorder radius="md" mb="md">
            <SimpleGrid cols={{ base: 2, sm: 4 }} mb="md">
              <Field label="Date">{date(inv.issue_date)}</Field><Field label="Échéance">{date(inv.due_date)}</Field>
              <Field label="Devise / cours">{inv.currency} {inv.currency !== "TND" && `(${inv.exchange_rate})`}</Field>
              <Field label="Référence externe">{inv.external_ref}</Field><Field label="Bon de commande">{inv.order_ref}</Field>
              <Field label="Origine">{inv.source}</Field><Field label="Validée le">{inv.validated_at ? date(inv.validated_at) : "—"}</Field>
              <Field label="Retard">{inv.days_overdue ? `${inv.days_overdue} jours` : "—"}</Field>
            </SimpleGrid>
            <Table fz="sm">
              <Table.Thead><Table.Tr><Table.Th>Désignation</Table.Th><Table.Th ta="right">Qté</Table.Th><Table.Th ta="right">P.U. HT</Table.Th><Table.Th ta="right">Remise</Table.Th><Table.Th>TVA</Table.Th><Table.Th ta="right">Total HT</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{inv.lines.map((l: any) => <Table.Tr key={l.id}><Table.Td>{l.description}</Table.Td><Table.Td ta="right">{Number(l.quantity)}</Table.Td>
                <Table.Td ta="right"><Amount v={l.unit_price} /></Table.Td><Table.Td ta="right">{Number(l.discount_pct)} %</Table.Td><Table.Td>{l.vat_code}</Table.Td><Table.Td ta="right"><Amount v={l.amount_ht} /></Table.Td></Table.Tr>)}</Table.Tbody>
            </Table>
            {inv.classification_reason && <Alert mt="md" color="grape" title="Justification du classement">{inv.classification_reason}</Alert>}
            {inv.notes && <Text size="sm" mt="sm" c="dimmed">{inv.notes}</Text>}
          </Card>
          {inv.doc_type === "FACTURE" && (
            <Card withBorder radius="md" mb="md">
              <Title order={5} mb="sm">Échéances</Title>
              <Table fz="sm"><Table.Thead><Table.Tr><Table.Th>#</Table.Th><Table.Th>Échéance</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th ta="right">Réglé</Table.Th><Table.Th ta="right">Reste dû</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{inv.installments.map((i: any) => <Table.Tr key={i.id}><Table.Td>{i.seq}</Table.Td><Table.Td>{date(i.due_date)}</Table.Td>
                  <Table.Td ta="right"><Amount v={i.amount} /></Table.Td><Table.Td ta="right"><Amount v={i.paid_amount} /></Table.Td><Table.Td ta="right"><Amount v={i.remaining} strong /></Table.Td></Table.Tr>)}</Table.Tbody></Table>
            </Card>)}
          <Card withBorder radius="md" mb="md">
            <Title order={5} mb="sm">Lettrage (affectations)</Title>
            <Table fz="sm"><Table.Thead><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Origine</Table.Th><Table.Th>Facture</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th ta="right">Écart de change</Table.Th><Table.Th>État</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>{inv.allocations.map((a: any) => <Table.Tr key={a.id} style={{ opacity: a.reversed ? 0.55 : 1 }}><Table.Td>{date(a.date)}</Table.Td><Table.Td>{a.source}</Table.Td><Table.Td>{a.invoice_number} / éch. {a.installment_seq}</Table.Td>
                <Table.Td ta="right"><Amount v={a.amount} /></Table.Td><Table.Td ta="right">{Number(a.fx_difference_tnd) ? <Amount v={a.fx_difference_tnd} /> : "—"}</Table.Td>
                <Table.Td>{a.reversed ? <Text size="xs" c="red">annulée le {date(a.reversed_date)} : {a.reversal_reason}</Text> : "active"}</Table.Td>
                <Table.Td>{!a.reversed && can("allocations.write") && !a.source.startsWith("OD") && <Button size="compact-xs" variant="subtle" color="red" onClick={() => setRev(a.id)}>Délettrer</Button>}</Table.Td></Table.Tr>)}
                {!inv.allocations.length && <Table.Tr><Table.Td colSpan={7}><Text size="sm" c="dimmed">Aucune affectation.</Text></Table.Td></Table.Tr>}</Table.Tbody></Table>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Card withBorder radius="md" mb="md">
            <Group justify="space-between"><Text>Total HT</Text><Amount v={inv.total_ht} /></Group>
            {inv.taxes.map((t: any) => <Group key={t.code} justify="space-between"><Text size="sm">{t.label}</Text><Amount v={t.amount} /></Group>)}
            <Divider my={6} />
            <Group justify="space-between"><Text fw={700}>Total TTC</Text><Amount v={inv.total_ttc} currency={inv.currency} strong /></Group>
            <Group justify="space-between"><Text size="sm">{inv.doc_type === "AVOIR" ? "Imputé" : "Réglé"}</Text><Amount v={inv.paid_amount} /></Group>
            <Group justify="space-between"><Text fw={700}>{inv.doc_type === "AVOIR" ? "Reste à imputer" : "Reste dû"}</Text><Amount v={inv.balance} strong color={Number(inv.balance) > 0 ? "orange.8" : "teal.8"} /></Group>
            {inv.currency !== "TND" && <Text size="xs" c="dimmed" mt={4}>Contre-valeur TTC : {money(inv.total_ttc_tnd)} TND</Text>}
          </Card>
          {inv.credit_notes.length > 0 && <Card withBorder radius="md" mb="md"><Title order={6} mb="xs">Avoirs liés</Title>
            {inv.credit_notes.map((c: any) => <Group key={c.id} justify="space-between" style={{ cursor: "pointer" }} onClick={() => nav(`/factures/${c.id}`)}><Text size="sm">{c.number || "brouillon"}</Text><Amount v={c.total_ttc} /></Group>)}</Card>}
          <Card withBorder radius="md"><Title order={6} mb="xs">Pièces justificatives</Title><Attachments entityType="invoice" entityId={inv.id} canWrite={can("invoices.write")} /></Card>
        </Grid.Col>
      </Grid>
      <ReasonModal opened={!!classify} onClose={() => setClassify(null)} title={`Classement : ${CLASSIFICATIONS[classify || "NORMALE"]}`} label="Justification (vérifiable, 10 caractères min.)"
                   onSubmit={(r) => cls.mutate(r)} loading={cls.isPending}>
        <Text size="sm">Le passage en douteuse ou litigieuse génère une écriture de reclassement proposée (compte clients douteux) et peut justifier une provision.</Text>
      </ReasonModal>
      <ReasonModal opened={wo} onClose={() => setWo(false)} title="Demande de passage en perte" color="red" confirm="Transmettre la demande" onSubmit={(r) => woReq.mutate(r)} loading={woReq.isPending}>
        <Alert color="red">Le reste dû ({money(inv.balance)} {inv.currency}) sera passé en perte après validation par une autre personne habilitée. Joignez les justificatifs (jugement, certificat d'irrécouvrabilité, PV de carence…).</Alert>
      </ReasonModal>
      <ReasonModal opened={diff} onClose={() => setDiff(false)} title="Solder un écart de règlement" onSubmit={(r) => settle.mutate(r)} loading={settle.isPending}>
        <Text size="sm">Uniquement pour un écart inférieur à la tolérance paramétrée (frais bancaires, arrondi).</Text>
      </ReasonModal>
      <ReasonModal opened={!!rev} onClose={() => setRev(null)} title="Annuler cette affectation" color="red" onSubmit={(r) => reverse.mutate(r)} loading={reverse.isPending} />
    </>
  );
}
