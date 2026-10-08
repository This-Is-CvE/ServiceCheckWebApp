from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import scoring
from ..database import get_db
from ..models import CheckItem, Customer, Product, ServiceCheck, User
from ..pdf_report import build_report
from ..schemas import CheckCreate, CheckItemUpdate, CheckListOut, CheckOut, CheckUpdate
from ..security import current_user

router = APIRouter(prefix="/api/checks", tags=["checks"])


def _get(db: Session, check_id: int) -> ServiceCheck:
    check = db.get(ServiceCheck, check_id)
    if not check:
        raise HTTPException(404, "Service Check nicht gefunden")
    return check


def _list_out(c: ServiceCheck) -> dict:
    return {
        "id": c.id, "title": c.title, "customer_id": c.customer_id, "customer_name": c.customer.name,
        "offer_name": c.offer_name, "product_name": c.product_name, "status": c.status,
        "score": c.score, "light": c.light, "created_at": c.created_at, "completed_at": c.completed_at,
    }


def _out(c: ServiceCheck) -> CheckOut:
    return CheckOut(
        **_list_out(c),
        system_description=c.system_description, green_min=c.green_min, yellow_min=c.yellow_min,
        created_by=(c.created_by.full_name or c.created_by.username) if c.created_by else None,
        items=c.items, result=scoring.evaluate(c.items, c.green_min, c.yellow_min),
    )


def _refresh(c: ServiceCheck) -> None:
    res = scoring.evaluate(c.items, c.green_min, c.yellow_min)
    c.score, c.light = res["score"], res["light"]


@router.get("", response_model=list[CheckListOut])
def list_checks(customer_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = select(ServiceCheck).order_by(ServiceCheck.created_at.desc())
    if customer_id:
        q = q.where(ServiceCheck.customer_id == customer_id)
    return [_list_out(c) for c in db.scalars(q)]


@router.post("", response_model=CheckOut, status_code=201)
def create_check(body: CheckCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    customer = db.get(Customer, body.customer_id)
    product = db.get(Product, body.product_id)
    if not customer or not product:
        raise HTTPException(404, "Kunde oder Produkt nicht gefunden")
    if not product.parameters:
        raise HTTPException(422, "Für dieses Produkt ist noch kein Parameterkatalog hinterlegt")
    check = ServiceCheck(
        customer_id=customer.id, product_id=product.id, offer_name=product.offer.name,
        product_name=product.name, title=body.title or f"{product.name} – {customer.name}",
        system_description=body.system_description, green_min=product.green_min,
        yellow_min=product.yellow_min, created_by_id=user.id,
    )
    check.items = [
        CheckItem(category=p.category, name=p.name, description=p.description, weight=p.weight,
                  is_blocker=p.is_blocker, recommendation=p.recommendation, position=n)
        for n, p in enumerate(product.parameters)
    ]
    db.add(check)
    db.commit()
    return _out(check)


@router.get("/{check_id}", response_model=CheckOut)
def get_check(check_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _out(_get(db, check_id))


@router.patch("/{check_id}", response_model=CheckOut)
def update_check(check_id: int, body: CheckUpdate, db: Session = Depends(get_db), _: User = Depends(current_user)):
    check = _get(db, check_id)
    if check.status == "completed":
        raise HTTPException(409, "Abgeschlossene Checks sind schreibgeschützt")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(check, k, v)
    db.commit()
    return _out(check)


@router.put("/{check_id}/items/{item_id}", response_model=CheckOut)
def update_item(check_id: int, item_id: int, body: CheckItemUpdate, db: Session = Depends(get_db),
                _: User = Depends(current_user)):
    check = _get(db, check_id)
    if check.status == "completed":
        raise HTTPException(409, "Abgeschlossene Checks sind schreibgeschützt")
    item = next((i for i in check.items if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "Prüfpunkt nicht gefunden")
    data = body.model_dump(exclude_unset=True)
    if "answer" in data:
        item.answer = data["answer"]
    if data.get("comment") is not None:
        item.comment = data["comment"]
    _refresh(check)
    db.commit()
    return _out(check)


@router.post("/{check_id}/complete", response_model=CheckOut)
def complete(check_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    check = _get(db, check_id)
    open_items = [i.name for i in check.items if i.answer is None]
    if open_items:
        raise HTTPException(422, f"{len(open_items)} Prüfpunkte sind noch nicht bewertet")
    _refresh(check)
    check.status, check.completed_at = "completed", datetime.now(timezone.utc)
    db.commit()
    return _out(check)


@router.post("/{check_id}/reopen", response_model=CheckOut)
def reopen(check_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    check = _get(db, check_id)
    check.status, check.completed_at = "draft", None
    db.commit()
    return _out(check)


@router.delete("/{check_id}", status_code=204)
def delete_check(check_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    check = _get(db, check_id)
    from ..models import Onboarding
    for ob in db.scalars(select(Onboarding).where(Onboarding.service_check_id == check.id)):
        ob.service_check_id = None
    db.delete(check)
    db.commit()


@router.get("/{check_id}/report.pdf")
def report(check_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    check = _get(db, check_id)
    result = scoring.evaluate(check.items, check.green_min, check.yellow_min)
    pdf = build_report(check, result)
    name = f"ServiceCheck_{check.customer.name}_{check.product_name}".replace(" ", "_")
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "_-") or "ServiceCheck"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"'})
