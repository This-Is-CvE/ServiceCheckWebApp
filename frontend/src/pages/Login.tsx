import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, setToken } from "../api";
import { ErrorBox, Field } from "../ui";

export default function Login() {
  const nav = useNavigate();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await login(u, p);
      setToken(r.access_token);
      nav("/");
    } catch (x: any) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <form className="card login" onSubmit={submit}>
        <img src="/logo.png" alt="PCO" className="login-logo" />
        <h1><small>Service Check &amp; Onboarding</small></h1>
        <ErrorBox error={err} />
        <Field label="Benutzername"><input value={u} onChange={(e) => setU(e.target.value)} autoFocus required /></Field>
        <Field label="Passwort"><input type="password" value={p} onChange={(e) => setP(e.target.value)} required /></Field>
        <button className="btn primary" disabled={busy}>Anmelden</button>
      </form>
    </div>
  );
}
