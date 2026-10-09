from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Customer, Onboarding, OnboardingAsset, OnboardingContact, OnboardingDocument, OnboardingItem,
                      Product, ProductExtension, ServiceCheck, User)
from .. import storage
from ..pdf_onboarding import build_onboarding_report
from ..schemas import (AssetIn, ContactIn, ExtensionSelection, OnboardingCreate, OnboardingItemUpdate, OnboardingListOut,
                       OnboardingOut)
from ..security import current_user

router = APIRouter(prefix="/api", tags=["onboarding"])


def _is_done(item: OnboardingItem) -> bool:
    return bool(item.value.strip()) if item.section == "general" else item.done


def _open_required(ob: Onboarding) -> list[str]:
    missing = [i.label for i in ob.items if i.required and not _is_done(i)]
    if not ob.contacts:
        missing.insert(0, "Mindestens ein Ansprechpartner")
    return missing


def _progress(ob: Onboarding) -> float:
    return round(sum(1 for i in ob.items if _is_done(i)) / len(ob.items) * 100, 1) if ob.items else 0.0


def _list_out(ob: Onboarding) -> dict:
    return {"id": ob.id, "title": ob.title, "product_id": ob.product_id, "customer_id": ob.customer_id, "customer_name": ob.customer.name,
            "customer_kt_number": ob.customer.kt_number, "offer_name": ob.offer_name,
            "product_name": ob.product_name, "status": ob.status, "progress": _progress(ob),
            "created_at": ob.created_at}


def _out(ob: Onboarding) -> OnboardingOut:
    return OnboardingOut(**_list_out(ob), service_check_id=ob.service_check_id, completed_at=ob.completed_at,
                         extensions=ob.extensions, items=ob.items, assets=ob.assets, contacts=ob.contacts, open_required=_open_required(ob),
                         documents=ob.documents)


def _get(db: Session, id_: int) -> Onboarding:
    ob = db.get(Onboarding, id_)
    if not ob:
        raise HTTPException(404, "Onboarding nicht gefunden")
    return ob


def _writable(ob: Onboarding) -> None:
    if ob.status == "completed":
        raise HTTPException(409, "Abgeschlossene Onboardings sind schreibgeschützt")


@router.get("/onboardings", response_model=list[OnboardingListOut])
def list_onboardings(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_list_out(o) for o in db.scalars(select(Onboarding).order_by(Onboarding.created_at.desc()))]


def _selected_extensions(product: Product, ids: list[int]) -> list[ProductExtension]:
    exts = [e for e in product.extensions if e.id in set(ids)]
    if len(exts) != len(set(ids)):
        raise HTTPException(422, "Mindestens eine Erweiterung gehört nicht zu diesem Produkt")
    return exts


def _snapshot(product: Product, extension: ProductExtension | None) -> list[OnboardingItem]:
    ext_id = extension.id if extension else None
    base = (extension.position if extension else 0) * 1000
    return [OnboardingItem(section=t.section, label=t.label, help=t.help, field_type=t.field_type,
                           required=t.required, position=base + t.position,
                           extension_name=extension.name if extension else None)
            for t in product.template_items if t.extension_id == ext_id]


@router.post("/onboardings", response_model=OnboardingOut, status_code=201)
def create_onboarding(body: OnboardingCreate, db: Session = Depends(get_db), _: User = Depends(current_user)):
    customer, product = db.get(Customer, body.customer_id), db.get(Product, body.product_id)
    if not customer or not product:
        raise HTTPException(404, "Kunde oder Produkt nicht gefunden")
    if body.service_check_id and not db.get(ServiceCheck, body.service_check_id):
        raise HTTPException(404, "Service Check nicht gefunden")
    exts = _selected_extensions(product, body.extension_ids)
    items = _snapshot(product, None)
    for e in exts:
        items += _snapshot(product, e)
    if not items:
        raise HTTPException(422, "Für dieses Produkt ist keine Onboarding-Vorlage hinterlegt")
    ob = Onboarding(customer_id=customer.id, offer_id=product.offer_id, offer_name=product.offer.name,
                    product_id=product.id, product_name=product.name,
                    extensions=[{"id": e.id, "name": e.name} for e in exts],
                    service_check_id=body.service_check_id,
                    title=body.title or f"Onboarding {customer.name} – {product.name}")
    ob.items = items
    db.add(ob)
    db.commit()
    return _out(ob)


@router.put("/onboardings/{ob_id}/extensions", response_model=OnboardingOut)
def set_extensions(ob_id: int, body: ExtensionSelection, db: Session = Depends(get_db),
                   _: User = Depends(current_user)):
    """Erweiterungen ändern: Punkte bleibender Erweiterungen bleiben unverändert, abgewählte werden entfernt,
    neue aus der Vorlage hinzugefügt."""
    ob = _get(db, ob_id)
    _writable(ob)
    product = db.get(Product, ob.product_id) if ob.product_id else None
    if not product:
        raise HTTPException(409, "Das Produkt dieses Onboardings existiert nicht mehr im Katalog")
    wanted = _selected_extensions(product, body.extension_ids)
    current = {e["id"]: e["name"] for e in ob.extensions}
    for gone in set(current) - {e.id for e in wanted}:
        ob.items = [i for i in ob.items if i.extension_name != current[gone]]
    new_items = []
    for e in wanted:
        if e.id not in current:
            new_items += _snapshot(product, e)
    ob.items = ob.items + new_items
    ob.extensions = [{"id": e.id, "name": e.name} for e in wanted]
    db.commit()
    return _out(ob)


@router.get("/onboardings/{ob_id}", response_model=OnboardingOut)
def get_onboarding(ob_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _out(_get(db, ob_id))


@router.put("/onboardings/{ob_id}/items/{item_id}", response_model=OnboardingOut)
def update_item(ob_id: int, item_id: int, body: OnboardingItemUpdate, db: Session = Depends(get_db),
                _: User = Depends(current_user)):
    ob = _get(db, ob_id)
    _writable(ob)
    item = next((i for i in ob.items if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "Punkt nicht gefunden")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(item, k, v)
    db.commit()
    return _out(ob)


@router.post("/onboardings/{ob_id}/assets", response_model=OnboardingOut, status_code=201)
def add_asset(ob_id: int, body: AssetIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    ob = _get(db, ob_id)
    _writable(ob)
    ob.assets.append(OnboardingAsset(**body.model_dump()))
    db.commit()
    return _out(ob)


@router.put("/onboardings/{ob_id}/assets/{asset_id}", response_model=OnboardingOut)
def update_asset(ob_id: int, asset_id: int, body: AssetIn, db: Session = Depends(get_db),
                 _: User = Depends(current_user)):
    ob = _get(db, ob_id)
    _writable(ob)
    asset = next((a for a in ob.assets if a.id == asset_id), None)
    if not asset:
        raise HTTPException(404, "Eintrag nicht gefunden")
    for k, v in body.model_dump().items():
        setattr(asset, k, v)
    db.commit()
    return _out(ob)


@router.delete("/onboardings/{ob_id}/assets/{asset_id}", response_model=OnboardingOut)
def delete_asset(ob_id: int, asset_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    ob = _get(db, ob_id)
    _writable(ob)
    asset = next((a for a in ob.assets if a.id == asset_id), None)
    if not asset:
        raise HTTPException(404, "Eintrag nicht gefunden")
    ob.assets.remove(asset)
    db.commit()
    return _out(ob)


@router.post("/onboardings/{ob_id}/contacts", response_model=OnboardingOut, status_code=201)
def add_contact(ob_id: int, body: ContactIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    ob = _get(db, ob_id)
    _writable(ob)
    ob.contacts.append(OnboardingContact(**body.model_dump()))
    db.commit()
    return _out(ob)


@router.put("/onboardings/{ob_id}/contacts/{contact_id}", response_model=OnboardingOut)
def update_contact(ob_id: int, contact_id: int, body: ContactIn, db: Session = Depends(get_db),
                   _: User = Depends(current_user)):
    ob = _get(db, ob_id)
    _writable(ob)
    contact = next((c for c in ob.contacts if c.id == contact_id), None)
    if not contact:
        raise HTTPException(404, "Ansprechpartner nicht gefunden")
    for k, v in body.model_dump().items():
        setattr(contact, k, v)
    db.commit()
    return _out(ob)


@router.delete("/onboardings/{ob_id}/contacts/{contact_id}", response_model=OnboardingOut)
def delete_contact(ob_id: int, contact_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    ob = _get(db, ob_id)
    _writable(ob)
    contact = next((c for c in ob.contacts if c.id == contact_id), None)
    if not contact:
        raise HTTPException(404, "Ansprechpartner nicht gefunden")
    ob.contacts.remove(contact)
    db.commit()
    return _out(ob)


@router.post("/onboardings/{ob_id}/complete", response_model=OnboardingOut)
def complete(ob_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ob = _get(db, ob_id)
    missing = _open_required(ob)
    if missing:
        raise HTTPException(422, f"{len(missing)} Pflichtpunkte sind noch offen: " + "; ".join(missing[:5]))
    ob.status, ob.completed_at = "completed", datetime.now(timezone.utc)
    _file_document(db, ob, user)
    db.commit()
    return _out(ob)


@router.post("/onboardings/{ob_id}/reopen", response_model=OnboardingOut)
def reopen(ob_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    ob = _get(db, ob_id)
    ob.status, ob.completed_at = "open", None
    db.commit()
    return _out(ob)


@router.delete("/onboardings/{ob_id}", status_code=204)
def delete_onboarding(ob_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    ob = _get(db, ob_id)
    docs = list(ob.documents)
    db.delete(ob)
    db.commit()
    for doc in docs:
        storage.remove(doc)


# ----- PDF-Dokument -----
def _file_document(db: Session, ob: Onboarding, user: User) -> OnboardingDocument:
    pdf = build_onboarding_report(ob)
    doc = OnboardingDocument(filename=_filename(ob), size=len(pdf), created_by=user.full_name or user.username)
    storage.store(doc, pdf, ob.id)
    ob.documents.insert(0, doc)
    return doc


def _filename(ob: Onboarding) -> str:
    raw = f"Onboarding_{ob.customer.name}_{ob.offer_name}_{datetime.now().strftime('%Y-%m-%d_%H%M')}"
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in raw) + ".pdf"


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/onboardings/{ob_id}/report.pdf")
def report(ob_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Aktuellen Stand als PDF erzeugen (ohne Ablage), z. B. zum Versand an den Kunden."""
    ob = _get(db, ob_id)
    return _pdf_response(build_onboarding_report(ob), _filename(ob))


@router.post("/onboardings/{ob_id}/documents", response_model=OnboardingOut, status_code=201)
def file_document(ob_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Aktuellen Stand als PDF erzeugen und beim Onboarding ablegen."""
    ob = _get(db, ob_id)
    _file_document(db, ob, user)
    db.commit()
    return _out(ob)


@router.get("/onboardings/{ob_id}/documents/{doc_id}")
def download_document(ob_id: int, doc_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    doc = db.get(OnboardingDocument, doc_id)
    if not doc or doc.onboarding_id != ob_id:
        raise HTTPException(404, "Dokument nicht gefunden")
    return _pdf_response(storage.load(doc), doc.filename)


@router.delete("/onboardings/{ob_id}/documents/{doc_id}", response_model=OnboardingOut)
def delete_document(ob_id: int, doc_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    ob = _get(db, ob_id)
    doc = next((d for d in ob.documents if d.id == doc_id), None)
    if not doc:
        raise HTTPException(404, "Dokument nicht gefunden")
    ob.documents.remove(doc)
    db.commit()
    storage.remove(doc)
    return _out(ob)
