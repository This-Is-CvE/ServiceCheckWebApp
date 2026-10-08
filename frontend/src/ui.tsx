import { ReactNode, useEffect, useState } from "react";
import { Light, LIGHT_LABEL } from "./types";

export function TrafficLight({ light, size = "md" }: { light: Light; size?: "sm" | "md" | "lg" }) {
  return (
    <span className={`tl tl-${size}`} title={LIGHT_LABEL[light]} aria-label={`Ampel ${LIGHT_LABEL[light]}`}>
      {(["red", "yellow", "green"] as const).map((c) => (
        <i key={c} className={light === c ? `on ${c}` : ""} />
      ))}
    </span>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-label={title}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="btn ghost" onClick={onClose} aria-label="Schließen">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="alert error" role="alert">{error}</div> : null;
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    fn().then((d) => alive && (setData(d), setError(null))).catch((e) => alive && setError(e.message));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, setData, reload: () => setTick((t) => t + 1) };
}

export const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleDateString("de-DE") : "–");
export const fmtScore = (s: number | null) => (s == null ? "–" : `${Math.round(s)} %`);

export function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = { draft: "Entwurf", completed: "Abgeschlossen", open: "Offen" };
  return <span className={`pill ${status}`}>{map[status] ?? status}</span>;
}
