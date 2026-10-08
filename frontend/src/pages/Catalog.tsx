import { FormEvent, Fragment, useEffect, useState } from "react";
import { api } from "../api";
import { Offer, Parameter, Product, Section, SECTION_LABEL, TemplateItem } from "../types";
import { ErrorBox, Field, Modal, useAsync } from "../ui";
import { useUser } from "../App";

type Tab = "params" | "template";

function ParameterEditor({ product, admin }: { product: Product; admin: boolean }) {
  const list = useAsync(() => api<Parameter[]>(`/products/${product.id}/parameters`), [product.id]);
  const [edit, setEdit] = useState<Partial<Parameter> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const categories = [...new Set((list.data ?? []).map((p) => p.category))];

  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await (edit!.id ? api(`/parameters/${edit!.id}`, "PUT", edit) : api(`/products/${product.id}/parameters`, "POST", edit));
      setEdit(null); list.reload();
    } catch (x: any) { setErr(x.message); }
  }
  async function remove(p: Parameter) {
    if (confirm(`Parameter „${p.name}“ löschen? Bestehende Checks bleiben unverändert.`)) {
      await api(`/parameters/${p.id}`, "DELETE"); list.reload();
    }
  }
  const total = (list.data ?? []).reduce((s, p) => s + p.weight, 0);

  return (
    <>
      <div className="row between">
        <small className="muted">{list.data?.length ?? 0} Parameter · Summe der Gewichte {total}</small>
        {admin && <button className="btn" onClick={() => { setErr(null); setEdit({ category: categories[categories.length - 1] ?? "Allgemein", name: "", description: "", weight: 5, is_blocker: false, recommendation: "" }); }}>Parameter hinzufügen</button>}
      </div>
      <ErrorBox error={list.error} />
      <table>
        <thead><tr><th>Parameter</th><th>Gew.</th><th>K.-o.</th><th>Empfehlung bei Abweichung</th>{admin && <th />}</tr></thead>
        <tbody>
          {categories.map((cat) => (
            <Fragment key={cat}>
              <tr className="cat-row"><td colSpan={5}>{cat}</td></tr>
              {(list.data ?? []).filter((p) => p.category === cat).map((p) => (
                <tr key={p.id}>
                  <td>{p.name}{p.description && <small className="block muted">{p.description}</small>}</td>
                  <td>{p.weight}</td><td>{p.is_blocker ? <span className="badge ko">K.-o.</span> : ""}</td>
                  <td className="muted">{p.recommendation}</td>
                  {admin && <td className="actions"><button className="btn ghost" onClick={() => { setErr(null); setEdit({ ...p }); }}>Bearbeiten</button><button className="btn ghost danger" onClick={() => remove(p)}>Löschen</button></td>}
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
      {edit && (
        <Modal title={edit.id ? "Parameter bearbeiten" : "Parameter hinzufügen"} onClose={() => setEdit(null)}>
          <form onSubmit={save}>
            <ErrorBox error={err} />
            <Field label="Kategorie"><input required list="cats" value={edit.category ?? ""} onChange={(e) => setEdit({ ...edit, category: e.target.value })} />
              <datalist id="cats">{categories.map((c) => <option key={c} value={c} />)}</datalist></Field>
            <Field label="Parameter / Prüffrage"><input required value={edit.name ?? ""} onChange={(e) => setEdit({ ...edit, name: e.target.value })} autoFocus /></Field>
            <Field label="Erläuterung (Wie wird geprüft?)"><textarea rows={2} value={edit.description ?? ""} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
            <div className="row">
              <Field label="Gewichtung (1–10)"><input type="number" min={1} max={10} value={edit.weight ?? 5} onChange={(e) => setEdit({ ...edit, weight: Number(e.target.value) })} /></Field>
              <label className="check-inline"><input type="checkbox" checked={!!edit.is_blocker} onChange={(e) => setEdit({ ...edit, is_blocker: e.target.checked })} /> K.-o.-Kriterium (Ampel Rot, wenn nicht erfüllt)</label>
            </div>
            <Field label="Empfehlung für das Vorprojekt bei Abweichung"><textarea rows={3} value={edit.recommendation ?? ""} onChange={(e) => setEdit({ ...edit, recommendation: e.target.value })} /></Field>
            <div className="row end"><button type="button" className="btn" onClick={() => setEdit(null)}>Abbrechen</button><button className="btn primary">Speichern</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}

function TemplateEditor({ offer, admin }: { offer: Offer; admin: boolean }) {
  const list = useAsync(() => api<TemplateItem[]>(`/offers/${offer.id}/template`), [offer.id]);
  const [edit, setEdit] = useState<Partial<TemplateItem> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await (edit!.id ? api(`/template-items/${edit!.id}`, "PUT", edit) : api(`/offers/${offer.id}/template`, "POST", edit));
      setEdit(null); list.reload();
    } catch (x: any) { setErr(x.message); }
  }
  return (
    <>
      <div className="row between">
        <small className="muted">Neue Onboardings übernehmen den aktuellen Stand der Vorlage; bestehende bleiben unverändert.</small>
        {admin && <button className="btn" onClick={() => { setErr(null); setEdit({ section: "readiness", label: "", help: "", field_type: "text", required: true }); }}>Punkt hinzufügen</button>}
      </div>
      <ErrorBox error={list.error} />
      {(["general", "checklist", "readiness"] as Section[]).map((s) => (
        <div key={s}>
          <h3>{SECTION_LABEL[s]}</h3>
          <table><tbody>
            {(list.data ?? []).filter((i) => i.section === s).map((i) => (
              <tr key={i.id}>
                <td>{i.label}{i.help && <small className="block muted">{i.help}</small>}</td>
                <td>{i.required ? "Pflicht" : "optional"}</td>
                {admin && <td className="actions"><button className="btn ghost" onClick={() => { setErr(null); setEdit({ ...i }); }}>Bearbeiten</button>
                  <button className="btn ghost danger" onClick={async () => { await api(`/template-items/${i.id}`, "DELETE"); list.reload(); }}>Löschen</button></td>}
              </tr>
            ))}
          </tbody></table>
        </div>
      ))}
      {edit && (
        <Modal title={edit.id ? "Punkt bearbeiten" : "Punkt hinzufügen"} onClose={() => setEdit(null)}>
          <form onSubmit={save}>
            <ErrorBox error={err} />
            <Field label="Abschnitt"><select value={edit.section} onChange={(e) => setEdit({ ...edit, section: e.target.value as Section })}>
              {(Object.keys(SECTION_LABEL) as Section[]).map((s) => <option key={s} value={s}>{SECTION_LABEL[s]}</option>)}</select></Field>
            <Field label="Bezeichnung"><input required value={edit.label ?? ""} onChange={(e) => setEdit({ ...edit, label: e.target.value })} autoFocus /></Field>
            <Field label="Hilfetext"><input value={edit.help ?? ""} onChange={(e) => setEdit({ ...edit, help: e.target.value })} /></Field>
            {edit.section === "general" && <Field label="Feldtyp"><select value={edit.field_type} onChange={(e) => setEdit({ ...edit, field_type: e.target.value as TemplateItem["field_type"] })}>
              <option value="text">Text (einzeilig)</option><option value="textarea">Text (mehrzeilig)</option><option value="date">Datum</option></select></Field>}
            <label className="check-inline"><input type="checkbox" checked={!!edit.required} onChange={(e) => setEdit({ ...edit, required: e.target.checked })} /> Pflichtpunkt (Voraussetzung für den Abschluss)</label>
            <div className="row end"><button type="button" className="btn" onClick={() => setEdit(null)}>Abbrechen</button><button className="btn primary">Speichern</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}

export default function Catalog() {
  const admin = useUser().role === "admin";
  const offers = useAsync(() => api<Offer[]>("/offers"), []);
  const [offerId, setOfferId] = useState<number | null>(null);
  const [productId, setProductId] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("params");
  const [err, setErr] = useState<string | null>(null);
  const [dlg, setDlg] = useState<null | { kind: "offer" | "product"; data: any }>(null);

  const offer = offers.data?.find((o) => o.id === offerId) ?? offers.data?.[0] ?? null;
  const product = offer?.products.find((p) => p.id === productId) ?? offer?.products[0] ?? null;
  useEffect(() => { if (offer && offerId !== offer.id) setOfferId(offer.id); }, [offer, offerId]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!dlg) return;
    const d = dlg.data;
    try {
      if (dlg.kind === "offer") {
        const o = await (d.id ? api<Offer>(`/offers/${d.id}`, "PUT", d) : api<Offer>("/offers", "POST", d));
        setOfferId(o.id);
      } else {
        const p = await (d.id ? api<Product>(`/products/${d.id}`, "PUT", d) : api<Product>(`/offers/${offer!.id}/products`, "POST", d));
        setProductId(p.id);
      }
      setDlg(null); setErr(null); offers.reload();
    } catch (x: any) { setErr(x.message); }
  }
  async function del(kind: "offers" | "products", id: number, name: string) {
    if (!confirm(`„${name}“ samt Inhalten löschen? Bestehende Checks bleiben erhalten.`)) return;
    try { await api(`/${kind}/${id}`, "DELETE"); setOfferId(null); setProductId(null); offers.reload(); } catch (x: any) { setErr(x.message); }
  }

  return (
    <>
      <div className="row between"><h1>Kataloge &amp; Vorlagen</h1>
        {admin && <button className="btn primary" onClick={() => { setErr(null); setDlg({ kind: "offer", data: { name: "", description: "" } }); }}>Neues Offer</button>}</div>
      {!admin && <p className="muted">Nur Administratoren können Kataloge ändern.</p>}
      <ErrorBox error={err || offers.error} />
      <div className="tabs">
        {(offers.data ?? []).map((o) => (
          <button key={o.id} className={o.id === offer?.id ? "active" : ""} onClick={() => { setOfferId(o.id); setProductId(null); }}>{o.name}</button>
        ))}
      </div>
      {offer && (
        <section className="card">
          <div className="row between">
            <div><h2>{offer.name}</h2><span className="muted">{offer.description}</span></div>
            {admin && <div className="row"><button className="btn ghost" onClick={() => { setErr(null); setDlg({ kind: "offer", data: { ...offer } }); }}>Offer bearbeiten</button>
              <button className="btn ghost danger" onClick={() => del("offers", offer.id, offer.name)}>Löschen</button></div>}
          </div>
          <div className="tabs sub">
            <button className={tab === "template" ? "active" : ""} onClick={() => setTab("template")}>Onboarding-Vorlage</button>
            {offer.products.map((p) => (
              <button key={p.id} className={tab === "params" && p.id === product?.id ? "active" : ""} onClick={() => { setProductId(p.id); setTab("params"); }}>{p.name}</button>
            ))}
            {admin && <button className="add" onClick={() => { setErr(null); setDlg({ kind: "product", data: { name: "", description: "", green_min: 80, yellow_min: 50 } }); }}>+ Produkt</button>}
          </div>
          {tab === "template" ? <TemplateEditor offer={offer} admin={admin} />
            : product ? (
              <>
                <div className="row between">
                  <span className="muted">Ampel: Grün ab {product.green_min} % · Gelb ab {product.yellow_min} % · darunter Rot. {product.description}</span>
                  {admin && <div className="row"><button className="btn ghost" onClick={() => { setErr(null); setDlg({ kind: "product", data: { ...product } }); }}>Produkt &amp; Schwellwerte</button>
                    <button className="btn ghost danger" onClick={() => del("products", product.id, product.name)}>Löschen</button></div>}
                </div>
                <ParameterEditor product={product} admin={admin} />
              </>
            ) : <p className="muted">Dieses Offer hat noch kein Produkt.</p>}
        </section>
      )}
      {dlg && (
        <Modal title={dlg.kind === "offer" ? (dlg.data.id ? "Offer bearbeiten" : "Neues Offer") : (dlg.data.id ? "Produkt bearbeiten" : "Neues Produkt")} onClose={() => setDlg(null)}>
          <form onSubmit={save}>
            <ErrorBox error={err} />
            <Field label="Name"><input required value={dlg.data.name} onChange={(e) => setDlg({ ...dlg, data: { ...dlg.data, name: e.target.value } })} autoFocus /></Field>
            <Field label="Beschreibung"><textarea rows={2} value={dlg.data.description} onChange={(e) => setDlg({ ...dlg, data: { ...dlg.data, description: e.target.value } })} /></Field>
            {dlg.kind === "product" && (
              <div className="row">
                <Field label="Grün ab (%)"><input type="number" min={0} max={100} value={dlg.data.green_min} onChange={(e) => setDlg({ ...dlg, data: { ...dlg.data, green_min: Number(e.target.value) } })} /></Field>
                <Field label="Gelb ab (%)"><input type="number" min={0} max={100} value={dlg.data.yellow_min} onChange={(e) => setDlg({ ...dlg, data: { ...dlg.data, yellow_min: Number(e.target.value) } })} /></Field>
              </div>
            )}
            <div className="row end"><button type="button" className="btn" onClick={() => setDlg(null)}>Abbrechen</button><button className="btn primary">Speichern</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}
