import { FormEvent, useState } from "react";
import { api } from "../api";
import { User } from "../types";
import { ErrorBox, Field, Modal, useAsync } from "../ui";
import { useUser } from "../App";

export default function Users() {
  const me = useUser();
  const list = useAsync(() => api<User[]>("/users"), []);
  const [form, setForm] = useState<{ username: string; full_name: string; password: string; role: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    try { await api("/users", "POST", form); setForm(null); list.reload(); } catch (x: any) { setErr(x.message); }
  }
  async function patch(u: User, body: object) {
    try { await api(`/users/${u.id}`, "PATCH", body); list.reload(); setErr(null); } catch (x: any) { setErr(x.message); }
  }
  function resetPw(u: User) {
    const pw = prompt(`Neues Passwort für ${u.username} (mind. 8 Zeichen):`);
    if (pw) patch(u, { password: pw });
  }

  return (
    <>
      <div className="row between"><h1>Benutzer</h1><button className="btn primary" onClick={() => { setErr(null); setForm({ username: "", full_name: "", password: "", role: "consultant" }); }}>Neuer Benutzer</button></div>
      <ErrorBox error={err || list.error} />
      <section className="card">
        <table>
          <thead><tr><th>Benutzername</th><th>Name</th><th>Rolle</th><th>Aktiv</th><th /></tr></thead>
          <tbody>
            {(list.data ?? []).map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td><td>{u.full_name}</td>
                <td>
                  <select value={u.role} disabled={u.id === me.id} onChange={(e) => patch(u, { role: e.target.value })}>
                    <option value="admin">Administrator</option><option value="consultant">Consultant</option>
                  </select>
                </td>
                <td><input type="checkbox" checked={u.active} disabled={u.id === me.id} onChange={(e) => patch(u, { active: e.target.checked })} /></td>
                <td className="actions"><button className="btn ghost" onClick={() => resetPw(u)}>Passwort setzen</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted"><b>Administrator:</b> pflegt Kataloge, Vorlagen und Benutzer. <b>Consultant:</b> führt Checks und Onboardings durch.</p>
      </section>
      {form && (
        <Modal title="Neuer Benutzer" onClose={() => setForm(null)}>
          <form onSubmit={create}>
            <ErrorBox error={err} />
            <Field label="Benutzername"><input required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoFocus /></Field>
            <Field label="Name"><input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
            <Field label="Passwort (mind. 8 Zeichen)"><input type="password" required minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
            <Field label="Rolle"><select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="consultant">Consultant</option><option value="admin">Administrator</option></select></Field>
            <div className="row end"><button type="button" className="btn" onClick={() => setForm(null)}>Abbrechen</button><button className="btn primary">Anlegen</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}
