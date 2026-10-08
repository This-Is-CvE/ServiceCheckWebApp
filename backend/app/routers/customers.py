from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, Onboarding, ServiceCheck, User
from ..schemas import CustomerIn, CustomerOut
from ..security import current_user

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _get(db, id_):
    c = db.get(Customer, id_)
    if not c:
        raise HTTPException(404, "Kunde nicht gefunden")
    return c


@router.get("", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.scalars(select(Customer).order_by(Customer.name)).all()


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    c = Customer(**body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, body: CustomerIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    c = _get(db, customer_id)
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return c


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    c = _get(db, customer_id)
    used = (db.scalar(select(func.count()).select_from(ServiceCheck).where(ServiceCheck.customer_id == c.id))
            or db.scalar(select(func.count()).select_from(Onboarding).where(Onboarding.customer_id == c.id)))
    if used:
        raise HTTPException(409, "Kunde hat noch Service Checks oder Onboardings und kann nicht gelöscht werden")
    db.delete(c)
    db.commit()
