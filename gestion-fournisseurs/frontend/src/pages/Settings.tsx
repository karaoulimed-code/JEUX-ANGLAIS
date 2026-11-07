import { useState } from "react";
import { api } from "../api";
import { dt, dtime, today } from "../format";
import { Badge, Card, DataTable, Field, Loading, Modal, Tabs, useAction, useCan, useLoad } from "../components/ui";

export function Settings() {
  const [tab, setTab] = useState("gestion");
  const [settings, reloadS] = useLoad(() => api.get("/api/admin/settings"), []);
  const [rates, reloadR] = useLoad(() => api.get("/api/admin/tax-rates"), []);
  const [accounts, reloadA] = useLoad(() => api.get("/api/admin/accounts"), []);
  const [fx, reloadF] = useLoad(() => api.get("/api/admin/fx-rates"), []);
  const [users, reloadU] = useLoad(() => api.get("/api/auth/users"), []);
  const [roles] = useLoad(() => api.get("/api/auth/roles"), []);
  const [modal, setModal] = useState<any>(null);
  const can = useCan();
  const act = useAction();
  const manage = can("settings.manage");
  return (
    <div>
      <h2>Paramètres</h2>
      <div className="alert warn">Les taux fiscaux livrés ont été relevés le 07/11/2026 à partir de sources secondaires et sont marqués « à vérifier » :
        faites-les confirmer par l'expert-comptable avant la mise en production. Pour un changement de taux, clôturez l'ancien (date de fin) et créez le nouveau.</div>
      <Tabs active={tab} onChange={setTab} tabs={[["gestion", "Règles de gestion"], ["taux", "Taux (TVA, RS, timbre)"], ["comptes", "Plan de comptes"], ["devises", "Cours de change"], ["users", "Utilisateurs"], ["droits", "Matrice des droits"]]} />
      {tab === "gestion" && <Card>{!settings ? <Loading /> : <DataTable rows={settings} cols={[{ key: "label", label: "Paramètre" }, { key: "value", label: "Valeur" },
        { key: "defaut", label: "Défaut" }, { key: "e", label: "", render: (r) => manage && <button className="btn sm" onClick={async () => {
          const v = prompt(`${r.label}\nNouvelle valeur :`, r.value); if (v === null) return;
          if (await act(() => api.put(`/api/admin/settings/${r.key}`, { value: v }), "Paramètre modifié")) reloadS(); }}>Modifier</button> }]} />}</Card>}
      {tab === "taux" && <Card actions={manage && <button className="btn" onClick={() => setModal({ k: "rate", v: { kind: "RS", code: "", label: "", rate: "0", fixed_amount: "0", threshold: "0", valid_from: today(), legal_reference: "", to_verify: true } })}>+ Taux</button>}>
        {!rates ? <Loading /> : <DataTable rows={rates} cols={[{ key: "kind", label: "Nature" }, { key: "code", label: "Code" }, { key: "label", label: "Libellé" },
          { key: "rate", label: "Taux %", kind: "num" }, { key: "fixed_amount", label: "Montant fixe", kind: "money" }, { key: "threshold", label: "Seuil TTC", kind: "money" },
          { key: "valid_from", label: "Depuis", kind: "date" }, { key: "valid_to", label: "Jusqu'au", kind: "date" },
          { key: "to_verify", label: "Vérification", render: (r) => r.to_verify ? <span className="badge warn">À vérifier (relevé {dt(r.verified_on)})</span> : <Badge v="verifie" /> },
          { key: "legal_reference", label: "Référence" },
          { key: "e", label: "", render: (r) => manage && <button className="btn sm" onClick={() => setModal({ k: "rate", v: { ...r } })}>Modifier</button> }]} />}</Card>}
      {tab === "comptes" && <Card>{!accounts ? <Loading /> : <DataTable rows={accounts} cols={[{ key: "label", label: "Rôle" }, { key: "account_code", label: "Compte" },
        { key: "defaut", label: "Défaut SCE" }, { key: "e", label: "", render: (r) => manage && <button className="btn sm" onClick={async () => {
          const v = prompt(`${r.label} — numéro de compte :`, r.account_code); if (!v) return;
          if (await act(() => api.put(`/api/admin/accounts/${r.key}`, { account_code: v }), "Compte modifié")) reloadA(); }}>Modifier</button> }]} />}</Card>}
      {tab === "devises" && <Card actions={<button className="btn" onClick={() => setModal({ k: "fx", v: { currency: "EUR", rate_date: today(), rate: "", source: "BCT" } })}>+ Cours</button>}>
        <p className="muted">Saisir le cours BCT (1 unité de devise = x TND). Le cours applicable est le dernier connu à la date de l'opération.</p>
        {!fx ? <Loading /> : <DataTable rows={fx} cols={[{ key: "currency", label: "Devise" }, { key: "rate_date", label: "Date", kind: "date" }, { key: "rate", label: "Cours" }, { key: "source", label: "Source" }]} />}</Card>}
      {tab === "users" && <Card actions={can("users.manage") && <button className="btn" onClick={() => setModal({ k: "user", v: { email: "", full_name: "", role: "agent_compta", password: "" } })}>+ Utilisateur</button>}>
        {!users ? <Loading /> : <DataTable rows={users} cols={[{ key: "full_name", label: "Nom" }, { key: "email", label: "E-mail" },
          { key: "role", label: "Profil", render: (r) => roles?.roles[r.role] || r.role }, { key: "is_active", label: "Actif", render: (r) => r.is_active ? "Oui" : "Non" },
          { key: "last_login", label: "Dernière connexion", render: (r) => dtime(r.last_login) },
          { key: "e", label: "", render: (r) => can("users.manage") && <div className="row gap">
            <button className="btn sm" onClick={async () => { const role = prompt(`Profil (${Object.keys(roles?.roles || {}).join(", ")})`, r.role); if (role && await act(() => api.patch(`/api/auth/users/${r.id}`, { role }), "Profil modifié")) reloadU(); }}>Profil</button>
            <button className="btn sm" onClick={async () => { if (await act(() => api.patch(`/api/auth/users/${r.id}`, { is_active: !r.is_active }), "Statut modifié")) reloadU(); }}>{r.is_active ? "Désactiver" : "Activer"}</button>
            <button className="btn sm" onClick={async () => { const p = prompt("Nouveau mot de passe (10 caractères, lettres et chiffres)"); if (p && await act(() => api.patch(`/api/auth/users/${r.id}`, { password: p }), "Mot de passe réinitialisé")) reloadU(); }}>Mot de passe</button></div> }]} />}</Card>}
      {tab === "droits" && <Card>{!roles ? <Loading /> : <DataTable filter={false} rows={roles.matrice} cols={[{ key: "permission", label: "Permission" },
        ...Object.entries(roles.roles).map(([k, l]) => ({ key: k, label: String(l), render: (r: any) => r[k] ? "✔" : "" }))]} />}</Card>}

      {modal?.k === "rate" && <Modal title="Taux paramétrable" onClose={() => setModal(null)}>
        <div className="form-grid">{[["kind", "Nature (TVA, RS, TIMBRE, AUTRE)"], ["code", "Code"], ["label", "Libellé"], ["rate", "Taux %"], ["fixed_amount", "Montant fixe"], ["threshold", "Seuil TTC"],
          ["valid_from", "Valable du (AAAA-MM-JJ)"], ["valid_to", "au (optionnel)"], ["account_code", "Compte"], ["legal_reference", "Référence légale"], ["verified_on", "Vérifié le"]].map(([k, l]) =>
          <Field key={k} label={l}><input value={modal.v[k] ?? ""} onChange={(e) => setModal({ ...modal, v: { ...modal.v, [k]: e.target.value } })} /></Field>)}
          <Field label="À vérifier"><input type="checkbox" checked={!!modal.v.to_verify} onChange={(e) => setModal({ ...modal, v: { ...modal.v, to_verify: e.target.checked } })} /></Field></div>
        <div className="modal-actions"><button className="btn primary" onClick={async () => {
          const v = modal.v; const body: any = { kind: v.kind, code: v.code, label: v.label, rate: v.rate, fixed_amount: v.fixed_amount, threshold: v.threshold,
            valid_from: v.valid_from, valid_to: v.valid_to || null, account_code: v.account_code || null, legal_reference: v.legal_reference || null,
            verified_on: v.verified_on || null, to_verify: !!v.to_verify, is_active: v.is_active ?? true };
          if (await act(() => v.id ? api.patch(`/api/admin/tax-rates/${v.id}`, body) : api.post("/api/admin/tax-rates", body), "Taux enregistré")) { setModal(null); reloadR(); } }}>Enregistrer</button></div>
      </Modal>}
      {modal?.k === "fx" && <Modal title="Cours de change" onClose={() => setModal(null)}>
        <div className="form-grid">{[["currency", "Devise"], ["rate_date", "Date"], ["rate", "Cours (TND)"], ["source", "Source"]].map(([k, l]) =>
          <Field key={k} label={l}><input type={k === "rate_date" ? "date" : "text"} value={modal.v[k]} onChange={(e) => setModal({ ...modal, v: { ...modal.v, [k]: e.target.value } })} /></Field>)}</div>
        <div className="modal-actions"><button className="btn primary" onClick={async () => { if (await act(() => api.post("/api/admin/fx-rates", modal.v), "Cours enregistré")) { setModal(null); reloadF(); } }}>Enregistrer</button></div>
      </Modal>}
      {modal?.k === "user" && <Modal title="Nouvel utilisateur" onClose={() => setModal(null)}>
        <div className="form-grid">{[["full_name", "Nom"], ["email", "E-mail"], ["password", "Mot de passe initial"]].map(([k, l]) =>
          <Field key={k} label={l}><input type={k === "password" ? "password" : "text"} value={modal.v[k]} onChange={(e) => setModal({ ...modal, v: { ...modal.v, [k]: e.target.value } })} /></Field>)}
          <Field label="Profil"><select value={modal.v.role} onChange={(e) => setModal({ ...modal, v: { ...modal.v, role: e.target.value } })}>
            {Object.entries(roles?.roles || {}).map(([k, l]) => <option key={k} value={k}>{String(l)}</option>)}</select></Field></div>
        <div className="modal-actions"><button className="btn primary" onClick={async () => { if (await act(() => api.post("/api/auth/users", modal.v), "Utilisateur créé")) { setModal(null); reloadU(); } }}>Créer</button></div>
      </Modal>}
    </div>
  );
}

export function Audit() {
  const [entity, setEntity] = useState("");
  const [rows, , , err] = useLoad(() => api.get(`/api/admin/audit?entity=${entity}`), [entity]);
  const [check, setCheck] = useState<any>(null);
  const act = useAction();
  return (
    <div>
      <div className="row between"><h2>Journal d'audit</h2>
        <button className="btn" onClick={async () => setCheck(await act(() => api.get("/api/admin/audit/verify")))}>Contrôler l'intégrité</button></div>
      {check && <div className={`alert ${check.integre ? "ok" : "err"}`}>{check.integre ? `Journal intègre : ${check.lignes_controlees} opérations chaînées contrôlées.`
        : `Rupture de chaîne détectée à l'opération #${check.premiere_rupture_id} : le journal a été altéré.`}</div>}
      <Card>
        <select value={entity} onChange={(e) => setEntity(e.target.value)} style={{ marginBottom: 8 }}><option value="">Tous objets</option>
          {["facture", "fournisseur", "reglement", "bon_commande", "reception", "demande_achat", "litige", "ecriture", "parametre", "taux", "utilisateur"].map((e) => <option key={e}>{e}</option>)}</select>
        {!rows ? <Loading err={err} /> : <DataTable rows={rows} cols={[{ key: "timestamp", label: "Date (UTC)", render: (r) => dtime(r.timestamp) },
          { key: "user_label", label: "Utilisateur" }, { key: "action", label: "Action" }, { key: "entity", label: "Objet" }, { key: "entity_id", label: "Id" },
          { key: "details", label: "Détails", render: (r) => <small>{r.details ? JSON.stringify(r.details).slice(0, 220) : ""}</small> }, { key: "ip", label: "IP" }]} />}
      </Card>
    </div>
  );
}
