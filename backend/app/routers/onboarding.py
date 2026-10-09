from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Customer, Offer, Onboarding, OnboardingAsset, OnboardingDocument, OnboardingItem,
                      ServiceCheck, User)
from .. import storage
from ..pdf_onboarding import build_onboarding_report
from ..schemas import AssetIn, OnboardingCreate, OnboardingItemUpdate, OnboardingListOut, OnboardingOut
from ..security import current_user

router = APIRouter(prefix="/api", tags=["onboarding"])


def _is_done(item: OnboardingItem) -> bool:
    return bool(item.value.strip()) if item.section == "general" else item.done


def _open_required(ob: Onboarding) -> list[str]:
    return [i.label for i in ob.items if i.required and not _is_done(i)]


def _progress(ob: Onboarding) -> float:
    return round(sum(1 for i in ob.items if _is_done(i)) / len(ob.items) * 100, 1) if ob.items else 0.0


def _list_out(ob: Onboarding) -> dict:
    return {"id": ob.id, "title": ob.title, "customer_id": ob.customer_id, "customer_name": ob.customer.name,
            "offer_name": ob.offer_name, "status": ob.status, "progress": _progress(ob),
            "created_at": ob.created_at}


def _out(ob: Onboarding) -> OnboardingOut:
    return OnboardingOut(**_list_out(ob), service_check_id=ob.service_check_id, completed_at=ob.completed_at,
                         items=ob.items, assets=ob.assets, open_required=_open_required(ob),
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


@router.post("/onboardings", response_model=OnboardingOut, status_code=201)
def create_onboarding(body: OnboardingCreate, db: Session = Depends(get_db), _: User = Depends(current_user)):
    customer, offer = db.get(Customer, body.customer_id), db.get(Offer, body.offer_id)
    if not customer or not offer:
        raise HTTPException(404, "Kunde oder Offer nicht gefunden")
    if body.service_check_id and not db.get(ServiceCheck, body.service_check_id):
        raise HTTPException(404, "Service Check nicht gefunden")
    if not offer.template_items:
        raise HTTPException(422, "Für dieses Offer ist keine Onboarding-Vorlage hinterlegt")
    ob = Onboarding(customer_id=customer.id, offer_id=offer.id, offer_name=offer.name,
                    service_check_id=body.service_check_id, title=body.title or f"Onboarding {customer.name} – {offer.name}")
    ob.items = [OnboardingItem(section=t.section, label=t.label, help=t.help, field_type=t.field_type,
                               required=t.required, position=t.position) for t in offer.template_items]
    db.add(ob)
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
