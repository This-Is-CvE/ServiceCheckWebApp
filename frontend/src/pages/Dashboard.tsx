import { Link } from "react-router-dom";
import { api } from "../api";
import { CheckListItem, OnboardingListItem } from "../types";
import { ErrorBox, fmtDate, fmtScore, StatusPill, TrafficLight, useAsync } from "../ui";

export default function Dashboard() {
  const checks = useAsync(() => api<CheckListItem[]>("/checks"), []);
  const obs = useAsync(() => api<OnboardingListItem[]>("/onboardings"), []);
  const c = checks.data ?? [];
  const o = obs.data ?? [];
  const count = (l: string) => c.filter((x) => x.status === "completed" && x.light === l).length;

  return (
    <>
      <h1>Übersicht</h1>
      <ErrorBox error={checks.error || obs.error} />
      <div className="tiles">
        <div className="tile"><b>{c.filter((x) => x.status === "draft").length}</b><span>Checks in Bearbeitung</span></div>
        <div className="tile green"><b>{count("green")}</b><span>abgeschlossen: Grün</span></div>
        <div className="tile yellow"><b>{count("yellow")}</b><span>abgeschlossen: Gelb</span></div>
        <div className="tile red"><b>{count("red")}</b><span>abgeschlossen: Rot</span></div>
        <div className="tile"><b>{o.filter((x) => x.status === "open").length}</b><span>Onboardings offen</span></div>
      </div>
      <div className="grid2">
        <section className="card">
          <div className="row between"><h2>Letzte Service Checks</h2><Link to="/checks">Alle</Link></div>
          <table>
            <tbody>
              {c.slice(0, 6).map((x) => (
                <tr key={x.id}>
                  <td><TrafficLight light={x.light} size="sm" /></td>
                  <td><Link to={`/checks/${x.id}`}>{x.customer_name}</Link><small className="block muted">{x.product_name}</small></td>
                  <td>{fmtScore(x.score)}</td>
                  <td><StatusPill status={x.status} /></td>
                </tr>
              ))}
              {!c.length && <tr><td className="muted">Noch keine Service Checks.</td></tr>}
            </tbody>
          </table>
        </section>
        <section className="card">
          <div className="row between"><h2>Letzte Onboardings</h2><Link to="/onboardings">Alle</Link></div>
          <table>
            <tbody>
              {o.slice(0, 6).map((x) => (
                <tr key={x.id}>
                  <td><Link to={`/onboardings/${x.id}`}>{x.customer_name}</Link><small className="block muted">{x.product_name || x.offer_name} · {fmtDate(x.created_at)}</small></td>
                  <td style={{ width: 120 }}><div className="bar"><i style={{ width: `${x.progress}%` }} /></div></td>
                  <td><StatusPill status={x.status} /></td>
                </tr>
              ))}
              {!o.length && <tr><td className="muted">Noch keine Onboardings.</td></tr>}
            </tbody>
          </table>
        </section>
      </div>
    </>
  );
}
