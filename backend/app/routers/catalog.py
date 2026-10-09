from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Offer, Onboarding, OnboardingTemplateItem, Parameter, Product, ServiceCheck, User)
from ..schemas import (OfferIn, OfferOut, ParameterIn, ParameterOut, ProductIn, ProductOut, TemplateItemIn,
                       TemplateItemOut)
from ..security import admin_user, current_user
from ..seed import default_template_items

router = APIRouter(prefix="/api", tags=["catalog"])


def _product_out(db: Session, p: Product) -> ProductOut:
    out = ProductOut.model_validate(p)
    out.parameter_count = db.scalar(select(func.count()).select_from(Parameter).where(Parameter.product_id == p.id)) or 0
    return out


def _offer_out(db: Session, o: Offer) -> OfferOut:
    return OfferOut(id=o.id, name=o.name, description=o.description,
                    products=[_product_out(db, p) for p in o.products])


def _get(db, model, id_, what):
    obj = db.get(model, id_)
    if not obj:
        raise HTTPException(404, f"{what} nicht gefunden")
    return obj


def _check_thresholds(green, yellow):
    if yellow > green:
        raise HTTPException(422, "Die Gelb-Schwelle darf nicht über der Grün-Schwelle liegen")


# ----- Offers -----
@router.get("/offers", response_model=list[OfferOut])
def list_offers(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_offer_out(db, o) for o in db.scalars(select(Offer).order_by(Offer.name))]


@router.post("/offers", response_model=OfferOut, status_code=201)
def create_offer(body: OfferIn, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    if db.scalar(select(Offer).where(Offer.name == body.name)):
        raise HTTPException(409, "Offer existiert bereits")
    offer = Offer(**body.model_dump())
    offer.template_items = default_template_items()  # Standard-Onboarding-Vorlage, danach frei anpassbar
    db.add(offer)
    db.commit()
    return _offer_out(db, offer)


@router.put("/offers/{offer_id}", response_model=OfferOut)
def update_offer(offer_id: int, body: OfferIn, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    offer = _get(db, Offer, offer_id, "Offer")
    for k, v in body.model_dump().items():
        setattr(offer, k, v)
    db.commit()
    return _offer_out(db, offer)


@router.delete("/offers/{offer_id}", status_code=204)
def delete_offer(offer_id: int, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    offer = _get(db, Offer, offer_id, "Offer")
    for p in offer.products:
        db.execute(update(ServiceCheck).where(ServiceCheck.product_id == p.id).values(product_id=None))
    db.execute(update(Onboarding).where(Onboarding.offer_id == offer.id).values(offer_id=None))
    db.delete(offer)
    db.commit()


# ----- Produkte -----
@router.post("/offers/{offer_id}/products", response_model=ProductOut, status_code=201)
def create_product(offer_id: int, body: ProductIn, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    _get(db, Offer, offer_id, "Offer")
    _check_thresholds(body.green_min, body.yellow_min)
    product = Product(offer_id=offer_id, **body.model_dump())
    db.add(product)
    db.commit()
    return _product_out(db, product)


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductIn, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    product = _get(db, Product, product_id, "Produkt")
    _check_thresholds(body.green_min, body.yellow_min)
    for k, v in body.model_dump().items():
        setattr(product, k, v)
    db.commit()
    return _product_out(db, product)


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    product = _get(db, Product, product_id, "Produkt")
    db.execute(update(ServiceCheck).where(ServiceCheck.product_id == product.id).values(product_id=None))
    db.delete(product)
    db.commit()


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _product_out(db, _get(db, Product, product_id, "Produkt"))


# ----- Parameter -----
@router.get("/products/{product_id}/parameters", response_model=list[ParameterOut])
def list_parameters(product_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _get(db, Product, product_id, "Produkt").parameters


@router.post("/products/{product_id}/parameters", response_model=ParameterOut, status_code=201)
def create_parameter(product_id: int, body: ParameterIn, db: Session = Depends(get_db),
                     _: User = Depends(admin_user)):
    product = _get(db, Product, product_id, "Produkt")
    data = body.model_dump()
    if not data["position"]:
        data["position"] = max((p.position for p in product.parameters), default=0) + 10
    param = Parameter(product_id=product_id, **data)
    db.add(param)
    db.commit()
    return param


@router.put("/parameters/{param_id}", response_model=ParameterOut)
def update_parameter(param_id: int, body: ParameterIn, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    param = _get(db, Parameter, param_id, "Parameter")
    for k, v in body.model_dump().items():
        setattr(param, k, v)
    db.commit()
    return param


@router.delete("/parameters/{param_id}", status_code=204)
def delete_parameter(param_id: int, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    db.delete(_get(db, Parameter, param_id, "Parameter"))
    db.commit()


# ----- Onboarding-Vorlagen -----
@router.get("/offers/{offer_id}/template", response_model=list[TemplateItemOut])
def get_template(offer_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _get(db, Offer, offer_id, "Offer").template_items


@router.post("/offers/{offer_id}/template", response_model=TemplateItemOut, status_code=201)
def create_template_item(offer_id: int, body: TemplateItemIn, db: Session = Depends(get_db),
                         _: User = Depends(admin_user)):
    offer = _get(db, Offer, offer_id, "Offer")
    data = body.model_dump()
    if not data["position"]:
        data["position"] = max((i.position for i in offer.template_items), default=0) + 10
    item = OnboardingTemplateItem(offer_id=offer_id, **data)
    db.add(item)
    db.commit()
    return item


@router.put("/template-items/{item_id}", response_model=TemplateItemOut)
def update_template_item(item_id: int, body: TemplateItemIn, db: Session = Depends(get_db),
                         _: User = Depends(admin_user)):
    item = _get(db, OnboardingTemplateItem, item_id, "Vorlagenpunkt")
    for k, v in body.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return item


@router.delete("/template-items/{item_id}", status_code=204)
def delete_template_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    db.delete(_get(db, OnboardingTemplateItem, item_id, "Vorlagenpunkt"))
    db.commit()
