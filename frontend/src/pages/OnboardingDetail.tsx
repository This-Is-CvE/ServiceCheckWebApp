import { FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, downloadPdf } from "../api";
import { Asset, Onboarding, OnboardingItem, Section, SECTION_LABEL } from "../types";
import { ErrorBox, Field, fmtDate, Modal, StatusPill, useAsync } from "../ui";

const ASSET_CATEGORIES = ["Server/Host", "Storage", "Netzwerk", "Virtualisierung", "Backup", "Betriebssystem", "Sonstiges"];
const emptyAsset = { category: "Server/Host", name: "", product_version: "", quantity: 1, location: "", notes: "" };

function GeneralField({ item, locked, onSave }: { item: OnboardingItem; locked: boolean; onSave: (v: string) => void }) {
  const [v, setV] = useState(item.value);
  const props = { value: v, disabled: locked, onChange: (e: any) => setV(e.target.value), onBlur: () => v !== item.value && onSave(v) };
  return (
    <Field label={`${item.label}${item.required ? " *" : ""}`} hint={item.help || undefined}>
      {item.field_type === "textarea" ? <textarea rows={3} {...props} />
        : <input type={item.field_type === "date" ? "date" : "text"} {...props} />}
    </Field>
  );
}

function CheckRow({ item, locked, onChange }: { item: OnboardingItem; locked: boolean; onChange: (p: Partial<OnboardingItem>) => void }) {
  const [comment, setComment] = useState(item.comment);
  return (
    <div className={`check-row ${item.done ? "done" : ""}`}>
      <label>
        <input type="checkbox" checked={item.done} disabled={locked} onChange={(e) => onChange({ done: e.target.checked })} />
        <span>{item.label}{item.required ? " *" : ""}{item.help && <small className="block muted">{item.help}</small>}</span>
      </label>
      <input className="note" placeholder="Notiz / Ablageort" value={comment} disabled={locked}
        onChange={(e) => setComment(e.target.value)} onBlur={() => comment !== item.comment && onChange({ comment })} />
    </div>
  );
}

export default function OnboardingDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: ob, error, setData } = useAsync(() => api<Onboarding>(`/onboardings/${id}`), [id]);
  const [err, setErr] = useState<string | null>(null);
  const [asset, setAsset] = useState<(Partial<Asset> & typeof emptyAsset) | null>(null);

  if (error) return <ErrorBox error={error} />;
  if (!ob) return <div className="muted">Lade …</div>;
  const locked = ob.status === "completed";

  async function run(fn: () => Promise<Onboarding | void>) {
    setErr(null);
    try { const r = await fn(); if (r) setData(r); } catch (x: any) { setErr(x.message); }
  }
  const saveItem = (item: OnboardingItem, patch: Partial<OnboardingItem>) =>
    run(() => api(`/onboardings/${ob.id}/items/${item.id}`, "PUT", patch));
  const saveAsset = async (e: FormEvent) => {
    e.preventDefault();
    if (!asset) return;
    await run(() => asset.id ? api(`/onboardings/${ob.id}/assets/${asset.id}`, "PUT", asset) : api(`/onboardings/${ob.id}/assets`, "POST", asset));
    setAsset(null);
  };
  const sections: Section[] = ["general", "checklist", "readiness"];

  return (
    <>
      <div className="crumbs"><Link to="/onboardings">Onboardings</Link> › {ob.customer_name}</div>
      <div className="row between wrap">
        <div>
          <h1>{ob.title}</h1>
          <div className="muted">{ob.offer_name} · {fmtDate(ob.created_at)} <StatusPill status={ob.status} />
            {ob.service_check_id && <> · <Link to={`/checks/${ob.service_check_id}`}>Service Check ansehen</Link></>}</div>
        </div>
        <div className="row">
          <button className="btn" onClick={() => run(() => downloadPdf(`/onboardings/${ob.id}/report.pdf`))}>PDF herunterladen</button>
          <button className="btn" onClick={() => run(() => api(`/onboardings/${ob.id}/documents`, "POST"))}>PDF ablegen</button>
          {locked
            ? <button className="btn" onClick={() => run(() => api(`/onboardings/${ob.id}/reopen`, "POST"))}>Wieder öffnen</button>
            : <button className="btn primary" onClick={() => run(() => api(`/onboardings/${ob.id}/complete`, "POST"))}>Onboarding abschließen</button>}
          <button className="btn ghost danger" onClick={() => confirm("Onboarding samt abgelegter Dokumente endgültig löschen?") && run(async () => { await api(`/onboardings/${ob.id}`, "DELETE"); nav("/onboardings"); })}>Löschen</button>
        </div>
      </div>
      <ErrorBox error={err} />
      <section className="card">
        <div className="bar big"><i style={{ width: `${ob.progress}%` }} /></div>
        <small className="muted">{Math.round(ob.progress)} % erledigt · {ob.open_required.length === 0 ? "Alle Pflichtpunkte erfüllt – bereit für den Service-Start." : `${ob.open_required.length} Pflichtpunkte offen`}</small>
      </section>

      <section className="card">
        <h2>{SECTION_LABEL.general}</h2>
        <div className="form-grid">
          {ob.items.filter((i) => i.section === "general").map((i) => (
            <GeneralField key={`${i.id}-${i.value}`} item={i} locked={locked} onSave={(value) => saveItem(i, { value })} />
          ))}
        </div>
      </section>

      <section className="card">
        <div className="row between"><h2>Installierte technische Basis</h2>
          {!locked && <button className="btn" onClick={() => setAsset({ ...emptyAsset })}>Eintrag hinzufügen</button>}</div>
        <table>
          <thead><tr><th>Kategorie</th><th>Bezeichnung</th><th>Produkt / Version</th><th>Anz.</th><th>Standort</th><th>Notiz</th><th /></tr></thead>
          <tbody>
            {ob.assets.map((a) => (
              <tr key={a.id}>
                <td>{a.category}</td><td>{a.name}</td><td>{a.product_version}</td><td>{a.quantity}</td><td>{a.location}</td><td>{a.notes}</td>
                <td className="actions">{!locked && <>
                  <button className="btn ghost" onClick={() => setAsset({ ...a })}>Bearbeiten</button>
                  <button className="btn ghost danger" onClick={() => run(() => api(`/onboardings/${ob.id}/assets/${a.id}`, "DELETE"))}>Löschen</button></>}</td>
              </tr>
            ))}
            {!ob.assets.length && <tr><td colSpan={7} className="muted">Noch keine Systeme erfasst (Hosts, Storage, Netzwerk, Hypervisor-Versionen, Backup …).</td></tr>}
          </tbody>
        </table>
      </section>

      {sections.slice(1).map((s) => (
        <section key={s} className="card">
          <h2>{SECTION_LABEL[s]}</h2>
          {ob.items.filter((i) => i.section === s).map((i) => (
            <CheckRow key={`${i.id}-${i.comment}`} item={i} locked={locked} onChange={(p) => saveItem(i, p)} />
          ))}
        </section>
      ))}

      <section className="card">
        <h2>Abgelegte Dokumente</h2>
        <p className="muted">„PDF ablegen“ speichert den aktuellen Stand als unveränderliches Dokument bei diesem Onboarding. Beim Abschluss wird automatisch eines abgelegt.</p>
        <table>
          <tbody>
            {ob.documents.map((d) => (
              <tr key={d.id}>
                <td><a href="#" onClick={(e) => { e.preventDefault(); run(() => downloadPdf(`/onboardings/${ob.id}/documents/${d.id}`)); }}>{d.filename}</a></td>
                <td>{new Date(d.created_at).toLocaleString("de-DE")}</td><td>{d.created_by}</td><td>{Math.max(1, Math.round(d.size / 1024))} kB</td>
                <td className="actions"><button className="btn ghost danger" onClick={() => confirm("Dokument löschen?") && run(() => api(`/onboardings/${ob.id}/documents/${d.id}`, "DELETE"))}>Löschen</button></td>
              </tr>
            ))}
            {!ob.documents.length && <tr><td className="muted">Noch kein Dokument abgelegt.</td></tr>}
          </tbody>
        </table>
      </section>

      {asset && (
        <Modal title={asset.id ? "Eintrag bearbeiten" : "Eintrag hinzufügen"} onClose={() => setAsset(null)}>
          <form onSubmit={saveAsset}>
            <Field label="Kategorie"><select value={asset.category} onChange={(e) => setAsset({ ...asset, category: e.target.value })}>
              {ASSET_CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
            <Field label="Bezeichnung"><input required value={asset.name} onChange={(e) => setAsset({ ...asset, name: e.target.value })} autoFocus placeholder="z. B. Dell PowerEdge R750" /></Field>
            <Field label="Produkt / Version"><input value={asset.product_version} onChange={(e) => setAsset({ ...asset, product_version: e.target.value })} placeholder="z. B. ESXi 8.0 U3" /></Field>
            <Field label="Anzahl"><input type="number" min={1} value={asset.quantity} onChange={(e) => setAsset({ ...asset, quantity: Number(e.target.value) || 1 })} /></Field>
            <Field label="Standort"><input value={asset.location} onChange={(e) => setAsset({ ...asset, location: e.target.value })} /></Field>
            <Field label="Notiz"><textarea rows={2} value={asset.notes} onChange={(e) => setAsset({ ...asset, notes: e.target.value })} /></Field>
            <div className="row end"><button type="button" className="btn" onClick={() => setAsset(null)}>Abbrechen</button><button className="btn primary">Speichern</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}
