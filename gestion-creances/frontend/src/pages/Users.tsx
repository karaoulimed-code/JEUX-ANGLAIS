import { useState } from "react";
import { Badge, Button, Card, Checkbox, Group, Modal, PasswordInput, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { IconPlus } from "@tabler/icons-react";
import { api } from "../api";
import { useQ } from "../hooks";
import { datetime } from "../format";
import { DataTable, PageHeader, useAction } from "../components/ui";

export default function Users() {
  const { data = [] } = useQ<any[]>(["users"], "/users");
  const roles = useQ<any[]>(["roles"], "/roles");
  const [edit, setEdit] = useState<any>(null);
  const save = useAction((v: any) => (v.id ? api(`/users/${v.id}`, { method: "PUT", body: v.body }) : api("/users", { body: v.body })), "Utilisateur enregistré", () => setEdit(null));
  return (
    <>
      <PageHeader title="Utilisateurs et rôles" subtitle="Séparation des responsabilités : chaque rôle n'accède qu'aux opérations de sa fonction"
                  actions={<Button leftSection={<IconPlus size={16} />} onClick={() => setEdit({ is_active: true, role: "LECTURE" })}>Nouvel utilisateur</Button>} />
      <Card withBorder radius="md" mb="md">
        <DataTable rows={data} onRowClick={(r) => setEdit({ ...r, password: "" })} columns={[
          { key: "username", label: "Identifiant" }, { key: "full_name", label: "Nom" }, { key: "role_label", label: "Rôle" }, { key: "email", label: "E-mail" },
          { key: "is_active", label: "État", render: (r) => (r.is_active ? (r.locked ? <Badge color="orange">verrouillé</Badge> : <Badge color="teal">actif</Badge>) : <Badge color="gray">désactivé</Badge>) },
          { key: "last_login_at", label: "Dernière connexion", render: (r) => datetime(r.last_login_at) },
        ]} />
      </Card>
      <Card withBorder radius="md">
        <Text fw={600} mb="xs">Matrice des droits</Text>
        <Table fz="xs" withTableBorder>
          <Table.Thead><Table.Tr><Table.Th>Rôle</Table.Th><Table.Th>Permissions</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{(roles.data || []).map((r) => <Table.Tr key={r.code}><Table.Td fw={600}>{r.label}</Table.Td><Table.Td>{r.permissions.join(" · ")}</Table.Td></Table.Tr>)}</Table.Tbody>
        </Table>
      </Card>
      <Modal opened={!!edit} onClose={() => setEdit(null)} title={edit?.id ? `Modifier ${edit.username}` : "Nouvel utilisateur"}>
        {edit && <Stack>
          <TextInput label="Identifiant" value={edit.username || ""} disabled={!!edit.id} onChange={(e) => setEdit({ ...edit, username: e.currentTarget.value })} />
          <TextInput label="Nom complet" value={edit.full_name || ""} onChange={(e) => setEdit({ ...edit, full_name: e.currentTarget.value })} />
          <TextInput label="E-mail" value={edit.email || ""} onChange={(e) => setEdit({ ...edit, email: e.currentTarget.value })} />
          <Select label="Rôle" data={(roles.data || []).map((r) => ({ value: r.code, label: r.label }))} value={edit.role} onChange={(v) => setEdit({ ...edit, role: v })} />
          <PasswordInput label={edit.id ? "Réinitialiser le mot de passe (facultatif)" : "Mot de passe initial"} description="10 caractères min., majuscule, minuscule, chiffre. Changement imposé à la 1re connexion."
                         value={edit.password || ""} onChange={(e) => setEdit({ ...edit, password: e.currentTarget.value })} />
          <Checkbox label="Compte actif" checked={!!edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.currentTarget.checked })} />
          <Group justify="flex-end"><Button loading={save.isPending} onClick={() => save.mutate({ id: edit.id, body: { username: edit.username, full_name: edit.full_name, email: edit.email || null, role: edit.role, password: edit.password || null, is_active: edit.is_active } })}>Enregistrer</Button></Group>
        </Stack>}
      </Modal>
    </>
  );
}
