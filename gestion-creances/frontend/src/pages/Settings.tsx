import { useState } from "react";
import { Alert, Badge, Button, Card, Checkbox, Group, JsonInput, Modal, NumberInput, Select, SimpleGrid, Stack, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconAlertTriangle, IconPlus } from "@tabler/icons-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useQ } from "../hooks";
import { date, iso } from "../format";
import { DataTable, PageHeader, useAction } from "../components/ui";

type FieldDef = { key: string; label: string; type?: "text" | "number" | "bool" | "date" | "select" | "textarea"; options?: string[]; show?: boolean };

function Crud({ path, fields, title }: { path: string; fields: FieldDef[]; title: string }) {
  const { can } = useAuth();
  const { data = [] } = useQ<any[]>([path.slice(1)], path);
  const [edit, setEdit] = useState<any>(null);
  const save = useAction((v: any) => (v.id !== undefined && v.__existing ? api(`${path}/${v.id}`, { method: "PUT", body: v }) : api(path, { body: v })), "Paramètre enregistré (tracé dans le journal d'audit)", () => setEdit(null));
  const set = (k: string) => (v: any) => setEdit((e: any) => ({ ...e, [k]: v?.currentTarget ? (v.currentTarget.type === "checkbox" ? v.currentTarget.checked : v.currentTarget.value) : v }));
  return (
    <>
      <Group justify="flex-end" mb="xs">{can("params.write") && <Button size="xs" leftSection={<IconPlus size={14} />} onClick={() => setEdit({})}>Ajouter</Button>}</Group>
      <DataTable rows={data} onRowClick={(r) => can("params.write") && setEdit({ ...r, __existing: true })} columns={fields.filter((f) => f.show !== false).map((f) => ({
        key: f.key, label: f.label, render: (r: any) => (f.type === "bool" ? (r[f.key] ? "Oui" : "Non") : f.type === "date" ? date(r[f.key]) : f.key === "to_validate" ? (r[f.key] ? <Badge color="orange">à valider</Badge> : "") : <Text size="sm" lineClamp={2}>{r[f.key] ?? "—"}</Text>),
      }))} />
      <Modal opened={!!edit} onClose={() => setEdit(null)} title={title} size="lg">
        {edit && <Stack>
          {fields.map((f) => {
            const v = edit[f.key];
            if (f.type === "bool") return <Checkbox key={f.key} label={f.label} checked={!!v} onChange={(e) => setEdit((x: any) => ({ ...x, [f.key]: e.currentTarget.checked }))} />;
            if (f.type === "number") return <NumberInput key={f.key} label={f.label} value={v ?? ""} onChange={set(f.key)} decimalScale={6} />;
            if (f.type === "date") return <DateInput key={f.key} label={f.label} value={v ? new Date(v) : null} onChange={(d) => setEdit((x: any) => ({ ...x, [f.key]: iso(d) || null }))} valueFormat="DD/MM/YYYY" clearable />;
            if (f.type === "select") return <Select key={f.key} label={f.label} data={f.options || []} value={v ?? null} onChange={set(f.key)} />;
            if (f.type === "textarea") return <Textarea key={f.key} label={f.label} value={v ?? ""} onChange={set(f.key)} autosize minRows={f.key === "body" ? 10 : 2} />;
            return <TextInput key={f.key} label={f.label} value={v ?? ""} onChange={set(f.key)} disabled={edit.__existing && (f.key === "code" && path === "/currencies")} />;
          })}
          {path === "/dunning-templates" && <Text size="xs" c="dimmed">Variables : {"{client} {code_client} {contact} {adresse_client} {date} {montant_du} {liste_factures} {nombre_factures} {jours_retard} {responsable} {societe} {adresse_societe} {telephone_societe}"}</Text>}
          <Group justify="flex-end"><Button onClick={() => { const { __existing, ...body } = edit; save.mutate({ ...body, __existing, id: edit.id }); }} loading={save.isPending}>Enregistrer</Button></Group>
        </Stack>}
      </Modal>
    </>
  );
}

function Params() {
  const { can } = useAuth();
  const { data = [] } = useQ<any[]>(["params"], "/params");
  const [edit, setEdit] = useState<any>(null);
  const save = useAction(() => api(`/params/${edit.key}`, { method: "PUT", body: { value: JSON.parse(edit.json), valid_from: iso(edit.valid_from), description: edit.description, source: edit.source, to_validate: edit.to_validate } }),
    "Paramètre enregistré — la nouvelle valeur s'applique à partir de la date d'effet", () => setEdit(null));
  let jsonOk = true;
  try { if (edit) JSON.parse(edit.json); } catch { jsonOk = false; }
  return (
    <>
      <DataTable rowKey="key" rows={data} pageSize={50} onRowClick={(r) => can("params.write") && setEdit({ ...r, json: JSON.stringify(r.value, null, 2), valid_from: new Date() })} columns={[
        { key: "key", label: "Paramètre", render: (r) => <Group gap={4}><Text size="sm" ff="monospace">{r.key}</Text>{r.to_validate && <Badge size="xs" color="orange">à valider</Badge>}</Group> },
        { key: "value", label: "Valeur en vigueur", render: (r) => <Text size="xs" ff="monospace" lineClamp={2}>{JSON.stringify(r.value)}</Text> },
        { key: "valid_from", label: "Depuis le", render: (r) => date(r.valid_from) },
        { key: "description", label: "Description / source", render: (r) => <Text size="xs" lineClamp={2}>{[r.description, r.source].filter(Boolean).join(" — ")}</Text> },
      ]} />
      <Modal opened={!!edit} onClose={() => setEdit(null)} title={`Paramètre ${edit?.key}`} size="lg">
        {edit && <Stack>
          <Alert color="blue" p="xs">Une modification crée une nouvelle version datée : les calculs antérieurs à la date d'effet continuent d'utiliser l'ancienne valeur.</Alert>
          <JsonInput label="Valeur (JSON)" value={edit.json} onChange={(v) => setEdit({ ...edit, json: v })} autosize minRows={6} formatOnBlur validationError="JSON invalide" />
          <DateInput label="Date d'effet" value={edit.valid_from} onChange={(d) => setEdit({ ...edit, valid_from: d })} valueFormat="DD/MM/YYYY" />
          <Textarea label="Description" value={edit.description || ""} onChange={(e) => setEdit({ ...edit, description: e.currentTarget.value })} autosize />
          <Textarea label="Source / texte de référence" value={edit.source || ""} onChange={(e) => setEdit({ ...edit, source: e.currentTarget.value })} autosize />
          <Checkbox label="Valeur à faire valider par l'expert-comptable" checked={!!edit.to_validate} onChange={(e) => setEdit({ ...edit, to_validate: e.currentTarget.checked })} />
          <Group justify="flex-end"><Button disabled={!jsonOk} onClick={() => save.mutate(undefined)} loading={save.isPending}>Enregistrer</Button></Group>
        </Stack>}
      </Modal>
    </>
  );
}

export default function Settings() {
  const { data: taxes = [] } = useQ<any[]>(["tax-rates"], "/tax-rates");
  const pending = taxes.filter((t) => t.to_validate).length;
  return (
    <>
      <PageHeader title="Paramétrage" subtitle="Règles fiscales, comptables et de gestion modifiables sans toucher au code — chaque modification est tracée" />
      {pending > 0 && <Alert color="orange" mb="md" icon={<IconAlertTriangle />}>{pending} taux fiscal(aux) marqué(s) « à valider » : faites confirmer les valeurs en vigueur (loi de finances de l'année) par l'expert-comptable avant la mise en production.</Alert>}
      <Card withBorder radius="md">
        <Tabs defaultValue="params" keepMounted={false}>
          <Tabs.List mb="md">
            <Tabs.Tab value="params">Règles de gestion</Tabs.Tab><Tabs.Tab value="taxes">Taxes</Tabs.Tab><Tabs.Tab value="methods">Moyens de paiement</Tabs.Tab>
            <Tabs.Tab value="fx">Devises et cours</Tabs.Tab><Tabs.Tab value="refs">Listes de valeurs</Tabs.Tab><Tabs.Tab value="levels">Niveaux de relance</Tabs.Tab><Tabs.Tab value="tpl">Modèles de relance</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="params"><Params /></Tabs.Panel>
          <Tabs.Panel value="taxes"><Crud path="/tax-rates" title="Taxe" fields={[{ key: "code", label: "Code" }, { key: "label", label: "Libellé" }, { key: "kind", label: "Nature", type: "select", options: ["TVA", "TIMBRE", "AUTRE"] },
            { key: "rate", label: "Taux (%)", type: "number" }, { key: "fixed_amount", label: "Montant fixe (TND)", type: "number" }, { key: "in_vat_base", label: "Inclus dans l'assiette TVA", type: "bool" },
            { key: "account_code", label: "Compte" }, { key: "valid_from", label: "Applicable du", type: "date" }, { key: "valid_to", label: "au", type: "date" }, { key: "active", label: "Actif", type: "bool" },
            { key: "source", label: "Texte de référence", type: "textarea", show: false }, { key: "to_validate", label: "À valider", type: "bool" }]} /></Tabs.Panel>
          <Tabs.Panel value="methods"><Crud path="/payment-methods" title="Moyen de paiement" fields={[{ key: "code", label: "Code" }, { key: "label", label: "Libellé" },
            { key: "kind", label: "Nature", type: "select", options: ["ESPECES", "CHEQUE", "VIREMENT", "EFFET", "RETENUE_SOURCE", "AUTRE"] }, { key: "requires_clearing", label: "Encaissement différé", type: "bool" },
            { key: "account_code", label: "Compte de trésorerie" }, { key: "active", label: "Actif", type: "bool" }]} /></Tabs.Panel>
          <Tabs.Panel value="fx">
            <SimpleGrid cols={{ base: 1, lg: 2 }}>
              <Crud path="/currencies" title="Devise" fields={[{ key: "code", label: "Code ISO" }, { key: "label", label: "Libellé" }, { key: "decimals", label: "Décimales", type: "number" }, { key: "active", label: "Active", type: "bool" }]} />
              <Crud path="/exchange-rates" title="Cours de change" fields={[{ key: "currency", label: "Devise", type: "select", options: ["EUR", "USD"] }, { key: "date", label: "Date", type: "date" },
                { key: "rate", label: "Cours (TND pour 1 unité)", type: "number" }, { key: "source", label: "Source (ex. BCT)" }]} />
            </SimpleGrid>
          </Tabs.Panel>
          <Tabs.Panel value="refs"><Crud path="/reference-values" title="Valeur de liste" fields={[{ key: "kind", label: "Liste", type: "select", options: ["CATEGORY", "SECTOR", "ZONE", "GROUP"] },
            { key: "code", label: "Code" }, { key: "label", label: "Libellé" }, { key: "active", label: "Active", type: "bool" }]} /></Tabs.Panel>
          <Tabs.Panel value="levels"><Crud path="/dunning-levels" title="Niveau de relance" fields={[{ key: "level", label: "Niveau", type: "number" }, { key: "code", label: "Code" }, { key: "label", label: "Libellé" },
            { key: "days_after_due", label: "Jours après échéance", type: "number" }, { key: "min_amount", label: "Montant minimum", type: "number" }, { key: "template_id", label: "N° modèle", type: "number" },
            { key: "escalate_to_legal", label: "Passage au contentieux", type: "bool" }, { key: "active", label: "Actif", type: "bool" }]} /></Tabs.Panel>
          <Tabs.Panel value="tpl"><Crud path="/dunning-templates" title="Modèle de relance" fields={[{ key: "code", label: "Code" }, { key: "label", label: "Libellé" },
            { key: "channel", label: "Canal", type: "select", options: ["LETTRE", "EMAIL", "SMS"] }, { key: "subject", label: "Objet" }, { key: "body", label: "Texte", type: "textarea", show: false }, { key: "active", label: "Actif", type: "bool" }]} /></Tabs.Panel>
        </Tabs>
      </Card>
    </>
  );
}
