import { ChangeEvent, useState } from "react";
import { api, apiUpload } from "../api";
import { bumpLogo, ErrorBox, Logo, useAsync } from "../ui";
import { useUser } from "../App";

type Kind = "app" | "report";
interface LogoInfo { custom: boolean; inherited: boolean; width: number; height: number; updated_by: string | null; updated_at: string | null }
interface Branding { app: LogoInfo; report: LogoInfo }

function LogoSection({ kind, title, usage, info, onChanged }: {
  kind: Kind; title: string; usage: string; info: LogoInfo | undefined; onChanged: () => void;
}) {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";   // dieselbe Datei später erneut wählen können
    if (!file) return;
    setBusy(true); setErr(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await apiUpload(`/branding/logo/${kind}`, form);
      bumpLogo(); onChanged();
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }
  async function reset() {
    const was = kind === "app" ? "wieder das Standardlogo" : "wieder das Logo der Anwendung";
    if (!confirm(`Eigenes Logo entfernen und ${was} verwenden?`)) return;
    setBusy(true); setErr(null);
    try { await api(`/branding/logo/${kind}`, "DELETE"); bumpLogo(); onChanged(); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }

  const status = !info ? "…" : info.custom
    ? <>Eigenes Logo ({info.width} × {info.height} Pixel){info.updated_by && <>, hochgeladen von {info.updated_by}</>}.</>
    : kind === "app" ? <>Es wird das Standardlogo verwendet.</> : <>Es wird das Logo der Anwendung verwendet.</>;
  return (
    <section className="card">
      <h2>{title}</h2>
      <p className="muted">{usage}</p>
      <ErrorBox error={err} />
      <div className="row logo-settings">
        <Logo kind={kind} className="logo-preview" alt={`Aktuelles Logo: ${title}`} />
        <div>
          <p>{status}</p>
          <div className="row">
            <label className={`btn primary file-btn${busy ? " disabled" : ""}`}>
              {busy ? "Bitte warten …" : "Neues Logo hochladen"}
              <input type="file" accept="image/png,image/jpeg" onChange={upload} disabled={busy} hidden />
            </label>
            {info?.custom && <button className="btn ghost danger" onClick={reset} disabled={busy}>
              {kind === "app" ? "Standardlogo wiederherstellen" : "Logo der Anwendung verwenden"}</button>}
          </div>
        </div>
      </div>
    </section>
  );
}

export default function Settings() {
  const admin = useUser().role === "admin";
  const info = useAsync(() => api<Branding>("/branding"), []);
  if (!admin) return <><h1>Einstellungen</h1><p className="muted">Nur Administratoren können Einstellungen ändern.</p></>;
  return (
    <>
      <h1>Einstellungen</h1>
      <ErrorBox error={info.error} />
      <LogoSection kind="app" title="Logo der Anwendung" info={info.data?.app} onChanged={info.reload}
        usage="Erscheint in der Seitenleiste und auf der Anmeldeseite." />
      <LogoSection kind="report" title="Logo für Reports" info={info.data?.report} onChanged={info.reload}
        usage="Erscheint im Kopf der PDF-Dokumente (Service-Check-Report, Onboarding-Dokumentation). Ohne eigenes Logo wird das Logo der Anwendung verwendet. Bereits erstellte und abgelegte PDFs ändern sich nicht, neue verwenden das aktuelle Logo." />
      <p className="muted logo-hint">
        Erlaubt sind PNG oder JPEG, höchstens 1 MB, zwischen 16 und 4000 Pixel je Seite. Empfohlen: quer, mit transparentem oder weißem
        Hintergrund und mindestens 400 Pixel Breite, damit es im PDF scharf bleibt.
      </p>
    </>
  );
}
