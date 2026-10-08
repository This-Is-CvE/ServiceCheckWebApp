import { FormEvent, useState } from "react";
import { api } from "../api";
import { Customer } from "../types";
import { ErrorBox, Field, Modal, useAsync } from "../ui";

const empty = { name: "", contact_name: "", contact_email: "", notes: "" };

export default function Customers() {
  const list = useAsync(() => api<Customer[]>("/customers"), []);
  const [edit, setEdit] = useState<(Partial<Customer> & typeof empty) | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!edit) return;
    try {
      await (edit.id ? api(`/customers/${edit.id}`, "PUT", edit) : api("/customers", "POST", edit));
      setEdit(null);
      list.reload();
    } catch (x: any) { setErr(x.message); }
  }
  async function remove(c: Customer) {
    if (!confirm(`Kunde „${c.name}“ löschen?`)) return;
    try { await api(`/customers/${c.id}`, "DELETE"); list.reload(); setErr(null); } catch (x: any) { setErr(x.message); }
  }

  return (
    <>
      <div className="row between"><h1>Kunden</h1><button className="btn primary" onClick={() => setEdit({ ...empty })}>Neuer Kunde</button></div>
      <ErrorBox error={err || list.error} />
      <section className="card">
        <table>
          <thead><tr><th>Name</th><th>Ansprechpartner</th><th>E-Mail</th><th /></tr></thead>
          <tbody>
            {(list.data ?? []).map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td><td>{c.contact_name}</td><td>{c.contact_email}</td>
                <td className="actions">
                  <button className="btn ghost" onClick={() => setEdit({ ...c })}>Bearbeiten</button>
                  <button className="btn ghost danger" onClick={() => remove(c)}>Löschen</button>
                </td>
              </tr>
            ))}
            {list.data?.length === 0 && <tr><td colSpan={4} className="muted">Noch keine Kunden angelegt.</td></tr>}
          </tbody>
        </table>
      </section>
      {edit && (
        <Modal title={edit.id ? "Kunde bearbeiten" : "Neuer Kunde"} onClose={() => setEdit(null)}>
          <form onSubmit={save}>
            <Field label="Name"><input required value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} autoFocus /></Field>
            <Field label="Ansprechpartner"><input value={edit.contact_name} onChange={(e) => setEdit({ ...edit, contact_name: e.target.value })} /></Field>
            <Field label="E-Mail"><input type="email" value={edit.contact_email} onChange={(e) => setEdit({ ...edit, contact_email: e.target.value })} /></Field>
            <Field label="Notizen"><textarea rows={3} value={edit.notes} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} /></Field>
            <div className="row end"><button type="button" className="btn" onClick={() => setEdit(null)}>Abbrechen</button><button className="btn primary">Speichern</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}
