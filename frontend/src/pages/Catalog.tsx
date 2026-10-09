import { FormEvent, Fragment, useEffect, useState } from "react";
import { api } from "../api";
import { Extension, Offer, Parameter, Product, Section, SECTION_LABEL, TemplateItem } from "../types";
import { ErrorBox, Field, Modal, useAsync } from "../ui";
import { useUser } from "../App";

/** scope: null = Basiskatalog des Produkts, sonst die ID einer Erweiterung. */
type Scope = number | null;

function ParameterEditor({ product, scope, admin, onChanged }: { product: Product; scope: Scope; admin: boolean; onChanged: () => void }) {
  const all = useAsync(() => api<Parameter[]>(`/products/${product.id}/parameters`), [product.id]);
  const list = (all.data ?? []).filter((p) => p.extension_id === scope);
  const [edit, setEdit] = useState<Partial<Parameter> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const categories = [...new Set(list.map((p) => p.category))];
  const blank = (category?: string): Partial<Parameter> => ({ extension_id: scope, category: category ?? categories[categories.length - 1] ?? "Allgemein", name: "", description: "", weight: 5, is_blocker: false, recommendation: "" });

  async function save(e: FormEvent, another = false) {
    e.preventDefault();
    try {
      await (edit!.id ? api(`/parameters/${edit!.id}`, "PUT", edit) : api(`/products/${product.id}/parameters`, "POST", edit));
      setEdit(another ? blank(edit!.category) : null);
      all.reload(); onChanged();
    } catch (x: any) { setErr(x.message); }
  }
  async function remove(p: Parameter) {
    if (confirm(`Parameter „${p.name}“ löschen? Bestehende Checks bleiben unverändert.`)) {
      await api(`/parameters/${p.id}`, "DELETE"); all.reload(); onChanged();
    }
  }
  const total = list.reduce((s, p) => s + p.weight, 0);

  return (
    <>
      <div className="row between">
        <small className="muted">{list.length} Parameter · Summe der Gewichte {total}</small>
        {admin && <button className="btn" onClick={() => { setErr(null); setEdit(blank()); }}>Parameter hinzufügen</button>}
      </div>
      <ErrorBox error={all.error} />
      {all.data && list.length === 0 && <p className="muted">{admin ? "Dieser Katalog ist noch leer. Lege mit „Parameter hinzufügen“ die technischen Prüfpunkte an." : "Dieser Katalog ist noch leer."}</p>}
      <table>
        <thead><tr><th>Parameter</th><th>Gew.</th><th>K.O.</th><th>Empfehlung bei Abweichung</th>{admin && <th />}</tr></thead>
        <tbody>
          {categories.map((cat) => (
            <Fragment key={cat}>
              <tr className="cat-row"><td colSpan={5}>{cat}</td></tr>
              {list.filter((p) => p.category === cat).map((p) => (
                <tr key={p.id}>
                  <td>{p.name}{p.description && <small className="block muted">{p.description}</small>}</td>
                  <td>{p.weight}</td><td>{p.is_blocker ? <span className="badge ko">K.O.</span> : ""}</td>
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
              <label className="check-inline"><input type="checkbox" checked={!!edit.is_blocker} onChange={(e) => setEdit({ ...edit, is_blocker: e.target.checked })} /> K.O.-Kriterium (Ampel Rot, wenn nicht erfüllt)</label>
            </div>
            <Field label="Empfehlung für das Vorprojekt bei Abweichung"><textarea rows={3} value={edit.recommendation ?? ""} onChange={(e) => setEdit({ ...edit, recommendation: e.target.value })} /></Field>
            <div className="row end"><button type="button" className="btn" onClick={() => setEdit(null)}>Abbrechen</button>
              {!edit.id && <button type="button" className="btn" onClick={(e) => (e.currentTarget.form as HTMLFormElement).reportValidity() && save(e as any, true)}>Speichern &amp; nächster</button>}
              <button className="btn primary">Speichern</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}

function TemplateEditor({ product, scope, admin }: { product: Product; scope: Scope; admin: boolean }) {
  const all = useAsync(() => api<TemplateItem[]>(`/products/${product.id}/template`), [product.id]);
  const list = (all.data ?? []).filter((i) => i.extension_id === scope);
  const [edit, setEdit] = useState<Partial<TemplateItem> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await (edit!.id ? api(`/template-items/${edit!.id}`, "PUT", edit) : api(`/products/${product.id}/template`, "POST", edit));
      setEdit(null); all.reload();
    } catch (x: any) { setErr(x.message); }
  }
  return (
    <>
      <div className="row between">
        <small className="muted">Neue Onboardings übernehmen den aktuellen Stand der Vorlage; bestehende bleiben unverändert.</small>
        {admin && <button className="btn" onClick={() => { setErr(null); setEdit({ extension_id: scope, section: "readiness", label: "", help: "", field_type: "text", required: true }); }}>Punkt hinzufügen</button>}
      </div>
      <ErrorBox error={all.error} />
      {all.data && list.length === 0 && <p className="muted">Keine Onboarding-Punkte{scope !== null ? " für diese Erweiterung" : ""} hinterlegt.</p>}
      {(["general", "checklist", "readiness"] as Section[]).map((s) => {
        const items = list.filter((i) => i.section === s);
        return items.length ? (
          <div key={s}>
            <h3>{SECTION_LABEL[s]}</h3>
            <table><tbody>
              {items.map((i) => (
                <tr key={i.id}>
                  <td>{i.label}{i.help && <small className="block muted">{i.help}</small>}</td>
                  <td>{i.required ? "Pflicht" : "optional"}</td>
                  {admin && <td className="actions"><button className="btn ghost" onClick={() => { setErr(null); setEdit({ ...i }); }}>Bearbeiten</button>
                    <button className="btn ghost danger" onClick={async () => { await api(`/template-items/${i.id}`, "DELETE"); all.reload(); }}>Löschen</button></td>}
                </tr>
              ))}
            </tbody></table>
          </div>
        ) : null;
      })}
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

type Dlg = null | { kind: "offer" | "product" | "extension"; data: any };

export default function Catalog() {
  const admin = useUser().role === "admin";
  const offers = useAsync(() => api<Offer[]>("/offers"), []);
  const [offerId, setOfferId] = useState<number | null>(null);
  const [productId, setProductId] = useState<number | null>(null);
  const [scope, setScope] = useState<Scope>(null);
  const [view, setView] = useState<"params" | "template">("params");
  const [err, setErr] = useState<string | null>(null);
  const [dlg, setDlg] = useState<Dlg>(null);

  const offer = offers.data?.find((o) => o.id === offerId) ?? offers.data?.[0] ?? null;
  const product = offer?.products.find((p) => p.id === productId) ?? offer?.products[0] ?? null;
  const ext: Extension | null = product?.extensions.find((e) => e.id === scope) ?? null;
  useEffect(() => { if (offer && offerId !== offer.id) setOfferId(offer.id); }, [offer, offerId]);
  useEffect(() => { if (scope !== null && !ext) setScope(null); }, [scope, ext]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!dlg) return;
    const d = dlg.data;
    try {
      if (dlg.kind === "offer") {
        const o = await (d.id ? api<Offer>(`/offers/${d.id}`, "PUT", d) : api<Offer>("/offers", "POST", d));
        setOfferId(o.id);
      } else if (dlg.kind === "product") {
        const p = await (d.id ? api<Product>(`/products/${d.id}`, "PUT", d) : api<Product>(`/offers/${offer!.id}/products`, "POST", d));
        setProductId(p.id); setScope(null);
      } else {
        const x = await (d.id ? api<Extension>(`/extensions/${d.id}`, "PUT", d) : api<Extension>(`/products/${product!.id}/extensions`, "POST", d));
        setScope(x.id);
      }
      setDlg(null); setErr(null); offers.reload();
    } catch (x: any) { setErr(x.message); }
  }
  async function del(kind: "offers" | "products" | "extensions", id: number, name: string, what: string) {
    if (!confirm(`${what} „${name}“ samt Inhalten löschen? Bestehende Checks und Onboardings bleiben erhalten.`)) return;
    try {
      await api(`/${kind}/${id}`, "DELETE");
      if (kind === "offers") { setOfferId(null); setProductId(null); }
      setScope(null);
      if (kind === "products") setProductId(null);
      offers.reload();
    } catch (x: any) { setErr(x.message); }
  }
  const open = (kind: "offer" | "product" | "extension", data: any) => { setErr(null); setDlg({ kind, data }); };
  const titles = { offer: "Managed Service", product: "Produkt", extension: "Erweiterung" };

  return (
    <>
      <div className="row between"><h1>Kataloge &amp; Vorlagen</h1>
        {admin && <button className="btn primary" onClick={() => open("offer", { name: "", description: "" })}>Neuer Managed Service</button>}</div>
      {!admin && <p className="muted">Nur Administratoren können Kataloge ändern.</p>}
      <ErrorBox error={err || offers.error} />
      {offers.data?.length === 0 && (
        <section className="card"><h2>Noch kein Katalog vorhanden</h2>
          <p>{admin ? "Lege zuerst einen Managed Service an, dann Produkte (z. B. VMware vSphere), deren Basiskatalog und bei Bedarf Erweiterungen (z. B. vSAN)." : "Ein Administrator muss zuerst Managed Services und Kataloge anlegen."}</p>
          {admin && <button className="btn primary" onClick={() => open("offer", { name: "", description: "" })}>Ersten Managed Service anlegen</button>}</section>
      )}
      <div className="tabs">
        {(offers.data ?? []).map((o) => (
          <button key={o.id} className={o.id === offer?.id ? "active" : ""} onClick={() => { setOfferId(o.id); setProductId(null); setScope(null); }}>{o.name}</button>
        ))}
      </div>
      {offer && (
        <section className="card">
          <div className="row between">
            <div><h2>{offer.name}</h2><span className="muted">{offer.description}</span></div>
            {admin && <div className="row"><button className="btn ghost" onClick={() => open("offer", { ...offer })}>Managed Service bearbeiten</button>
              <button className="btn ghost danger" onClick={() => del("offers", offer.id, offer.name, "Managed Service")}>Löschen</button></div>}
          </div>
          <div className="tabs sub">
            {offer.products.map((p) => (
              <button key={p.id} className={p.id === product?.id ? "active" : ""} onClick={() => { setProductId(p.id); setScope(null); }}>{p.name}</button>
            ))}
            {admin && <button className="add" onClick={() => open("product", { name: "", description: "", green_min: 80, yellow_min: 50 })}>+ Produkt</button>}
          </div>
          {!product && <p className="muted">Dieser Managed Service hat noch kein Produkt.</p>}
          {product && (
            <>
              <div className="row between">
                <span className="muted">Ampel: Grün ab {product.green_min} % · Gelb ab {product.yellow_min} % · darunter Rot. {product.description}</span>
                {admin && <div className="row"><button className="btn ghost" onClick={() => open("product", { ...product })}>Produkt &amp; Schwellwerte</button>
                  <button className="btn ghost danger" onClick={() => del("products", product.id, product.name, "Produkt")}>Löschen</button></div>}
              </div>
              <div className="tabs scope-tabs">
                <button className={scope === null ? "active" : ""} onClick={() => setScope(null)}>Basiskatalog ({product.parameter_count})</button>
                {product.extensions.map((x) => (
                  <button key={x.id} className={scope === x.id ? "active" : ""} onClick={() => setScope(x.id)}>Erweiterung: {x.name} ({x.parameter_count})</button>
                ))}
                {admin && <button className="add" onClick={() => open("extension", { name: "", description: "" })}>+ Erweiterung</button>}
              </div>
              {ext && (
                <div className="row between">
                  <span className="muted">Wird nur geprüft, wenn die Erweiterung beim Check bzw. Onboarding ausgewählt ist. {ext.description}</span>
                  {admin && <div className="row"><button className="btn ghost" onClick={() => open("extension", { ...ext })}>Erweiterung bearbeiten</button>
                    <button className="btn ghost danger" onClick={() => del("extensions", ext.id, ext.name, "Erweiterung")}>Löschen</button></div>}
                </div>
              )}
              <div className="tabs sub">
                <button className={view === "params" ? "active" : ""} onClick={() => setView("params")}>Prüfparameter</button>
                <button className={view === "template" ? "active" : ""} onClick={() => setView("template")}>Onboarding-Punkte</button>
              </div>
              {view === "params"
                ? <ParameterEditor key={`p-${product.id}-${scope}`} product={product} scope={scope} admin={admin} onChanged={offers.reload} />
                : <TemplateEditor key={`t-${product.id}-${scope}`} product={product} scope={scope} admin={admin} />}
            </>
          )}
        </section>
      )}
      {dlg && (
        <Modal title={`${titles[dlg.kind]} ${dlg.data.id ? "bearbeiten" : "anlegen"}`} onClose={() => setDlg(null)}>
          <form onSubmit={save}>
            <ErrorBox error={err} />
            <Field label="Name"><input required value={dlg.data.name} onChange={(e) => setDlg({ ...dlg, data: { ...dlg.data, name: e.target.value } })} autoFocus
              placeholder={dlg.kind === "extension" ? "z. B. VMware vSAN" : dlg.kind === "product" ? "z. B. VMware vSphere" : ""} /></Field>
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
