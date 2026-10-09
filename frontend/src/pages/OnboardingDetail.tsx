import { FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, downloadPdf } from "../api";
import { Asset, Contact, Onboarding, OnboardingItem, Product, Section, SECTION_LABEL } from "../types";
import { ErrorBox, ExtensionPicker, Field, fmtDate, Modal, StatusPill, useAsync } from "../ui";

const ASSET_CATEGORIES = ["Server/Host", "Storage", "Netzwerk", "Virtualisierung", "Backup", "Betriebssystem", "Sonstiges"];
const emptyContact = { name: "", role: "", phone: "", mobile: "", email: "", notes: "" };
const emptyAsset = { category: "Server/Host", name: "", model: "", serial_number: "", product_version: "", quantity: 1, location: "", notes: "" };

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
        <span>{item.label}{item.required ? " *" : ""}{item.extension_name && <span className="badge ext-tag">{item.extension_name}</span>}{item.help && <small className="block muted">{item.help}</small>}</span>
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
  const product = useAsync(() => (ob?.product_id ? api<Product>(`/products/${ob.product_id}`) : Promise.resolve(null)), [ob?.product_id]);
  const [contact, setContact] = useState<(Partial<Contact> & typeof emptyContact) | null>(null);
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
  const saveContact = async (e: FormEvent) => {
    e.preventDefault();
    if (!contact) return;
    await run(() => contact.id ? api(`/onboardings/${ob.id}/contacts/${contact.id}`, "PUT", contact) : api(`/onboardings/${ob.id}/contacts`, "POST", contact));
    setContact(null);
  };
  const changeExtensions = (ids: number[]) => {
    const removed = ob.extensions.filter((e) => !ids.includes(e.id));
    const lost = ob.items.filter((i) => removed.some((e) => e.name === i.extension_name) && (i.done || i.value || i.comment)).length;
    if (lost && !confirm(`Beim Abwählen gehen ${lost} bereits erfasste Angaben dieser Erweiterung verloren. Fortfahren?`)) return;
    run(() => api(`/onboardings/${ob.id}/extensions`, "PUT", { extension_ids: ids }));
  };
  const sections: Section[] = ["general", "checklist", "readiness"];

  return (
    <>
      <div className="crumbs"><Link to="/onboardings">Onboardings</Link> › {ob.customer_name}</div>
      <div className="row between wrap">
        <div>
          <h1>{ob.title}</h1>
          <div className="muted">{ob.offer_name} · {ob.product_name}{ob.extensions.length > 0 && ` + ${ob.extensions.map((e) => e.name).join(", ")}`} · {ob.customer_name}{ob.customer_kt_number && ` (${ob.customer_kt_number})`} · {fmtDate(ob.created_at)} <StatusPill status={ob.status} />
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

      {(product.data?.extensions.length ?? 0) > 0 && (
        <section className="card">
          <ExtensionPicker extensions={product.data!.extensions} selected={ob.extensions.map((e) => e.id)} onChange={changeExtensions} disabled={locked} />
          <small className="muted">Die Auswahl bestimmt, welche zusätzlichen Onboarding-Punkte der Erweiterungen enthalten sind.</small>
        </section>
      )}

      <section className="card">
        <h2>{SECTION_LABEL.general}</h2>
        <div className="form-grid">
          {ob.items.filter((i) => i.section === "general").map((i) => (
            <GeneralField key={`${i.id}-${i.value}`} item={i} locked={locked} onSave={(value) => saveItem(i, { value })} />
          ))}
        </div>
      </section>

      <section className="card">
        <div className="row between"><h2>Ansprechpartner</h2>
          {!locked && <button className="btn" onClick={() => setContact({ ...emptyContact })}>Ansprechpartner hinzufügen</button>}</div>
        <table>
          <thead><tr><th>Name / Funktion</th><th>Telefon</th><th>Mobil</th><th>E-Mail</th><th>Bemerkung</th><th /></tr></thead>
          <tbody>
            {ob.contacts.map((c) => (
              <tr key={c.id}>
                <td>{c.name}<small className="block muted">{c.role}</small></td><td>{c.phone}</td><td>{c.mobile}</td><td>{c.email}</td><td>{c.notes}</td>
                <td className="actions">{!locked && <>
                  <button className="btn ghost" onClick={() => setContact({ ...c })}>Bearbeiten</button>
                  <button className="btn ghost danger" onClick={() => run(() => api(`/onboardings/${ob.id}/contacts/${c.id}`, "DELETE"))}>Löschen</button></>}</td>
              </tr>
            ))}
            {!ob.contacts.length && <tr><td colSpan={6} className="muted">Mindestens ein Ansprechpartner ist erforderlich (z. B. technisch, Geschäftsführung, Eskalation).</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="card">
        <div className="row between"><h2>Installierte technische Basis</h2>
          {!locked && <button className="btn" onClick={() => setAsset({ ...emptyAsset })}>Eintrag hinzufügen</button>}</div>
        <table>
          <thead><tr><th>Kategorie</th><th>Bezeichnung</th><th>Modell</th><th>Seriennummer</th><th>Produkt / Version</th><th>Anz.</th><th>Standort</th><th>Notiz</th><th /></tr></thead>
          <tbody>
            {ob.assets.map((a) => (
              <tr key={a.id}>
                <td>{a.category}</td><td>{a.name}</td><td>{a.model}</td><td>{a.serial_number}</td><td>{a.product_version}</td><td>{a.quantity}</td><td>{a.location}</td><td>{a.notes}</td>
                <td className="actions">{!locked && <>
                  <button className="btn ghost" onClick={() => setAsset({ ...a })}>Bearbeiten</button>
                  <button className="btn ghost danger" onClick={() => run(() => api(`/onboardings/${ob.id}/assets/${a.id}`, "DELETE"))}>Löschen</button></>}</td>
              </tr>
            ))}
            {!ob.assets.length && <tr><td colSpan={9} className="muted">Noch keine Systeme erfasst (Hosts, Storage, Netzwerk, Hypervisor-Versionen, Backup …).</td></tr>}
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

      {contact && (
        <Modal title={contact.id ? "Ansprechpartner bearbeiten" : "Ansprechpartner hinzufügen"} onClose={() => setContact(null)}>
          <form onSubmit={saveContact}>
            <Field label="Name"><input required value={contact.name} onChange={(e) => setContact({ ...contact, name: e.target.value })} autoFocus /></Field>
            <Field label="Funktion / Rolle"><input value={contact.role} onChange={(e) => setContact({ ...contact, role: e.target.value })} placeholder="z. B. IT-Leitung, Geschäftsführung, Eskalation" /></Field>
            <div className="row">
              <Field label="Telefon"><input value={contact.phone} onChange={(e) => setContact({ ...contact, phone: e.target.value })} /></Field>
              <Field label="Mobil"><input value={contact.mobile} onChange={(e) => setContact({ ...contact, mobile: e.target.value })} /></Field>
            </div>
            <Field label="E-Mail"><input type="email" value={contact.email} onChange={(e) => setContact({ ...contact, email: e.target.value })} /></Field>
            <Field label="Bemerkung"><textarea rows={2} value={contact.notes} onChange={(e) => setContact({ ...contact, notes: e.target.value })} placeholder="z. B. erreichbar Mo–Fr 8–17 Uhr" /></Field>
            <div className="row end"><button type="button" className="btn" onClick={() => setContact(null)}>Abbrechen</button><button className="btn primary">Speichern</button></div>
          </form>
        </Modal>
      )}

      {asset && (
        <Modal title={asset.id ? "Eintrag bearbeiten" : "Eintrag hinzufügen"} onClose={() => setAsset(null)}>
          <form onSubmit={saveAsset}>
            <Field label="Kategorie"><select value={asset.category} onChange={(e) => setAsset({ ...asset, category: e.target.value })}>
              {ASSET_CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
            <Field label="Bezeichnung"><input required value={asset.name} onChange={(e) => setAsset({ ...asset, name: e.target.value })} autoFocus placeholder="z. B. Dell-Server, ESXi-Host 1" /></Field>
            <div className="row">
              <Field label="Modell"><input value={asset.model} onChange={(e) => setAsset({ ...asset, model: e.target.value })} placeholder="z. B. PowerEdge R750" /></Field>
              <Field label="Seriennummer"><input value={asset.serial_number} onChange={(e) => setAsset({ ...asset, serial_number: e.target.value })} /></Field>
            </div>
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
