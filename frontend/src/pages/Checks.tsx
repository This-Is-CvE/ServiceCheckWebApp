import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Check, CheckListItem, Customer, Offer } from "../types";
import { ErrorBox, ExtensionPicker, Field, fmtDate, fmtScore, Modal, StatusPill, TrafficLight, useAsync } from "../ui";

export default function Checks() {
  const nav = useNavigate();
  const list = useAsync(() => api<CheckListItem[]>("/checks"), []);
  const customers = useAsync(() => api<Customer[]>("/customers"), []);
  const offers = useAsync(() => api<Offer[]>("/offers"), []);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ customer_id: "", product_id: "", title: "", system_description: "" });
  const [extIds, setExtIds] = useState<number[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const products = (offers.data ?? []).flatMap((o) => o.products.map((p) => ({ ...p, offer: o.name })));
  const selected = products.find((p) => String(p.id) === form.product_id);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      const c = await api<Check>("/checks", "POST", {
        ...form, customer_id: Number(form.customer_id), product_id: Number(form.product_id), extension_ids: extIds,
      });
      nav(`/checks/${c.id}`);
    } catch (x: any) { setErr(x.message); }
  }

  return (
    <>
      <div className="row between"><h1>Service Checks</h1><button className="btn primary" onClick={() => { setErr(null); setOpen(true); }}>Neuer Service Check</button></div>
      <ErrorBox error={list.error} />
      <section className="card">
        <table>
          <thead><tr><th /><th>Kunde</th><th>Managed Service / Produkt</th><th>Score</th><th>Status</th><th>Erstellt</th></tr></thead>
          <tbody>
            {(list.data ?? []).map((c) => (
              <tr key={c.id}>
                <td><TrafficLight light={c.light} size="sm" /></td>
                <td><Link to={`/checks/${c.id}`}>{c.customer_name}</Link>{c.customer_kt_number && <small className="block muted">{c.customer_kt_number}</small>}</td>
                <td>{c.offer_name}<small className="block muted">{c.product_name}</small></td>
                <td>{fmtScore(c.score)}</td>
                <td><StatusPill status={c.status} /></td>
                <td>{fmtDate(c.created_at)}</td>
              </tr>
            ))}
            {list.data?.length === 0 && <tr><td colSpan={6} className="muted">Noch keine Service Checks.</td></tr>}
          </tbody>
        </table>
      </section>
      {open && (
        <Modal title="Neuer Service Check" onClose={() => setOpen(false)}>
          <form onSubmit={create}>
            <ErrorBox error={err} />
            <Field label="Kunde" hint={!customers.data?.length ? "Bitte zuerst unter „Kunden“ einen Kunden anlegen." : undefined}>
              <select required value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })}>
                <option value="">– wählen –</option>
                {(customers.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}{c.kt_number ? ` (${c.kt_number})` : ""}</option>)}
              </select>
            </Field>
            <Field label="Produkt (Katalog)">
              <select required value={form.product_id} onChange={(e) => { setForm({ ...form, product_id: e.target.value }); setExtIds([]); }}>
                <option value="">– wählen –</option>
                {products.map((p) => <option key={p.id} value={p.id}>{p.offer} › {p.name} ({p.parameter_count} Basispunkte)</option>)}
              </select>
            </Field>
            {selected && <ExtensionPicker extensions={selected.extensions} selected={extIds} onChange={setExtIds} />}
            <Field label="Bezeichnung (optional)"><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
            <Field label="Kurzbeschreibung des Systems (optional)"><textarea rows={3} value={form.system_description} onChange={(e) => setForm({ ...form, system_description: e.target.value })} placeholder="z. B. 3-Node-Cluster, Standort Hamburg, ca. 80 VMs" /></Field>
            <div className="row end"><button type="button" className="btn" onClick={() => setOpen(false)}>Abbrechen</button><button className="btn primary">Check starten</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}
