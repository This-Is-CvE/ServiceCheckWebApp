import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { CheckListItem, Customer, Offer, Onboarding, OnboardingListItem } from "../types";
import { ErrorBox, ExtensionPicker, Field, fmtDate, Modal, StatusPill, useAsync } from "../ui";

export default function Onboardings() {
  const nav = useNavigate();
  const list = useAsync(() => api<OnboardingListItem[]>("/onboardings"), []);
  const customers = useAsync(() => api<Customer[]>("/customers"), []);
  const offers = useAsync(() => api<Offer[]>("/offers"), []);
  const checks = useAsync(() => api<CheckListItem[]>("/checks"), []);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ customer_id: "", product_id: "", service_check_id: "", title: "" });
  const [extIds, setExtIds] = useState<number[]>([]);
  const products = (offers.data ?? []).flatMap((o) => o.products.map((p) => ({ ...p, offer: o.name })));
  const selected = products.find((p) => String(p.id) === form.product_id);
  const [err, setErr] = useState<string | null>(null);
  const checkOptions = (checks.data ?? []).filter((c) => String(c.customer_id) === form.customer_id);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      const ob = await api<Onboarding>("/onboardings", "POST", {
        title: form.title, customer_id: Number(form.customer_id), product_id: Number(form.product_id), extension_ids: extIds,
        service_check_id: form.service_check_id ? Number(form.service_check_id) : null,
      });
      nav(`/onboardings/${ob.id}`);
    } catch (x: any) { setErr(x.message); }
  }

  return (
    <>
      <div className="row between"><h1>Onboardings</h1><button className="btn primary" onClick={() => { setErr(null); setOpen(true); }}>Neues Onboarding</button></div>
      <ErrorBox error={list.error} />
      <section className="card">
        <table>
          <thead><tr><th>Kunde</th><th>Managed Service / Produkt</th><th>Fortschritt</th><th>Status</th><th>Erstellt</th></tr></thead>
          <tbody>
            {(list.data ?? []).map((o) => (
              <tr key={o.id}>
                <td><Link to={`/onboardings/${o.id}`}>{o.customer_name}</Link>{o.customer_kt_number && <small className="block muted">{o.customer_kt_number}</small>}</td>
                <td>{o.offer_name}<small className="block muted">{o.product_name}</small></td>
                <td style={{ width: 180 }}><div className="bar"><i style={{ width: `${o.progress}%` }} /></div><small className="muted">{Math.round(o.progress)} %</small></td>
                <td><StatusPill status={o.status} /></td>
                <td>{fmtDate(o.created_at)}</td>
              </tr>
            ))}
            {list.data?.length === 0 && <tr><td colSpan={5} className="muted">Noch keine Onboardings.</td></tr>}
          </tbody>
        </table>
      </section>
      {open && (
        <Modal title="Neues Onboarding" onClose={() => setOpen(false)}>
          <form onSubmit={create}>
            <ErrorBox error={err} />
            <Field label="Kunde">
              <select required value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value, service_check_id: "" })}>
                <option value="">– wählen –</option>
                {(customers.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}{c.kt_number ? ` (${c.kt_number})` : ""}</option>)}
              </select>
            </Field>
            <Field label="Produkt (Onboarding-Vorlage)">
              <select required value={form.product_id} onChange={(e) => { setForm({ ...form, product_id: e.target.value }); setExtIds([]); }}>
                <option value="">– wählen –</option>
                {products.map((p) => <option key={p.id} value={p.id}>{p.offer} › {p.name}</option>)}
              </select>
            </Field>
            {selected && <ExtensionPicker extensions={selected.extensions} selected={extIds} onChange={setExtIds} />}
            <Field label="Zugehöriger Service Check (optional)">
              <select value={form.service_check_id} onChange={(e) => setForm({ ...form, service_check_id: e.target.value })}>
                <option value="">– keiner –</option>
                {checkOptions.map((c) => <option key={c.id} value={c.id}>{c.product_name} ({fmtDate(c.created_at)})</option>)}
              </select>
            </Field>
            <Field label="Bezeichnung (optional)"><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
            <div className="row end"><button type="button" className="btn" onClick={() => setOpen(false)}>Abbrechen</button><button className="btn primary">Onboarding starten</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}
