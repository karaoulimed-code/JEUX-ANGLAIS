import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, Group, SegmentedControl, Text, Textarea } from "@mantine/core";
import { api } from "../api";
import { useAuth } from "../auth";
import { useQ } from "../hooks";
import { datetime, money } from "../format";
import { DataTable, PageHeader, StatusBadge, useAction } from "../components/ui";

export default function Approvals() {
  const { can, user } = useAuth();
  const nav = useNavigate();
  const [status, setStatus] = useState("EN_ATTENTE");
  const { data = [] } = useQ<any[]>(["approvals", status], `/approvals${status ? `?status=${status}` : ""}`);
  const [comment, setComment] = useState("");
  const decide = useAction(({ id, approve }: any) => api(`/approvals/${id}/decide`, { body: { approve, comment } }), (r) => `Demande ${r.status.toLowerCase()}`, () => setComment(""));
  const link = (r: any) => (r.entity_type === "customer" ? `/clients/${r.entity_id}` : r.entity_type === "invoice" ? `/factures/${r.entity_id}` : `/encaissements/${r.entity_id}`);
  const describe = (r: any) => {
    const p = r.payload || {};
    if (r.kind === "CREDIT_LIMIT") return `Plafond ${money(p.old_credit_limit)} → ${money(p.credit_limit)} ; encours max ${money(p.old_max_exposure)} → ${money(p.max_exposure)}`;
    if (r.kind === "WRITE_OFF") return `Facture ${p.number} (${p.customer}) : ${money(p.amount)} à passer en perte`;
    if (r.kind === "PAYMENT_CANCEL") return `Règlement ${p.number} de ${money(p.amount)}`;
    if (r.kind === "CUSTOMER_BLOCK") return `Statut ${p.old} → ${p.status}`;
    return JSON.stringify(p);
  };
  return (
    <>
      <PageHeader title="Approbations" subtitle="Opérations sensibles soumises à la validation d'une seconde personne (principe des « quatre yeux »)" />
      <Card withBorder radius="md">
        <Group justify="space-between" mb="sm">
          <SegmentedControl value={status} onChange={setStatus} data={[{ value: "EN_ATTENTE", label: "En attente" }, { value: "APPROUVEE", label: "Approuvées" }, { value: "REJETEE", label: "Rejetées" }, { value: "", label: "Toutes" }]} />
          {can("approvals.decide") && status === "EN_ATTENTE" && <Textarea placeholder="Commentaire de décision (facultatif)" value={comment} onChange={(e) => setComment(e.currentTarget.value)} w={360} autosize />}
        </Group>
        <DataTable rows={data} columns={[
          { key: "requested_at", label: "Demandé le", render: (r) => datetime(r.requested_at) }, { key: "kind_label", label: "Nature" },
          { key: "payload", label: "Objet", render: (r) => <Text size="sm" style={{ cursor: "pointer" }} c="brand.7" onClick={() => nav(link(r))}>{describe(r)}</Text> },
          { key: "reason", label: "Motif", render: (r) => <Text size="xs">{r.reason}</Text> }, { key: "requested_by", label: "Demandeur" },
          { key: "status", label: "Statut", render: (r) => <StatusBadge code={r.status} label={r.status.replace("_", " ").toLowerCase()} /> },
          { key: "decided_by", label: "Décision", render: (r) => (r.decided_by ? `${r.decided_by} · ${datetime(r.decided_at)}${r.decision_comment ? ` · ${r.decision_comment}` : ""}` : "—") },
          { key: "act", label: "", sortable: false, render: (r) => r.status === "EN_ATTENTE" && can("approvals.decide") && (r.requested_by_id === user?.id
              ? <Text size="xs" c="dimmed">votre demande</Text>
              : <Group gap={4} wrap="nowrap"><Button size="compact-xs" color="red" variant="light" onClick={() => decide.mutate({ id: r.id, approve: false })}>Rejeter</Button>
                  <Button size="compact-xs" onClick={() => decide.mutate({ id: r.id, approve: true })}>Approuver</Button></Group>) },
        ]} />
      </Card>
    </>
  );
}
