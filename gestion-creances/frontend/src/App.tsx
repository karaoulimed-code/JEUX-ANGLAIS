import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  Alert, AppShell, Autocomplete, Avatar, Badge, Burger, Button, Center, Group, Indicator, Loader, Menu, NavLink, Paper, PasswordInput,
  Popover, ScrollArea, Select, Stack, Text, TextInput, Title, useDirection,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import {
  IconAlertTriangle, IconBell, IconBuildingBank, IconCash, IconChartBar, IconChecklist, IconClockHour4, IconFileImport, IconFileInvoice,
  IconGauge, IconLock, IconLogout, IconPhoneCall, IconReportAnalytics, IconScale, IconSettings, IconShieldCheck, IconSparkles, IconUsers,
  IconUserShield, IconBook2,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { api } from "./api";
import { useAuth } from "./auth";
import { useQ } from "./hooks";
import { LANGS } from "./i18n";
import { notifyError, notifyOk } from "./components/ui";
import Dashboard from "./pages/Dashboard";
import Customers, { CustomerDetail } from "./pages/Customers";
import Invoices, { InvoiceDetail, InvoiceForm } from "./pages/Invoices";
import Payments, { PaymentDetail, PaymentForm } from "./pages/Payments";
import Recovery from "./pages/Recovery";
import Aging from "./pages/Aging";
import Risk from "./pages/Risk";
import Provisions from "./pages/Provisions";
import Forecast from "./pages/Forecast";
import Reports from "./pages/Reports";
import Accounting from "./pages/Accounting";
import Approvals from "./pages/Approvals";
import Imports from "./pages/Imports";
import Settings from "./pages/Settings";
import Users from "./pages/Users";
import Audit from "./pages/Audit";

const NAV = [
  { group: "groupPilot", items: [
    { to: "/", key: "dashboard", icon: IconGauge, perm: "dashboard.read", exclude: ["COMMERCIAL"] },
    { to: "/previsions", key: "forecast", icon: IconSparkles, perm: "forecast.read", exclude: ["COMMERCIAL"] },
  ] },
  { group: "groupCycle", items: [
    { to: "/clients", key: "customers", icon: IconUsers, perm: "customers.read" },
    { to: "/factures", key: "invoices", icon: IconFileInvoice, perm: "invoices.read" },
    { to: "/encaissements", key: "payments", icon: IconCash, perm: "payments.read" },
    { to: "/recouvrement", key: "recovery", icon: IconPhoneCall, perm: "dunning.read" },
    { to: "/balance-agee", key: "aging", icon: IconClockHour4, perm: "aging.read" },
    { to: "/risque", key: "risk", icon: IconAlertTriangle, perm: "risk.read" },
    { to: "/provisions", key: "provisions", icon: IconScale, perm: "provisions.read" },
  ] },
  { group: "groupControl", items: [
    { to: "/etats", key: "reports", icon: IconReportAnalytics, perm: "reports.read" },
    { to: "/comptabilite", key: "accounting", icon: IconBook2, perm: "accounting.read" },
    { to: "/approbations", key: "approvals", icon: IconChecklist, perm: null },
    { to: "/imports", key: "imports", icon: IconFileImport, perm: "imports.write" },
  ] },
  { group: "groupAdmin", items: [
    { to: "/parametres", key: "settings", icon: IconSettings, perm: "params.read" },
    { to: "/utilisateurs", key: "users", icon: IconUserShield, perm: "users.manage" },
    { to: "/audit", key: "audit", icon: IconShieldCheck, perm: "audit.read" },
  ] },
];

function Login() {
  const { login } = useAuth();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    try {
      await login(u, p);
    } catch (x: any) {
      setErr(x.message);
    } finally {
      setLoading(false);
    }
  };
  return (
    <Center mih="100vh" bg="var(--mantine-color-brand-9)" p="md">
      <Paper component="form" onSubmit={submit} w={400} maw="100%" p="xl" radius="lg" shadow="xl">
        <Group gap="sm" mb="lg">
          <IconBuildingBank size={34} color="var(--mantine-color-brand-9)" />
          <div>
            <Title order={3}>Poste clients</Title>
            <Text size="sm" c="dimmed">Gestion intégrée des créances</Text>
          </div>
        </Group>
        <Stack>
          <TextInput label="Identifiant" value={u} onChange={(e) => setU(e.currentTarget.value)} autoFocus required autoComplete="username" />
          <PasswordInput label="Mot de passe" value={p} onChange={(e) => setP(e.currentTarget.value)} required autoComplete="current-password" />
          {err && <Alert color="red" icon={<IconLock size={16} />}>{err}</Alert>}
          <Button type="submit" loading={loading} fullWidth>Se connecter</Button>
          <Text size="xs" c="dimmed">Accès réservé aux utilisateurs habilités. Toutes les opérations sont tracées.</Text>
        </Stack>
      </Paper>
    </Center>
  );
}

function ChangePassword() {
  const { refresh, logout } = useAuth();
  const [cur, setCur] = useState("");
  const [n1, setN1] = useState("");
  const [n2, setN2] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async () => {
    if (n1 !== n2) return notifyError({ message: "Les deux mots de passe diffèrent" });
    setLoading(true);
    try {
      await api("/auth/change-password", { body: { current_password: cur, new_password: n1 } });
      notifyOk("Mot de passe modifié");
      await refresh();
    } catch (e) {
      notifyError(e);
    } finally {
      setLoading(false);
    }
  };
  return (
    <Center mih="100vh" p="md">
      <Paper w={420} p="xl" withBorder radius="lg">
        <Title order={4} mb="xs">Changement de mot de passe obligatoire</Title>
        <Text size="sm" c="dimmed" mb="md">Au moins 10 caractères, une majuscule, une minuscule et un chiffre.</Text>
        <Stack>
          <PasswordInput label="Mot de passe actuel" value={cur} onChange={(e) => setCur(e.currentTarget.value)} />
          <PasswordInput label="Nouveau mot de passe" value={n1} onChange={(e) => setN1(e.currentTarget.value)} />
          <PasswordInput label="Confirmation" value={n2} onChange={(e) => setN2(e.currentTarget.value)} />
          <Group justify="space-between">
            <Button variant="subtle" onClick={logout}>Annuler</Button>
            <Button onClick={submit} loading={loading}>Valider</Button>
          </Group>
        </Stack>
      </Paper>
    </Center>
  );
}

function GlobalSearch() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [dq] = useDebouncedValue(q, 250);
  const [opts, setOpts] = useState<{ value: string; label: string }[]>([]);
  useEffect(() => {
    if (dq.length < 2) return setOpts([]);
    Promise.all([
      api(`/customers?q=${encodeURIComponent(dq)}&limit=6&with_balance=false`).catch(() => ({ rows: [] })),
      api(`/invoices?q=${encodeURIComponent(dq)}&limit=6`).catch(() => ({ rows: [] })),
    ]).then(([c, i]) => setOpts([
      ...c.rows.map((x: any) => ({ value: `/clients/${x.id}`, label: `Client · ${x.code} · ${x.legal_name}` })),
      ...i.rows.map((x: any) => ({ value: `/factures/${x.id}`, label: `${x.doc_type === "AVOIR" ? "Avoir" : "Facture"} · ${x.number || "brouillon"} · ${x.customer_name}` })),
    ]));
  }, [dq]);
  return (
    <Autocomplete placeholder={t("common.search")} value={q} onChange={setQ} data={opts} filter={({ options }) => options}
                  onOptionSubmit={(v) => { nav(v); setQ(""); }} w={{ base: 150, sm: 380 }} limit={12} />
  );
}

function Alerts() {
  const nav = useNavigate();
  const { data = [] } = useQ<any[]>(["alerts"], "/alerts");
  const color = (l: string) => (l === "error" ? "red" : l === "warning" ? "orange" : "blue");
  return (
    <Popover width={380} position="bottom-end" shadow="md">
      <Popover.Target>
        <Indicator disabled={!data.length} label={data.length} size={16} color="red">
          <Button variant="subtle" px={8} aria-label="Alertes"><IconBell size={20} /></Button>
        </Indicator>
      </Popover.Target>
      <Popover.Dropdown>
        <Text fw={600} mb="xs">Alertes et notifications</Text>
        <ScrollArea.Autosize mah={400}>
          <Stack gap={6}>
            {!data.length && <Text size="sm" c="dimmed">Aucune alerte.</Text>}
            {data.map((a, i) => (
              <Alert key={i} color={color(a.level)} p="xs" style={{ cursor: a.link || a.customer_id ? "pointer" : undefined }}
                     onClick={() => a.link ? nav(a.link) : a.customer_id && nav(`/clients/${a.customer_id}`)}>
                <Text size="sm">{a.message}</Text>
              </Alert>
            ))}
          </Stack>
        </ScrollArea.Autosize>
      </Popover.Dropdown>
    </Popover>
  );
}

export default function App() {
  const { user, loading, can, logout } = useAuth();
  const { t, i18n } = useTranslation();
  const { setDirection } = useDirection();
  const [opened, { toggle, close }] = useDisclosure();
  const loc = useLocation();
  useEffect(() => close(), [loc.pathname, close]);
  useEffect(() => {
    const l = LANGS.find((x) => x.code === i18n.language) || LANGS[0];
    document.documentElement.dir = l.dir;
    document.documentElement.lang = l.code;
    setDirection(l.dir);
  }, [i18n.language, setDirection]);

  if (loading) return <Center mih="100vh"><Loader /></Center>;
  if (!user) return <Login />;
  if (user.must_change_password) return <ChangePassword />;
  const home = can("dashboard.read") && user.role !== "COMMERCIAL" ? "/" : "/clients";

  return (
    <AppShell header={{ height: 58 }} navbar={{ width: 250, breakpoint: "md", collapsed: { mobile: !opened } }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="md" size="sm" />
            <IconBuildingBank size={26} color="var(--mantine-color-brand-9)" />
            <Stack gap={0} style={{ lineHeight: 1.1 }} visibleFrom="sm">
              <Text fw={700} c="var(--mantine-color-brand-9)">{t("app.name")}</Text>
              <Text size="xs" c="dimmed">{t("app.subtitle")}</Text>
            </Stack>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <GlobalSearch />
            <Alerts />
            <Menu position="bottom-end" shadow="md">
              <Menu.Target>
                <Button variant="subtle" px={6} leftSection={<Avatar size={28} color="brand" radius="xl">{user.full_name.slice(0, 1)}</Avatar>}>
                  <Text size="sm" visibleFrom="sm">{user.full_name}</Text>
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>{user.role_label}</Menu.Label>
                <Menu.Item component="div" closeMenuOnClick={false}>
                  <Select size="xs" value={i18n.language} data={LANGS.map((l) => ({ value: l.code, label: l.label }))}
                          onChange={(v) => { if (v) { i18n.changeLanguage(v); localStorage.setItem("gpc_lang", v); } }} />
                </Menu.Item>
                <Menu.Item leftSection={<IconLogout size={16} />} color="red" onClick={logout}>{t("common.logout")}</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        <AppShell.Section grow component={ScrollArea}>
          {NAV.map((g) => {
            const items = g.items.filter((it) => (!it.perm || can(it.perm)) && !(it as any).exclude?.includes(user.role));
            if (!items.length) return null;
            return (
              <div key={g.group}>
                <div className="nav-section">{t(`nav.${g.group}`)}</div>
                {items.map((it) => (
                  <NavLink key={it.to} label={t(`nav.${it.key}`)} leftSection={<it.icon size={18} stroke={1.6} />}
                           active={it.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(it.to)}
                           component={Link} to={it.to} style={{ borderRadius: 8 }} />
                ))}
              </div>
            );
          })}
        </AppShell.Section>
        <AppShell.Section>
          <Badge variant="light" color="gray" fullWidth radius="sm">v1.0 · TND · {new Date().toLocaleDateString("fr-FR")}</Badge>
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main>
        <Routes>
          <Route path="/" element={home === "/" ? <Dashboard /> : <Navigate to={home} />} />
          <Route path="/clients" element={<Customers />} />
          <Route path="/clients/:id" element={<CustomerDetail />} />
          <Route path="/factures" element={<Invoices />} />
          <Route path="/factures/nouvelle" element={<InvoiceForm />} />
          <Route path="/factures/:id/modifier" element={<InvoiceForm />} />
          <Route path="/factures/:id" element={<InvoiceDetail />} />
          <Route path="/encaissements" element={<Payments />} />
          <Route path="/encaissements/nouveau" element={<PaymentForm />} />
          <Route path="/encaissements/:id" element={<PaymentDetail />} />
          <Route path="/recouvrement" element={<Recovery />} />
          <Route path="/balance-agee" element={<Aging />} />
          <Route path="/risque" element={<Risk />} />
          <Route path="/provisions" element={<Provisions />} />
          <Route path="/previsions" element={<Forecast />} />
          <Route path="/etats" element={<Reports />} />
          <Route path="/comptabilite" element={<Accounting />} />
          <Route path="/approbations" element={<Approvals />} />
          <Route path="/imports" element={<Imports />} />
          <Route path="/parametres" element={<Settings />} />
          <Route path="/utilisateurs" element={<Users />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="*" element={<Center h={300}><Stack align="center"><IconChartBar size={40} /><Text>Page introuvable</Text></Stack></Center>} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}
