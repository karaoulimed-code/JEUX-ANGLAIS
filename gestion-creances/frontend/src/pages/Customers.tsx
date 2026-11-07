import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert, Badge, Button, Card, FileInput, Grid, Group, Modal, NumberInput, Progress, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput, Textarea, Title,
} from "@mantine/core";
import { IconAlertTriangle, IconFileUpload, IconPlus, IconEdit, IconLock } from "@tabler/icons-react";
import { api, download, qs } from "../api";
import { useAuth } from "../auth";
import { useQ, useRefs } from "../hooks";
import { date, datetime, money, pct, RISK_LABELS } from "../format";
import { Amount, Col, DataTable, ExportMenu, Field, Kpi, PageHeader, StatusBadge, notifyError, notifyOk, useAction } from "../components/ui";
import { RiskPanel } from "./Risk";

const EMPTY = {
  legal_name: "", trade_name: "", tax_id: "", rne_id: "", address: "", city: "", postal_code: "", country: "TN", phone: "", email: "", activity: "",
  category_code: null, sector_code: null, zone_code: null, group_code: null, salesperson_id: null, contact_name: "", contact_function: "",
  contact_phone: "", contact_email: "", bank_name: "", bank_rib: "", payment_terms_days: 30, payment_terms_label: "", currency: "TND",
  credit_limit: "0", max_exposure: "0", notes: "",
};

export function CustomerForm({ opened, onClose, initial }: { opened: boolean; onClose: () => void; initial?: any }) {
  const refs = useRefs();
  const { can } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState<any>(EMPTY);
  useEffect(() => {
    if (opened) setF(initial ? { ...EMPTY, ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, initial[k] ?? (EMPTY as any)[k]])), code: initial.code } : { ...EMPTY });
  }, [opened, initial]);
  const set = (k: string) => (v: any) => setF((x: any) => ({ ...x, [k]: v?.currentTarget ? v.currentTarget.value : v }));
  const save = useAction(
    (body: any) => (initial ? api(`/customers/${initial.id}`, { method: "PUT", body }) : api("/customers", { body })),
    (r) => (r.pending_approval ? "Fiche enregistrée. La modification du plafond est soumise à validation du directeur financier." : "Fiche client enregistrée"),
    (r) => { onClose(); if (!initial) nav(`/clients/${r.id}`); },
  );
  const submit = () => {
    const body: any = { ...f, salesperson_id: f.salesperson_id ? Number(f.salesperson_id) : null, credit_limit: String(f.credit_limit || 0),
      max_exposure: String(f.max_exposure || 0), payment_terms_days: Number(f.payment_terms_days || 0) };
    if (!initial) body.code = f.code || null;
    else delete body.code;
    Object.keys(body).forEach((k) => body[k] === "" && (body[k] = null));
    body.legal_name = f.legal_name;
    body.country = f.country || "TN";
    body.currency = f.currency || "TND";
    save.mutate(body);
  };
  const limitLocked = !can("customers.credit_limit") && !initial;
  return (
    <Modal opened={opened} onClose={onClose} title={initial ? `Modifier ${initial.code}` : "Nouveau client"} size="xl">
      <Tabs defaultValue="id">
        <Tabs.List mb="md">
          <Tabs.Tab value="id">Identification</Tabs.Tab><Tabs.Tab value="contact">Contacts</Tabs.Tab>
          <Tabs.Tab value="credit">Conditions et crédit</Tabs.Tab><Tabs.Tab value="class">Classification</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="id">
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            {!initial && <TextInput label="Code client" description="Laisser vide pour une numérotation automatique" value={f.code || ""} onChange={set("code")} />}
            <TextInput label="Raison sociale" required value={f.legal_name} onChange={set("legal_name")} />
            <TextInput label="Nom commercial" value={f.trade_name} onChange={set("trade_name")} />
            <TextInput label="Matricule fiscal" value={f.tax_id} onChange={set("tax_id")} placeholder="1234567A/A/M/000" />
            <TextInput label="Identifiant RNE" value={f.rne_id} onChange={set("rne_id")} />
            <TextInput label="Activité économique" value={f.activity} onChange={set("activity")} />
            <Textarea label="Adresse" value={f.address} onChange={set("address")} autosize />
            <TextInput label="Ville" value={f.city} onChange={set("city")} />
            <TextInput label="Code postal" value={f.postal_code} onChange={set("postal_code")} />
          </SimpleGrid>
        </Tabs.Panel>
        <Tabs.Panel value="contact">
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label="Téléphone" value={f.phone} onChange={set("phone")} />
            <TextInput label="E-mail" value={f.email} onChange={set("email")} />
            <TextInput label="Personne de contact" value={f.contact_name} onChange={set("contact_name")} />
            <TextInput label="Fonction" value={f.contact_function} onChange={set("contact_function")} />
            <TextInput label="Téléphone du contact" value={f.contact_phone} onChange={set("contact_phone")} />
            <TextInput label="E-mail du contact" value={f.contact_email} onChange={set("contact_email")} />
            <TextInput label="Banque" value={f.bank_name} onChange={set("bank_name")} />
            <TextInput label="RIB" value={f.bank_rib} onChange={set("bank_rib")} />
          </SimpleGrid>
        </Tabs.Panel>
        <Tabs.Panel value="credit">
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <NumberInput label="Délai de paiement (jours)" min={0} max={365} value={f.payment_terms_days} onChange={set("payment_terms_days")} />
            <TextInput label="Conditions de règlement" placeholder="ex. 60 jours fin de mois, par traite" value={f.payment_terms_label} onChange={set("payment_terms_label")} />
            <Select label="Devise de facturation" data={refs.currencies} value={f.currency} onChange={set("currency")} />
            <div />
            <NumberInput label="Plafond de crédit (TND)" description="Créances ouvertes maximales" decimalScale={3} thousandSeparator=" " decimalSeparator=","
                         min={0} value={f.credit_limit} onChange={set("credit_limit")} disabled={limitLocked} />
            <NumberInput label="Encours maximal (TND)" description="Créances + chèques et effets non encore encaissés" decimalScale={3} thousandSeparator=" "
                         decimalSeparator="," min={0} value={f.max_exposure} onChange={set("max_exposure")} disabled={limitLocked} />
          </SimpleGrid>
          {initial && <Alert mt="md" color="blue" icon={<IconLock size={16} />}>Toute modification du plafond ou de l'encours maximal crée une demande soumise à la validation d'une autre personne habilitée.</Alert>}
        </Tabs.Panel>
        <Tabs.Panel value="class">
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Select label="Catégorie" data={refs.categories} value={f.category_code} onChange={set("category_code")} clearable />
            <Select label="Secteur d'activité" data={refs.sectors} value={f.sector_code} onChange={set("sector_code")} clearable searchable />
            <Select label="Zone géographique" data={refs.zones} value={f.zone_code} onChange={set("zone_code")} clearable searchable />
            <Select label="Groupe de clients" data={refs.groups} value={f.group_code} onChange={set("group_code")} clearable />
            <Select label="Commercial" data={refs.salespeople} value={f.salesperson_id ? String(f.salesperson_id) : null} onChange={set("salesperson_id")} clearable />
            <Textarea label="Notes" value={f.notes} onChange={set("notes")} autosize />
          </SimpleGrid>
        </Tabs.Panel>
      </Tabs>
      <Group justify="flex-end" mt="lg">
        <Button variant="default" onClick={onClose}>Annuler</Button>
        <Button onClick={submit} loading={save.isPending} disabled={!f.legal_name}>Enregistrer</Button>
      </Group>
    </Modal>
  );
}

export default function Customers() {
  const nav = useNavigate();
  const { can } = useAuth();
  const refs = useRefs();
  const [filters, setFilters] = useState<any>({});
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useQ<any>(["customers", filters], `/customers${qs({ ...filters, limit: 2000 })}`);
  const cols: Col<any>[] = [
    { key: "code", label: "Code" },
    { key: "legal_name", label: "Raison sociale", render: (r) => <Group gap={6} wrap="nowrap"><Text size="sm" fw={500}>{r.legal_name}</Text>
        {r.is_demo && <Badge size="xs" color="yellow">démo</Badge>}{r.in_litigation && <Badge size="xs" color="grape">contentieux</Badge>}</Group> },
    { key: "city", label: "Ville" },
    { key: "open_tnd", label: "Encours TND", align: "right", render: (r) => <Amount v={r.open_tnd} /> },
    { key: "overdue_tnd", label: "Dont échu", align: "right", render: (r) => <Amount v={r.overdue_tnd} color={Number(r.overdue_tnd) > 0 ? "orange.8" : undefined} /> },
    { key: "credit_limit", label: "Plafond", align: "right", render: (r) => (Number(r.credit_limit) ? <Amount v={r.credit_limit} /> : <Text size="sm" c="dimmed">—</Text>) },
    { key: "usage", label: "Utilisation", sortValue: (r) => (Number(r.credit_limit) ? Number(r.open_tnd) / Number(r.credit_limit) : -1), render: (r) => {
      if (!Number(r.credit_limit)) return "—";
      const u = (Number(r.open_tnd) / Number(r.credit_limit)) * 100;
      return <Progress value={Math.min(u, 100)} color={u > 100 ? "red" : u > 85 ? "orange" : "teal"} w={80} />;
    } },
    { key: "risk_class", label: "Risque", render: (r) => <StatusBadge code={r.risk_class} label={r.risk_class ? `${RISK_LABELS[r.risk_class]} (${r.risk_score})` : null} /> },
    { key: "status", label: "Statut", render: (r) => <StatusBadge code={r.status === "ACTIF" ? "ENCAISSE" : r.status === "BLOQUE" ? "REJETE" : "ANNULE"} label={r.status.toLowerCase()} /> },
  ];
  const f = (k: string) => (v: any) => setFilters((x: any) => ({ ...x, [k]: v || undefined }));
  return (
    <>
      <PageHeader title="Fichier clients" subtitle={`${data?.total ?? "…"} client(s)`}
                  actions={can("customers.write") && <Button leftSection={<IconPlus size={16} />} onClick={() => setOpen(true)}>Nouveau client</Button>} />
      <Card withBorder radius="md">
        <Group mb="sm" gap="xs" wrap="wrap">
          <TextInput placeholder="Nom, code, matricule, ville…" value={filters.q || ""} onChange={(e) => f("q")(e.currentTarget.value)} w={240} />
          <Select placeholder="Risque" data={Object.entries(RISK_LABELS).map(([value, label]) => ({ value, label }))} value={filters.risk_class || null} onChange={f("risk_class")} clearable w={130} />
          <Select placeholder="Catégorie" data={refs.categories} value={filters.category_code || null} onChange={f("category_code")} clearable w={170} />
          <Select placeholder="Secteur" data={refs.sectors} value={filters.sector_code || null} onChange={f("sector_code")} clearable w={170} />
          <Select placeholder="Zone" data={refs.zones} value={filters.zone_code || null} onChange={f("zone_code")} clearable searchable w={150} />
          <Select placeholder="Statut" data={[{ value: "ACTIF", label: "Actif" }, { value: "BLOQUE", label: "Bloqué" }, { value: "ARCHIVE", label: "Archivé" }]}
                  value={filters.status || null} onChange={f("status")} clearable w={120} />
        </Group>
        <DataTable rows={data?.rows || []} columns={cols} loading={isLoading} searchable={false} onRowClick={(r) => nav(`/clients/${r.id}`)} />
      </Card>
      <CustomerForm opened={open} onClose={() => setOpen(false)} />
    </>
  );
}

export function Attachments({ entityType, entityId, canWrite }: { entityType: string; entityId: number; canWrite: boolean }) {
  const { data = [] } = useQ<any[]>(["attachments", entityType, entityId], `/attachments?entity_type=${entityType}&entity_id=${entityId}`);
  const [file, setFile] = useState<File | null>(null);
  const [desc, setDesc] = useState("");
  const up = useAction(async () => {
    const fd = new FormData();
    fd.append("entity_type", entityType);
    fd.append("entity_id", String(entityId));
    if (desc) fd.append("description", desc);
    fd.append("file", file as File);
    return api("/attachments", { form: fd, method: "POST" });
  }, "Pièce jointe ajoutée", () => { setFile(null); setDesc(""); });
  return (
    <Stack>
      {canWrite && (
        <Group align="flex-end">
          <FileInput label="Pièce justificative" placeholder="PDF, image, Excel…" value={file} onChange={setFile} leftSection={<IconFileUpload size={16} />} w={260} />
          <TextInput label="Description" value={desc} onChange={(e) => setDesc(e.currentTarget.value)} w={260} />
          <Button disabled={!file} loading={up.isPending} onClick={() => up.mutate(undefined)}>Ajouter</Button>
        </Group>
      )}
      <Table fz="sm">
        <Table.Thead><Table.Tr><Table.Th>Fichier</Table.Th><Table.Th>Description</Table.Th><Table.Th>Ajouté le</Table.Th><Table.Th ta="right">Taille</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {data.map((a) => (
            <Table.Tr key={a.id}><Table.Td><Button variant="subtle" size="compact-sm" onClick={() => download(`/attachments/${a.id}`, a.filename).catch(notifyError)}>{a.filename}</Button></Table.Td>
              <Table.Td>{a.description || "—"}</Table.Td><Table.Td>{datetime(a.uploaded_at)}</Table.Td><Table.Td ta="right">{Math.round(a.size / 1024)} Ko</Table.Td></Table.Tr>
          ))}
          {!data.length && <Table.Tr><Table.Td colSpan={4}><Text size="sm" c="dimmed">Aucune pièce.</Text></Table.Td></Table.Tr>}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}

export function CustomerDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const [edit, setEdit] = useState(false);
  const { data: c } = useQ<any>(["customer", id], `/customers/${id}`);
  const inv = useQ<any>(["invoices", "cust", id], `/invoices?customer_id=${id}&limit=2000`);
  const pays = useQ<any>(["payments", "cust", id], `/payments?customer_id=${id}&limit=2000`);
  const led = useQ<any>(["ledger", id], `/customers/${id}/ledger`);
  const acts = useQ<any[]>(["dunning", "cust", id], `/dunning/actions?customer_id=${id}`);
  const hist = useQ<any[]>(["history", id], `/customers/${id}/history`);
  const [statusModal, setStatusModal] = useState(false);
  const [newStatus, setNewStatus] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const reqStatus = useAction(() => api(`/customers/${id}/status`, { body: { status: newStatus, reason } }), "Demande de changement de statut transmise pour validation",
    () => setStatusModal(false));
  if (!c) return <Text>Chargement…</Text>;
  const e = c.exposure;
  return (
    <>
      <PageHeader title={`${c.legal_name}`} subtitle={<Group gap="xs"><Text size="sm" c="dimmed">{c.code} · MF {c.tax_id || "—"} · {c.city || ""}</Text>
        <StatusBadge code={c.status === "ACTIF" ? "ENCAISSE" : "REJETE"} label={c.status.toLowerCase()} />
        {c.risk_class && <StatusBadge code={c.risk_class} label={`Risque ${RISK_LABELS[c.risk_class].toLowerCase()} · ${c.risk_score}/100`} />}
        {c.in_litigation && <Badge color="grape">En contentieux</Badge>}{c.is_demo && <Badge color="yellow">Données de démonstration</Badge>}</Group>}
        actions={<>
          {can("invoices.write") && <Button variant="default" onClick={() => nav(`/factures/nouvelle?customer_id=${c.id}`)}>Nouvelle facture</Button>}
          {can("payments.write") && <Button variant="default" onClick={() => nav(`/encaissements/nouveau?customer_id=${c.id}`)}>Saisir un règlement</Button>}
          {can("customers.write") && <Button variant="default" onClick={() => setStatusModal(true)}>Bloquer / débloquer</Button>}
          {can("customers.write") && <Button leftSection={<IconEdit size={16} />} onClick={() => setEdit(true)}>Modifier</Button>}
        </>} />
      {(e.over_limit || e.over_exposure) && (
        <Alert color="red" mb="md" icon={<IconAlertTriangle />}>
          {e.over_limit && <>Plafond de crédit dépassé : encours {money(e.open_tnd)} pour un plafond de {money(c.credit_limit)} TND. </>}
          {e.over_exposure && <>Encours maximal (y compris effets et chèques en circulation) dépassé : {money(e.exposure_tnd)} TND.</>}
        </Alert>
      )}
      <SimpleGrid cols={{ base: 1, xs: 2, md: 5 }} mb="md">
        <Kpi label="Créances ouvertes" value={money(e.open_tnd)} />
        <Kpi label="Dont échu" value={money(e.overdue_tnd)} color="orange.7" />
        <Kpi label="Effets / chèques à encaisser" value={money(e.pending_instruments_tnd)} hint="Risque jusqu'à encaissement" />
        <Kpi label="Crédits non affectés" value={money(e.unallocated_credits_tnd)} hint="Avances, avoirs non imputés" />
        <Kpi label="Plafond disponible" value={e.available_credit !== null ? money(e.available_credit) : "—"} color={Number(e.available_credit) < 0 ? "red.7" : "teal.7"}
             hint={e.limit_usage_pct !== null ? `Utilisation ${pct(e.limit_usage_pct, 0)}` : "Aucun plafond fixé"} />
      </SimpleGrid>
      <Card withBorder radius="md">
        <Tabs defaultValue="factures" keepMounted={false}>
          <Tabs.List>
            <Tabs.Tab value="factures">Factures ({inv.data?.total ?? 0})</Tabs.Tab>
            <Tabs.Tab value="reglements">Règlements ({pays.data?.total ?? 0})</Tabs.Tab>
            <Tabs.Tab value="grandlivre">Grand livre</Tabs.Tab>
            <Tabs.Tab value="relances">Relances ({acts.data?.length ?? 0})</Tabs.Tab>
            <Tabs.Tab value="risque">Risque</Tabs.Tab>
            <Tabs.Tab value="fiche">Fiche</Tabs.Tab>
            <Tabs.Tab value="incidents">Incidents ({c.incidents.length})</Tabs.Tab>
            <Tabs.Tab value="docs">Documents ({c.attachments.length})</Tabs.Tab>
            <Tabs.Tab value="historique">Historique</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="factures" pt="md">
            <DataTable rows={inv.data?.rows || []} onRowClick={(r) => nav(`/factures/${r.id}`)} columns={[
              { key: "number", label: "N°", render: (r) => r.number || <Text size="sm" c="dimmed">brouillon</Text> }, { key: "doc_type", label: "Type" },
              { key: "issue_date", label: "Date", render: (r) => date(r.issue_date) }, { key: "due_date", label: "Échéance", render: (r) => date(r.due_date) },
              { key: "total_ttc", label: "TTC", align: "right", render: (r) => <Amount v={r.total_ttc} currency={r.currency !== "TND" ? r.currency : undefined} /> },
              { key: "balance", label: "Reste dû", align: "right", render: (r) => <Amount v={r.balance} strong /> },
              { key: "days_overdue", label: "Retard", align: "right", render: (r) => (r.days_overdue ? `${r.days_overdue} j` : "—") },
              { key: "status", label: "Statut", render: (r) => <StatusBadge code={r.status} label={r.status_label} /> },
            ]} />
          </Tabs.Panel>
          <Tabs.Panel value="reglements" pt="md">
            <DataTable rows={pays.data?.rows || []} onRowClick={(r) => nav(`/encaissements/${r.id}`)} columns={[
              { key: "number", label: "N°" }, { key: "receipt_date", label: "Date", render: (r) => date(r.receipt_date) }, { key: "method_label", label: "Moyen" },
              { key: "reference", label: "Référence" }, { key: "amount", label: "Montant", align: "right", render: (r) => <Amount v={r.amount} currency={r.currency !== "TND" ? r.currency : undefined} /> },
              { key: "unallocated_amount", label: "Non affecté", align: "right", render: (r) => <Amount v={r.unallocated_amount} /> },
              { key: "status", label: "Statut", render: (r) => <StatusBadge code={r.status} label={r.status.replace("_", " ").toLowerCase()} /> },
            ]} />
          </Tabs.Panel>
          <Tabs.Panel value="grandlivre" pt="md">
            <Group justify="flex-end" mb="xs"><ExportMenu path={`/reports/grand-livre?customer_id=${c.id}`} /></Group>
            <DataTable rows={(led.data?.rows || []).map((r: any, i: number) => ({ ...r, id: i }))} pageSize={50} columns={[
              { key: "date", label: "Date", render: (r) => date(r.date) }, { key: "piece", label: "Pièce" }, { key: "label", label: "Libellé" },
              { key: "debit", label: "Débit", align: "right", render: (r) => (Number(r.debit) ? <Amount v={r.debit} /> : "") },
              { key: "credit", label: "Crédit", align: "right", render: (r) => (Number(r.credit) ? <Amount v={r.credit} /> : "") },
              { key: "balance", label: "Solde", align: "right", render: (r) => <Amount v={r.balance} strong /> },
            ]} />
            <Text size="sm" ta="right" mt="xs">Solde de clôture : <b>{money(led.data?.closing_balance)} TND</b></Text>
          </Tabs.Panel>
          <Tabs.Panel value="relances" pt="md">
            <DataTable rows={acts.data || []} columns={[
              { key: "action_date", label: "Date", render: (r) => date(r.action_date) }, { key: "action_label", label: "Action" }, { key: "channel", label: "Canal" },
              { key: "amount_due_tnd", label: "Montant dû", align: "right", render: (r) => <Amount v={r.amount_due_tnd} /> },
              { key: "responsible", label: "Responsable" }, { key: "result_label", label: "Résultat" },
              { key: "next_action_date", label: "Prochaine action", render: (r) => `${date(r.next_action_date)} ${r.next_action || ""}` },
              { key: "comments", label: "Commentaires" },
            ]} />
          </Tabs.Panel>
          <Tabs.Panel value="risque" pt="md"><RiskPanel customerId={c.id} history={c.risk_history} /></Tabs.Panel>
          <Tabs.Panel value="fiche" pt="md">
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
              <Field label="Nom commercial">{c.trade_name}</Field><Field label="Activité">{c.activity}</Field><Field label="Identifiant RNE">{c.rne_id}</Field>
              <Field label="Adresse">{c.address} {c.postal_code} {c.city}</Field><Field label="Téléphone / e-mail">{c.phone} {c.email}</Field>
              <Field label="Contact">{c.contact_name} {c.contact_function && `(${c.contact_function})`} {c.contact_phone} {c.contact_email}</Field>
              <Field label="Conditions de règlement">{c.payment_terms_days} jours {c.payment_terms_label && `– ${c.payment_terms_label}`}</Field>
              <Field label="Plafond / encours max">{money(c.credit_limit)} / {money(c.max_exposure)} TND</Field>
              <Field label="Banque / RIB">{c.bank_name} {c.bank_rib}</Field>
              <Field label="Catégorie / secteur / zone">{[c.category_code, c.sector_code, c.zone_code].filter(Boolean).join(" · ")}</Field>
              <Field label="Groupe">{c.group_code}</Field><Field label="Commercial">{c.salesperson_name}</Field>
              <Field label="Notes">{c.notes}</Field><Field label="Créé le">{datetime(c.created_at)}</Field><Field label="Modifié le">{datetime(c.updated_at)}</Field>
            </SimpleGrid>
          </Tabs.Panel>
          <Tabs.Panel value="incidents" pt="md">
            <Table fz="sm"><Table.Thead><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Règlement</Table.Th><Table.Th>Référence</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th>Motif</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{c.incidents.map((x: any) => <Table.Tr key={x.number}><Table.Td>{date(x.date)}</Table.Td><Table.Td>{x.number}</Table.Td><Table.Td>{x.reference}</Table.Td>
                <Table.Td ta="right"><Amount v={x.amount} /></Table.Td><Table.Td>{x.reason}</Table.Td></Table.Tr>)}
                {!c.incidents.length && <Table.Tr><Table.Td colSpan={5}><Text size="sm" c="dimmed">Aucun incident de paiement.</Text></Table.Td></Table.Tr>}</Table.Tbody></Table>
          </Tabs.Panel>
          <Tabs.Panel value="docs" pt="md"><Attachments entityType="customer" entityId={c.id} canWrite={can("customers.write")} /></Tabs.Panel>
          <Tabs.Panel value="historique" pt="md">
            <DataTable rows={(hist.data || []).map((h, i) => ({ ...h, id: i }))} columns={[
              { key: "ts", label: "Date", render: (r) => datetime(r.ts) }, { key: "username", label: "Utilisateur" }, { key: "action", label: "Opération" },
              { key: "details", label: "Détail", render: (r) => <Text size="xs" ff="monospace" lineClamp={3}>{JSON.stringify(r.details)}</Text> },
            ]} />
          </Tabs.Panel>
        </Tabs>
      </Card>
      <CustomerForm opened={edit} onClose={() => setEdit(false)} initial={c} />
      <Modal opened={statusModal} onClose={() => setStatusModal(false)} title="Changement de statut du client">
        <Stack>
          <Select label="Nouveau statut" data={[{ value: "ACTIF", label: "Actif" }, { value: "BLOQUE", label: "Bloqué (facturation soumise à accord)" }, { value: "ARCHIVE", label: "Archivé" }]}
                  value={newStatus} onChange={setNewStatus} />
          <Textarea label="Motif" value={reason} onChange={(ev) => setReason(ev.currentTarget.value)} />
          <Text size="xs" c="dimmed">La demande sera validée par une autre personne habilitée (séparation des fonctions).</Text>
          <Group justify="flex-end"><Button onClick={() => reqStatus.mutate(undefined)} disabled={!newStatus || reason.length < 10} loading={reqStatus.isPending}>Transmettre</Button></Group>
        </Stack>
      </Modal>
    </>
  );
}
