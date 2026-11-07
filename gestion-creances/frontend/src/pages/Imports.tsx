import { useState } from "react";
import { Alert, Badge, Button, Card, FileInput, Group, SegmentedControl, Stack, Table, Text, Title } from "@mantine/core";
import { IconDownload, IconFileUpload } from "@tabler/icons-react";
import { api, download } from "../api";
import { PageHeader, notifyError, useAction } from "../components/ui";

export default function Imports() {
  const [kind, setKind] = useState("invoices");
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<any>(null);
  const run = useAction(async (dry: boolean) => {
    const fd = new FormData();
    fd.append("file", file as File);
    fd.append("dry_run", String(dry));
    return api(`/imports/${kind}`, { form: fd, method: "POST" });
  }, (r) => (r.dry_run ? `Simulation : ${r.total} ligne(s), ${r.errors} en erreur` : r.imported ? `${r.imported} ligne(s) importée(s)` : r.message || "Aucune ligne importée"), setRes);
  return (
    <>
      <PageHeader title="Imports" subtitle="Reprise de clients et de factures depuis Excel, CSV ou un autre logiciel" />
      <Card withBorder radius="md" mb="md">
        <Stack>
          <SegmentedControl value={kind} onChange={(v) => { setKind(v); setRes(null); }} data={[{ value: "invoices", label: "Factures et avoirs" }, { value: "customers", label: "Clients" }]} w={340} />
          <Alert color="blue">
            1. Téléchargez le modèle · 2. Complétez-le (dates JJ/MM/AAAA, montants avec virgule ou point) · 3. Lancez une <b>simulation</b> : rien n'est enregistré, chaque ligne est contrôlée
            (client existant, HT + TVA + taxes = TTC, doublons, échéance) · 4. Importez : l'opération est atomique (tout ou rien). Les factures importées sont considérées comme déjà émises et validées ;
            par défaut elles ne génèrent pas d'écritures (déjà comptabilisées dans le logiciel d'origine).
          </Alert>
          <Group align="flex-end">
            <Button variant="default" leftSection={<IconDownload size={16} />} onClick={() => download(`/imports/${kind}/template`).catch(notifyError)}>Modèle Excel</Button>
            <FileInput label="Fichier (.xlsx ou .csv)" accept=".xlsx,.csv" value={file} onChange={setFile} leftSection={<IconFileUpload size={16} />} w={300} />
            <Button variant="light" disabled={!file} onClick={() => run.mutate(true)} loading={run.isPending}>Simuler</Button>
            <Button disabled={!file || !res?.dry_run || res.errors > 0} onClick={() => run.mutate(false)} loading={run.isPending}>Importer</Button>
          </Group>
        </Stack>
      </Card>
      {res && (
        <Card withBorder radius="md">
          <Title order={5} mb="sm">Rapport {res.dry_run ? "de simulation" : "d'import"}</Title>
          <Table fz="sm"><Table.Thead><Table.Tr><Table.Th>Ligne</Table.Th><Table.Th>Référence</Table.Th><Table.Th>Résultat</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{res.lines.map((l: any) => (
              <Table.Tr key={l.line}><Table.Td>{l.line}</Table.Td><Table.Td>{l.number || l.code}</Table.Td>
                <Table.Td>{l.errors.length ? l.errors.map((e: string, i: number) => <Badge key={i} color="red" variant="light" mr={4}>{e}</Badge>) : <Badge color="teal" variant="light">OK</Badge>}
                  {l.warnings.map((w: string, i: number) => <Badge key={i} color="orange" variant="light" ml={4}>{w}</Badge>)}</Table.Td></Table.Tr>))}</Table.Tbody></Table>
          {res.message && <Text c="red" mt="sm">{res.message}</Text>}
        </Card>)}
    </>
  );
}
