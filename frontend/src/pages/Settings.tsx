import { ChangeEvent, useState } from "react";
import { api, apiUpload } from "../api";
import { bumpLogo, ErrorBox, Logo, useAsync } from "../ui";
import { useUser } from "../App";

interface Branding { custom: boolean; width: number; height: number; updated_by: string | null; updated_at: string | null }

export default function Settings() {
  const admin = useUser().role === "admin";
  const info = useAsync(() => api<Branding>("/branding"), []);
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
      await apiUpload("/branding/logo", form);
      bumpLogo(); info.reload();
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }
  async function reset() {
    if (!confirm("Eigenes Logo entfernen und wieder das Standardlogo verwenden?")) return;
    setBusy(true); setErr(null);
    try { await api("/branding/logo", "DELETE"); bumpLogo(); info.reload(); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }

  if (!admin) return <><h1>Einstellungen</h1><p className="muted">Nur Administratoren können Einstellungen ändern.</p></>;
  const b = info.data;
  return (
    <>
      <h1>Einstellungen</h1>
      <ErrorBox error={err || info.error} />
      <section className="card">
        <h2>Firmenlogo</h2>
        <p className="muted">
          Das Logo erscheint in der Seitenleiste, auf der Anmeldeseite und im Kopf der PDF-Dokumente.
          Bereits erstellte und abgelegte PDFs ändern sich nicht, neue verwenden das aktuelle Logo.
        </p>
        <div className="row logo-settings">
          <Logo className="logo-preview" alt="Aktuelles Logo" />
          <div>
            <p>
              {b ? (b.custom
                ? <>Eigenes Logo ({b.width} × {b.height} Pixel){b.updated_by && <>, hochgeladen von {b.updated_by}</>}.</>
                : <>Es wird das Standardlogo verwendet.</>) : "…"}
            </p>
            <div className="row">
              <label className={`btn primary file-btn${busy ? " disabled" : ""}`}>
                {busy ? "Bitte warten …" : "Neues Logo hochladen"}
                <input type="file" accept="image/png,image/jpeg" onChange={upload} disabled={busy} hidden />
              </label>
              {b?.custom && <button className="btn ghost danger" onClick={reset} disabled={busy}>Standardlogo wiederherstellen</button>}
            </div>
            <small className="muted block logo-hint">
              PNG oder JPEG, höchstens 1 MB, zwischen 16 und 4000 Pixel je Seite. Empfohlen: quer, mit transparentem oder weißem
              Hintergrund und mindestens 400 Pixel Breite, damit es im PDF scharf bleibt.
            </small>
          </div>
        </div>
      </section>
    </>
  );
}
