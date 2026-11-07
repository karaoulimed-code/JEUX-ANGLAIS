import { useMemo, useState } from "react";
import {
  ActionIcon, Badge, Box, Button, Card, Group, Menu, Modal, Pagination, ScrollArea, Stack, Table, Text, Textarea, TextInput, Title, Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { IconArrowDown, IconArrowUp, IconDownload, IconFileSpreadsheet, IconFileTypePdf, IconFileTypeCsv, IconSearch } from "@tabler/icons-react";
import { download } from "../api";
import { money, STATUS_COLORS, STATUS_LABELS } from "../format";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" mb="md" wrap="wrap">
      <div>
        <Title order={2} fw={650} c="var(--mantine-color-brand-9)">{title}</Title>
        {subtitle && (typeof subtitle === "string" ? <Text c="dimmed" size="sm">{subtitle}</Text> : <div>{subtitle}</div>)}
      </div>
      <Group gap="xs">{actions}</Group>
    </Group>
  );
}

export function StatusBadge({ code, label }: { code?: string | null; label?: string | null }) {
  if (!code) return <Text c="dimmed" size="sm">—</Text>;
  return (
    <Badge variant="light" color={STATUS_COLORS[code] || "gray"} radius="sm"
           styles={{ root: { maxWidth: "none", flexShrink: 0 }, label: { overflow: "visible", textOverflow: "clip" } }}>
      {label || STATUS_LABELS[code] || code.replaceAll("_", " ").toLowerCase()}
    </Badge>
  );
}

export function Amount({ v, currency, strong, color }: { v: any; currency?: string; strong?: boolean; color?: string }) {
  const n = Number(v);
  return (
    <Text component="span" ff="var(--mantine-font-family-monospace)" fw={strong ? 700 : 400} size="sm"
          c={color || (n < 0 ? "red.7" : undefined)} style={{ whiteSpace: "nowrap" }}>
      {money(v, currency)}
    </Text>
  );
}

export function Kpi({ label, value, hint, color, icon }: { label: string; value: React.ReactNode; hint?: React.ReactNode; color?: string; icon?: React.ReactNode }) {
  return (
    <Card withBorder radius="md" padding="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
        {icon}
      </Group>
      <Text fw={700} size="xl" mt={4} c={color} ff="var(--mantine-font-family-monospace)" style={{ whiteSpace: "nowrap" }}>{value}</Text>
      {hint && <Text size="xs" c="dimmed" mt={2}>{hint}</Text>}
    </Card>
  );
}

export type Col<T> = {
  key: string; label: string; render?: (r: T) => React.ReactNode; align?: "left" | "right" | "center"; sortable?: boolean;
  sortValue?: (r: T) => any; width?: number | string;
};

export function DataTable<T extends Record<string, any>>({
  rows, columns, onRowClick, pageSize = 25, searchable = true, empty = "Aucune donnée", footer, loading, rowKey = "id",
}: {
  rows: T[]; columns: Col<T>[]; onRowClick?: (r: T) => void; pageSize?: number; searchable?: boolean; empty?: string;
  footer?: React.ReactNode; loading?: boolean; rowKey?: string;
}) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [page, setPage] = useState(1);
  const filtered = useMemo(() => {
    let r = rows || [];
    if (q) {
      const s = q.toLowerCase();
      r = r.filter((x) => Object.values(x).some((v) => v !== null && typeof v !== "object" && String(v).toLowerCase().includes(s)));
    }
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      const get = col?.sortValue || ((x: any) => x[sort.key]);
      r = [...r].sort((a, b) => {
        const va = get(a), vb = get(b);
        const na = Number(va), nb = Number(vb);
        const cmp = !Number.isNaN(na) && !Number.isNaN(nb) && va !== null && vb !== null && va !== "" ? na - nb : String(va ?? "").localeCompare(String(vb ?? ""), "fr");
        return cmp * sort.dir;
      });
    }
    return r;
  }, [rows, q, sort, columns]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const view = filtered.slice((page - 1) * pageSize, page * pageSize);
  return (
    <Stack gap="xs">
      {searchable && (
        <TextInput leftSection={<IconSearch size={16} />} placeholder="Filtrer le tableau…" value={q} size="sm" maw={340}
                   onChange={(e) => { setQ(e.currentTarget.value); setPage(1); }} />
      )}
      <ScrollArea type="auto">
        <Table striped highlightOnHover withTableBorder verticalSpacing={6} fz="sm" miw={columns.length * 95}>
          <Table.Thead bg="var(--mantine-color-brand-0)">
            <Table.Tr>
              {columns.map((c) => (
                <Table.Th key={c.key} style={{ textAlign: c.align || "left", cursor: c.sortable !== false ? "pointer" : undefined, width: c.width, whiteSpace: "nowrap" }}
                          onClick={() => c.sortable !== false && setSort((s) => (s?.key === c.key ? { key: c.key, dir: (s.dir * -1) as 1 | -1 } : { key: c.key, dir: 1 }))}>
                  <Group gap={4} wrap="nowrap" justify={c.align === "right" ? "flex-end" : "flex-start"}>
                    {c.label}
                    {sort?.key === c.key && (sort.dir === 1 ? <IconArrowUp size={12} /> : <IconArrowDown size={12} />)}
                  </Group>
                </Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {view.map((r, i) => (
              <Table.Tr key={r[rowKey] ?? i} onClick={() => onRowClick?.(r)} style={{ cursor: onRowClick ? "pointer" : undefined }}>
                {columns.map((c) => (
                  <Table.Td key={c.key} style={{ textAlign: c.align || "left" }}>{c.render ? c.render(r) : (r[c.key] ?? "—")}</Table.Td>
                ))}
              </Table.Tr>
            ))}
            {!view.length && (
              <Table.Tr><Table.Td colSpan={columns.length}><Text c="dimmed" ta="center" py="md">{loading ? "Chargement…" : empty}</Text></Table.Td></Table.Tr>
            )}
          </Table.Tbody>
          {footer && <Table.Tfoot>{footer}</Table.Tfoot>}
        </Table>
      </ScrollArea>
      <Group justify="space-between">
        <Text size="xs" c="dimmed">{filtered.length} ligne(s)</Text>
        {pages > 1 && <Pagination size="sm" total={pages} value={page} onChange={setPage} />}
      </Group>
    </Stack>
  );
}

export function notifyError(e: any) {
  notifications.show({ color: "red", title: "Opération refusée", message: e?.message || String(e), autoClose: 8000 });
}
export function notifyOk(message: string) {
  notifications.show({ color: "green", title: "Opération effectuée", message });
}

/** Mutation avec notification et rafraîchissement global des données : toute
 * opération met à jour l'ensemble des vues (soldes, balance âgée, risque…). */
export function useAction<V = any>(fn: (v: V) => Promise<any>, success?: string | ((r: any) => string), after?: (r: any) => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      qc.invalidateQueries();
      if (success) notifyOk(typeof success === "function" ? success(r) : success);
      after?.(r);
    },
    onError: notifyError,
  });
}

export function ExportMenu({ path, label = "Exporter" }: { path: string; label?: string }) {
  const sep = path.includes("?") ? "&" : "?";
  const go = (fmt: string) => download(`${path}${sep}format=${fmt}`).catch(notifyError);
  return (
    <Menu shadow="md" position="bottom-end">
      <Menu.Target><Button variant="default" leftSection={<IconDownload size={16} />}>{label}</Button></Menu.Target>
      <Menu.Dropdown>
        <Menu.Item leftSection={<IconFileSpreadsheet size={16} />} onClick={() => go("xlsx")}>Excel (.xlsx)</Menu.Item>
        <Menu.Item leftSection={<IconFileTypePdf size={16} />} onClick={() => go("pdf")}>PDF</Menu.Item>
        <Menu.Item leftSection={<IconFileTypeCsv size={16} />} onClick={() => go("csv")}>CSV</Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

export function ReasonModal({ opened, onClose, title, label = "Motif (obligatoire)", onSubmit, loading, color = "blue", confirm = "Confirmer", children }: {
  opened: boolean; onClose: () => void; title: string; label?: string; onSubmit: (reason: string) => void; loading?: boolean; color?: string;
  confirm?: string; children?: React.ReactNode;
}) {
  const [reason, setReason] = useState("");
  return (
    <Modal opened={opened} onClose={onClose} title={title} centered>
      <Stack>
        {children}
        <Textarea label={label} minRows={3} autosize value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Annuler</Button>
          <Button color={color} loading={loading} disabled={reason.trim().length < 5} onClick={() => onSubmit(reason)}>{confirm}</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
      <Text size="sm" component="div">{children ?? "—"}</Text>
    </Box>
  );
}

export function IconBtn({ label, onClick, children, color }: { label: string; onClick: () => void; children: React.ReactNode; color?: string }) {
  return <Tooltip label={label}><ActionIcon variant="subtle" color={color} onClick={onClick} aria-label={label}>{children}</ActionIcon></Tooltip>;
}
