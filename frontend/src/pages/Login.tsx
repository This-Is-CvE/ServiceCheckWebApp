import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, login, setToken } from "../api";
import { ErrorBox, Field } from "../ui";

const ERRORS: Record<string, string> = {
  no_role: "Für dieses Konto ist keine Rolle in der Anwendung vergeben. Bitte beim Administrator die Zuweisung „ServiceCheck.Consultant“ oder „ServiceCheck.Admin“ anfragen.",
  account_disabled: "Dieses Konto wurde deaktiviert.",
  login_cancelled: "Die Anmeldung wurde abgebrochen.",
  session_expired: "Die Anmeldung ist abgelaufen. Bitte erneut versuchen.",
  state_mismatch: "Die Anmeldung konnte nicht überprüft werden. Bitte erneut versuchen.",
  invalid_token: "Die Antwort von Microsoft konnte nicht überprüft werden.",
  token_exchange_failed: "Die Anmeldung bei Microsoft ist fehlgeschlagen.",
  username_taken: "Ein lokaler Benutzer mit diesem Namen existiert bereits.",
};

export default function Login() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [methods, setMethods] = useState<{ local: boolean; oidc: boolean }>({ local: true, oidc: false });
  useEffect(() => { api("/auth/config").then(setMethods).catch(() => {}); }, []);
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(params.get("error") ? ERRORS[params.get("error")!] ?? "Anmeldung fehlgeschlagen." : null);
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
        {methods.oidc && <a className="btn primary block-btn" href="/api/auth/oidc/login">Mit Microsoft anmelden</a>}
        {methods.local && methods.oidc && <div className="muted sep">oder lokal</div>}
        {methods.local && <>
        <Field label="Benutzername"><input value={u} onChange={(e) => setU(e.target.value)} autoFocus required /></Field>
        <Field label="Passwort"><input type="password" value={p} onChange={(e) => setP(e.target.value)} required /></Field>
        <button className="btn primary" disabled={busy}>Anmelden</button>
        </>}
      </form>
    </div>
  );
}
