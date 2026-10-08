import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, downloadPdf } from "../api";
import { Answer, ANSWER_LABEL, Check, CheckItem, Finding, LIGHT_LABEL } from "../types";
import { ErrorBox, fmtDate, fmtScore, StatusPill, TrafficLight, useAsync } from "../ui";

const ANSWERS: Answer[] = ["yes", "partial", "no", "na"];
const PRIORITY_LABEL: Record<Finding["priority"], string> = {
  critical: "Kritisch – vor Vertragsstart zwingend beheben",
  high: "Hoch – Bestandteil des Vorprojekts",
  medium: "Mittel – im Vorprojekt oder zeitnah danach",
  low: "Niedrig – im Regelbetrieb nachziehen",
};
const VERDICT = {
  green: "Risikoarmer Betrieb durch uns ist möglich.",
  yellow: "Betrieb ist nach Behebung der Befunde (Vorprojekt) risikoarm möglich.",
  red: "Betrieb in der aktuellen Form ist nicht risikoarm – Vorprojekt zwingend erforderlich.",
  grey: "Noch keine Bewertung.",
};

function ItemRow({ item, locked, onChange }: { item: CheckItem; locked: boolean; onChange: (patch: { answer?: Answer | null; comment?: string }) => void }) {
  const [comment, setComment] = useState(item.comment);
  return (
    <div className={`item ${item.answer ?? "open"}`}>
      <div className="item-head">
        <div>
          <b>{item.name}</b>
          {item.is_blocker && <span className="badge ko" title="Bei „Nicht erfüllt“ wird die Ampel Rot">K.-o.</span>}
          <span className="badge" title="Gewichtung">Gewicht {item.weight}</span>
          {item.description && <small className="block muted">{item.description}</small>}
        </div>
        <div className="seg" role="radiogroup" aria-label={item.name}>
          {ANSWERS.map((a) => (
            <button key={a} type="button" role="radio" aria-checked={item.answer === a} disabled={locked}
              className={`${a} ${item.answer === a ? "sel" : ""}`}
              onClick={() => onChange({ answer: item.answer === a ? null : a })}>
              {ANSWER_LABEL[a]}
            </button>
          ))}
        </div>
      </div>
      <input className="note" placeholder="Notiz / Befund (optional)" value={comment} disabled={locked}
        onChange={(e) => setComment(e.target.value)}
        onBlur={() => comment !== item.comment && onChange({ comment })} />
    </div>
  );
}

export default function CheckDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: check, error, setData } = useAsync(() => api<Check>(`/checks/${id}`), [id]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (error) return <ErrorBox error={error} />;
  if (!check) return <div className="muted">Lade …</div>;
  const locked = check.status === "completed";
  const r = check.result;

  async function run<T>(fn: () => Promise<T>) {
    setErr(null);
    setBusy(true);
    try { return await fn(); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }
  const setAnswer = (item: CheckItem, patch: { answer?: Answer | null; comment?: string }) =>
    run(async () => setData(await api<Check>(`/checks/${check.id}/items/${item.id}`, "PUT", patch)));
  const complete = () => run(async () => setData(await api<Check>(`/checks/${check.id}/complete`, "POST")));
  const reopen = () => run(async () => setData(await api<Check>(`/checks/${check.id}/reopen`, "POST")));
  const pdf = () => run(() => downloadPdf(`/checks/${check.id}/report.pdf`));
  const remove = () => confirm("Diesen Service Check endgültig löschen?") &&
    run(async () => { await api(`/checks/${check.id}`, "DELETE"); nav("/checks"); });

  const categories = [...new Set(check.items.map((i) => i.category))];

  return (
    <>
      <div className="crumbs"><Link to="/checks">Service Checks</Link> › {check.customer_name}</div>
      <div className="row between wrap">
        <div><h1>{check.title}</h1><div className="muted">{check.offer_name} · {check.product_name} · {check.customer_name} · {fmtDate(check.created_at)} <StatusPill status={check.status} /></div></div>
        <div className="row">
          <button className="btn" onClick={pdf} disabled={busy}>PDF-Report</button>
          {locked
            ? <button className="btn" onClick={reopen} disabled={busy}>Wieder öffnen</button>
            : <button className="btn primary" onClick={complete} disabled={busy}>Check abschließen</button>}
          <button className="btn ghost danger" onClick={remove}>Löschen</button>
        </div>
      </div>
      <ErrorBox error={err} />

      <section className="card result">
        <TrafficLight light={r.light} size="lg" />
        <div className="grow">
          <h2>{LIGHT_LABEL[r.light]} · {fmtScore(r.score)}</h2>
          <p>{VERDICT[r.light]}</p>
          {r.blocker_failed.length > 0 && <p className="alert error"><b>K.-o.-Kriterien nicht erfüllt:</b> {r.blocker_failed.join("; ")}</p>}
          {r.blocker_partial.length > 0 && <p className="alert warn"><b>K.-o.-Kriterien nur teilweise erfüllt:</b> {r.blocker_partial.join("; ")}</p>}
          <div className="bar" title={`${r.answered} von ${r.total} bewertet`}><i style={{ width: `${(r.answered / r.total) * 100}%` }} /></div>
          <small className="muted">{r.answered} von {r.total} Prüfpunkten bewertet · Grün ab {check.green_min} %, Gelb ab {check.yellow_min} %</small>
        </div>
        <table className="cats">
          <tbody>
            {r.categories.map((c) => (
              <tr key={c.name}><td>{c.name}</td><td>{fmtScore(c.score)}</td><td>{c.answered}/{c.total}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      {check.system_description && <section className="card"><b>System:</b> {check.system_description}</section>}

      {categories.map((cat) => (
        <section key={cat} className="card">
          <h2>{cat}</h2>
          {check.items.filter((i) => i.category === cat).map((i) => (
            <ItemRow key={`${i.id}-${i.comment}`} item={i} locked={locked || busy} onChange={(p) => setAnswer(i, p)} />
          ))}
        </section>
      ))}

      <section className="card">
        <h2>Empfehlungen für das Vorprojekt</h2>
        {r.findings.length === 0 && <p className="muted">Keine Abweichungen festgestellt.</p>}
        {(["critical", "high", "medium", "low"] as const).map((p) => {
          const group = r.findings.filter((f) => f.priority === p);
          return group.length ? (
            <div key={p}>
              <h3 className={`prio ${p}`}>{PRIORITY_LABEL[p]}</h3>
              <ul className="findings">
                {group.map((f) => (
                  <li key={f.item_id}>
                    <b>{f.name}</b> <span className={`badge ${f.answer}`}>{ANSWER_LABEL[f.answer]}</span>
                    <div>{f.recommendation || "Maßnahme im Vorprojekt festlegen."}</div>
                    {f.comment && <small className="muted">Notiz: {f.comment}</small>}
                  </li>
                ))}
              </ul>
            </div>
          ) : null;
        })}
      </section>
    </>
  );
}
