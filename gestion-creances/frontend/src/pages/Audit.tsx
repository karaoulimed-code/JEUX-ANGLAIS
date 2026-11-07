import { useState } from "react";
import { Alert, Button, Card, Code, Group, TextInput } from "@mantine/core";
import { IconShieldCheck } from "@tabler/icons-react";
import { qs } from "../api";
import { useQ } from "../hooks";
import { datetime } from "../format";
import { DataTable, PageHeader } from "../components/ui";

export default function Audit() {
  const [f, setF] = useState<any>({});
  const { data = [] } = useQ<any[]>(["audit", f], `/audit${qs({ ...f, limit: 1000 })}`);
  const [check, setCheck] = useState(false);
  const v = useQ<any>(["audit-verify"], check ? "/audit/verify" : null);
  return (
    <>
      <PageHeader title="Journal d'audit" subtitle="Inaltérable : protégé par la base de données et chaîné par empreintes cryptographiques (SHA-256)"
                  actions={<Button leftSection={<IconShieldCheck size={16} />} onClick={() => { setCheck(true); v.refetch(); }}>Vérifier l'intégrité</Button>} />
      {v.data && <Alert mb="md" color={v.data.ok ? "teal" : "red"}>{v.data.ok ? `Chaîne intègre : ${v.data.checked} enregistrements vérifiés.` : `Rupture de la chaîne à l'enregistrement n° ${v.data.broken_at_id} : altération détectée.`}</Alert>}
      <Card withBorder radius="md">
        <Group mb="sm">
          <TextInput placeholder="Utilisateur" value={f.username || ""} onChange={(e) => setF({ ...f, username: e.currentTarget.value || undefined })} w={160} />
          <TextInput placeholder="Opération (ex. PAYMENT)" value={f.action || ""} onChange={(e) => setF({ ...f, action: e.currentTarget.value || undefined })} w={200} />
          <TextInput placeholder="Type d'objet (invoice, customer…)" value={f.entity_type || ""} onChange={(e) => setF({ ...f, entity_type: e.currentTarget.value || undefined })} w={220} />
        </Group>
        <DataTable rows={data} pageSize={50} columns={[
          { key: "id", label: "N°" }, { key: "ts", label: "Horodatage", render: (r) => datetime(r.ts) }, { key: "username", label: "Utilisateur" },
          { key: "action", label: "Opération" }, { key: "entity_type", label: "Objet", render: (r) => `${r.entity_type} ${r.entity_id || ""}` },
          { key: "details", label: "Détail", render: (r) => <Code block style={{ maxWidth: 520, maxHeight: 90, overflow: "auto", fontSize: 11 }}>{JSON.stringify(r.details)}</Code> },
          { key: "ip", label: "IP" }, { key: "hash", label: "Empreinte", render: (r) => <Code>{r.hash}</Code> },
        ]} />
      </Card>
    </>
  );
}
