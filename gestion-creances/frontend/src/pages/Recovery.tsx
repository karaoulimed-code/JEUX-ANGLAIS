import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, Grid, Group, Modal, MultiSelect, NumberInput, Select, SimpleGrid, Stack, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconCopy, IconPrinter } from "@tabler/icons-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useQ } from "../hooks";
import { date, iso, money } from "../format";
import { Amount, DataTable, ExportMenu, Kpi, PageHeader, StatusBadge, notifyOk, useAction } from "../components/ui";

const ACTION_FOR_LEVEL: Record<number, string> = { 1: "RELANCE_1", 2: "RELANCE_2", 3: "MISE_EN_DEMEURE", 4: "TRANSMISSION_JURIDIQUE" };

function ActionModal({ target, onClose }: { target: any; onClose: () => void }) {
  const meta = useQ<any>(["dunning-meta"], "/dunning/meta");
  const tpls = useQ<any[]>(["dunning-templates"], "/dunning-templates");
  const levels = useQ<any[]>(["dunning-levels"], "/dunning-levels");
  const [f, setF] = useState<any>({});
  const [preview, setPreview] = useState<any>(null);
  useEffect(() => {
    if (!target) return;
    const lv = target.recommended_level;
    setF({ action_type: lv ? ACTION_FOR_LEVEL[lv.level] || "RELANCE_1" : target.upcoming ? "RELANCE_PREVENTIVE" : "APPEL", level_id: lv ? String(lv.id) : null,
      template_id: lv?.template_id ? String(lv.template_id) : target.upcoming ? String((tpls.data || []).find((t) => t.code === "RAPPEL")?.id || "") : null,
      channel: "LETTRE", invoice_ids: (target.invoices || []).map((i: any) => String(i.invoice_id)), action_date: new Date(),
      next_action_date: new Date(Date.now() + 8 * 86400000) });
    setPreview(null);
  }, [target, tpls.data]);
  const set = (k: string) => (v: any) => setF((x: any) => ({ ...x, [k]: v?.currentTarget ? v.currentTarget.value : v }));
  const gen = useAction(() => api("/dunning/preview", { body: { customer_id: target.customer_id, template_id: Number(f.template_id), invoice_ids: f.invoice_ids.map(Number) } }),
    undefined, (r) => setPreview(r));
  const save = useAction(() => api("/dunning/actions", { body: {
    customer_id: target.customer_id, level_id: f.level_id ? Number(f.level_id) : null, action_type: f.action_type, action_date: iso(f.action_date), channel: f.channel,
    result_code: f.result_code || null, result: f.result || null, promised_date: iso(f.promised_date), promised_amount: f.promised_amount ? String(f.promised_amount) : null,
    next_action: f.next_action || null, next_action_date: iso(f.next_action_date), comments: f.comments || null, invoice_ids: f.invoice_ids.map(Number),
    rendered_subject: preview?.subject || null, rendered_text: preview?.body || null } }), "Action de recouvrement enregistrée", onClose);
  if (!target) return null;
  const at = meta.data?.action_types || {};
  const rc = meta.data?.result_codes || {};
  const print = () => {
    const w = window.open("", "_blank");
    if (!w) return;
    w.document.write(`<html><head><title>${preview.subject}</title></head><body style="font-family:Arial;padding:40px;white-space:pre-wrap;font-size:13px">${preview.body.replace(/</g, "&lt;")}</body></html>`);
    w.document.close();
    w.print();
  };
  return (
    <Modal opened={!!target} onClose={onClose} title={`Action de recouvrement — ${target.name}`} size="xl">
      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Stack gap="xs">
            <Select label="Type d'action" data={Object.entries(at).map(([value, label]) => ({ value, label: label as string }))} value={f.action_type} onChange={set("action_type")} />
            <Select label="Niveau de relance" clearable data={(levels.data || []).map((l) => ({ value: String(l.id), label: `${l.level} – ${l.label}` }))} value={f.level_id} onChange={set("level_id")} />
            <Select label="Canal" data={meta.data?.channels || []} value={f.channel} onChange={set("channel")} />
            <MultiSelect label="Factures concernées" data={(target.invoices || []).map((i: any) => ({ value: String(i.invoice_id), label: `${i.number} – ${money(i.remaining_tnd)}` }))}
                         value={f.invoice_ids || []} onChange={set("invoice_ids")} />
            <DateInput label="Date de l'action" value={f.action_date} onChange={set("action_date")} valueFormat="DD/MM/YYYY" />
            <Select label="Résultat" clearable data={Object.entries(rc).map(([value, label]) => ({ value, label: label as string }))} value={f.result_code || null} onChange={set("result_code")} />
            {f.result_code === "PROMESSE" && <SimpleGrid cols={2}><DateInput label="Date promise" value={f.promised_date || null} onChange={set("promised_date")} valueFormat="DD/MM/YYYY" />
              <NumberInput label="Montant promis" decimalScale={3} value={f.promised_amount || ""} onChange={set("promised_amount")} /></SimpleGrid>}
            <TextInput label="Détail du résultat" value={f.result || ""} onChange={set("result")} />
            <SimpleGrid cols={2}><TextInput label="Prochaine action" value={f.next_action || ""} onChange={set("next_action")} />
              <DateInput label="Le" value={f.next_action_date || null} onChange={set("next_action_date")} valueFormat="DD/MM/YYYY" /></SimpleGrid>
            <Textarea label="Commentaires" value={f.comments || ""} onChange={set("comments")} autosize />
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Group align="flex-end" mb="xs">
            <Select label="Modèle de courrier" data={(tpls.data || []).filter((t) => t.active).map((t) => ({ value: String(t.id), label: t.label }))} value={f.template_id} onChange={set("template_id")} style={{ flex: 1 }} />
            <Button variant="light" onClick={() => gen.mutate(undefined)} disabled={!f.template_id} loading={gen.isPending}>Générer</Button>
          </Group>
          {preview ? (
            <>
              <Text fw={600} size="sm">{preview.subject}</Text>
              <Textarea value={preview.body} onChange={(e) => setPreview({ ...preview, body: e.currentTarget.value })} autosize minRows={14} maxRows={22} />
              <Group mt="xs"><Button size="xs" variant="default" leftSection={<IconCopy size={14} />} onClick={() => { navigator.clipboard.writeText(preview.body); notifyOk("Texte copié"); }}>Copier</Button>
                <Button size="xs" variant="default" leftSection={<IconPrinter size={14} />} onClick={print}>Imprimer</Button></Group>
              <Text size="xs" c="dimmed" mt={4}>Le texte est conservé dans l'historique de l'action. Aucun envoi n'est fait automatiquement.</Text>
            </>
          ) : <Text size="sm" c="dimmed">Choisissez un modèle puis « Générer » pour préparer le courrier ou le courriel personnalisé.</Text>}
        </Grid.Col>
      </Grid>
      <Group justify="flex-end" mt="md"><Button variant="default" onClick={onClose}>Annuler</Button><Button onClick={() => save.mutate(undefined)} loading={save.isPending}>Enregistrer l'action</Button></Group>
    </Modal>
  );
}

export default function Recovery() {
  const nav = useNavigate();
  const { can } = useAuth();
  const props = useQ<any>(["dunning-proposals"], "/dunning/proposals");
  const todo = useQ<any[]>(["dunning-todo"], "/dunning/actions?due_only=true");
  const hist = useQ<any[]>(["dunning-history"], "/dunning/actions?limit=500");
  const prio = useQ<any[]>(["priorities"], "/ai/priorities");
  const [target, setTarget] = useState<any>(null);
  const overdue = props.data?.overdue || [];
  const total = overdue.reduce((s: number, r: any) => s + Number(r.amount_overdue), 0);
  const writable = can("dunning.write");
  return (
    <>
      <PageHeader title="Échéances et recouvrement" subtitle="Relances proposées selon les niveaux paramétrés, historique et priorités" actions={<ExportMenu path="/reports/historique-relances" label="Historique des relances" />} />
      <SimpleGrid cols={{ base: 1, sm: 4 }} mb="md">
        <Kpi label="Clients en retard" value={overdue.length} />
        <Kpi label="Montant échu" value={money(total)} color="orange.7" />
        <Kpi label="Actions à mener" value={overdue.filter((o: any) => o.needs_action).length} color="red.7" />
        <Kpi label="Échéances à 7 jours" value={money((props.data?.upcoming || []).reduce((s: number, r: any) => s + Number(r.amount), 0))} />
      </SimpleGrid>
      <Card withBorder radius="md">
        <Tabs defaultValue="relancer">
          <Tabs.List>
            <Tabs.Tab value="relancer">À relancer ({overdue.filter((o: any) => o.needs_action).length})</Tabs.Tab>
            <Tabs.Tab value="tous">Tous les retards ({overdue.length})</Tabs.Tab>
            <Tabs.Tab value="prochaines">Échéances prochaines ({props.data?.upcoming?.length || 0})</Tabs.Tab>
            <Tabs.Tab value="todo">Suivis à faire ({todo.data?.length || 0})</Tabs.Tab>
            <Tabs.Tab value="prio">Priorités (aide à la décision)</Tabs.Tab>
            <Tabs.Tab value="hist">Historique</Tabs.Tab>
          </Tabs.List>
          {["relancer", "tous"].map((tab) => (
            <Tabs.Panel key={tab} value={tab} pt="md">
              <DataTable rowKey="customer_id" rows={tab === "relancer" ? overdue.filter((o: any) => o.needs_action) : overdue} columns={[
                { key: "name", label: "Client", render: (r) => <Group gap={4}><Text size="sm" fw={500} style={{ cursor: "pointer" }} onClick={() => nav(`/clients/${r.customer_id}`)}>{r.name}</Text>
                  {r.in_litigation && <Badge size="xs" color="grape">contentieux</Badge>}</Group> },
                { key: "amount_overdue", label: "Échu", align: "right", render: (r) => <Amount v={r.amount_overdue} strong /> },
                { key: "invoice_count", label: "Fact.", align: "right" },
                { key: "max_days_overdue", label: "Retard max", align: "right", render: (r) => `${r.max_days_overdue} j` },
                { key: "risk_class", label: "Risque", render: (r) => <StatusBadge code={r.risk_class} /> },
                { key: "last_action", label: "Dernière action", render: (r) => (r.last_action ? `${date(r.last_action.date)} · ${r.last_action.type.replaceAll("_", " ").toLowerCase()}` : "—") },
                { key: "promise", label: "Promesse", render: (r) => (r.promise ? <Badge color="teal" variant="light">{date(r.promise.date)} · {money(r.promise.amount)}</Badge> : "—") },
                { key: "recommended_level", label: "Recommandé", render: (r) => (r.recommended_level ? <Badge color="orange">{r.recommended_level.label}</Badge> : r.followup_due ? <Badge>Suivi</Badge> : "—") },
                { key: "act", label: "", sortable: false, render: (r) => writable && <Button size="compact-xs" onClick={() => setTarget(r)}>Agir</Button> },
              ]} />
            </Tabs.Panel>
          ))}
          <Tabs.Panel value="prochaines" pt="md">
            <DataTable rowKey="customer_id" rows={props.data?.upcoming || []} columns={[
              { key: "name", label: "Client" }, { key: "next_due", label: "Prochaine échéance", render: (r) => date(r.next_due) },
              { key: "amount", label: "Montant", align: "right", render: (r) => <Amount v={r.amount} /> },
              { key: "invoices", label: "Factures", render: (r) => r.invoices.map((i: any) => i.number).join(", ") },
              { key: "act", label: "", sortable: false, render: (r) => writable && <Button size="compact-xs" variant="light" onClick={() => setTarget({ ...r, upcoming: true })}>Rappel</Button> },
            ]} />
          </Tabs.Panel>
          <Tabs.Panel value="todo" pt="md">
            <DataTable rows={todo.data || []} columns={[
              { key: "next_action_date", label: "Prévu le", render: (r) => date(r.next_action_date) }, { key: "customer_name", label: "Client" },
              { key: "next_action", label: "Action prévue" }, { key: "action_label", label: "Dernière action" }, { key: "result_label", label: "Résultat" }, { key: "responsible", label: "Responsable" },
            ]} />
          </Tabs.Panel>
          <Tabs.Panel value="prio" pt="md">
            <Text size="sm" c="dimmed" mb="xs">Score = montant échu × (1 + score de risque / 100) × facteur d'ancienneté (1 à 2). Proposition à valider par l'agent : aucune action n'est déclenchée automatiquement.</Text>
            <DataTable rowKey="customer_id" rows={prio.data || []} onRowClick={(r) => nav(`/clients/${r.customer_id}`)} columns={[
              { key: "name", label: "Client" }, { key: "amount_overdue", label: "Échu", align: "right", render: (r) => <Amount v={r.amount_overdue} /> },
              { key: "max_days", label: "Retard max", align: "right", render: (r) => `${r.max_days} j` }, { key: "priority_score", label: "Score", align: "right" },
              { key: "reasons", label: "Justification", render: (r) => r.reasons.join(" · ") },
            ]} />
          </Tabs.Panel>
          <Tabs.Panel value="hist" pt="md">
            <DataTable rows={hist.data || []} columns={[
              { key: "action_date", label: "Date", render: (r) => date(r.action_date) }, { key: "customer_name", label: "Client" }, { key: "action_label", label: "Action" },
              { key: "channel", label: "Canal" }, { key: "invoices", label: "Factures", render: (r) => r.invoices.map((i: any) => i.number).join(", ") },
              { key: "amount_due_tnd", label: "Montant", align: "right", render: (r) => <Amount v={r.amount_due_tnd} /> }, { key: "responsible", label: "Responsable" },
              { key: "result_label", label: "Résultat" }, { key: "next_action_date", label: "Suivi", render: (r) => date(r.next_action_date) },
            ]} />
          </Tabs.Panel>
        </Tabs>
      </Card>
      <ActionModal target={target} onClose={() => setTarget(null)} />
    </>
  );
}
