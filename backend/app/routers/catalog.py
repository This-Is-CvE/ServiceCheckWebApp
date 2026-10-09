from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Offer, Onboarding, OnboardingTemplateItem, Parameter, Product, ProductExtension, ServiceCheck,
                      User)
from ..schemas import (ExtensionIn, ExtensionOut, OfferIn, OfferOut, ParameterIn, ParameterOut, ProductIn, ProductOut,
                       TemplateItemIn, TemplateItemOut)
from ..security import admin_user, current_user
from ..seed import default_template_items

router = APIRouter(prefix="/api", tags=["catalog"])


def _count(db: Session, **where) -> int:
    q = select(func.count()).select_from(Parameter)
    for k, v in where.items():
        q = q.where(getattr(Parameter, k).is_(None) if v is None else getattr(Parameter, k) == v)
    return db.scalar(q) or 0


def _ext_out(db: Session, e: ProductExtension) -> ExtensionOut:
    out = ExtensionOut.model_validate(e)
    out.parameter_count = _count(db, extension_id=e.id)
    return out


def _product_out(db: Session, p: Product) -> ProductOut:
    out = ProductOut.model_validate(p, from_attributes=True)
    out.parameter_count = _count(db, product_id=p.id, extension_id=None)
    out.extensions = [_ext_out(db, e) for e in p.extensions]
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


def _check_extension(db: Session, product_id: int, extension_id: int | None) -> None:
    if extension_id is not None:
        ext = db.get(ProductExtension, extension_id)
        if not ext or ext.product_id != product_id:
            raise HTTPException(422, "Die Erweiterung gehört nicht zu diesem Produkt")


def _drop_product_refs(db: Session, product_ids: list[int]) -> None:
    db.execute(update(ServiceCheck).where(ServiceCheck.product_id.in_(product_ids)).values(product_id=None))
    db.execute(update(Onboarding).where(Onboarding.product_id.in_(product_ids)).values(product_id=None))


# ----- Managed Services (Offers) -----
@router.get("/offers", response_model=list[OfferOut])
def list_offers(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_offer_out(db, o) for o in db.scalars(select(Offer).order_by(Offer.name))]


@router.post("/offers", response_model=OfferOut, status_code=201)
def create_offer(body: OfferIn, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    if db.scalar(select(Offer).where(Offer.name == body.name)):
        raise HTTPException(409, "Ein Managed Service mit diesem Namen existiert bereits")
    offer = Offer(**body.model_dump())
    db.add(offer)
    db.commit()
    return _offer_out(db, offer)


@router.put("/offers/{offer_id}", response_model=OfferOut)
def update_offer(offer_id: int, body: OfferIn, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    offer = _get(db, Offer, offer_id, "Managed Service")
    for k, v in body.model_dump().items():
        setattr(offer, k, v)
    db.commit()
    return _offer_out(db, offer)


@router.delete("/offers/{offer_id}", status_code=204)
def delete_offer(offer_id: int, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    offer = _get(db, Offer, offer_id, "Managed Service")
    _drop_product_refs(db, [p.id for p in offer.products])
    for p in offer.products:
        _delete_product_contents(db, p)
    db.delete(offer)
    db.commit()


# ----- Produkte -----
def _delete_product_contents(db: Session, product: Product) -> None:
    """Parameter und Vorlagenpunkte vor Erweiterungen löschen (Reihenfolge wegen Fremdschlüsseln)."""
    db.execute(delete(Parameter).where(Parameter.product_id == product.id))
    db.execute(delete(OnboardingTemplateItem).where(OnboardingTemplateItem.product_id == product.id))
    db.expire(product)


@router.post("/offers/{offer_id}/products", response_model=ProductOut, status_code=201)
def create_product(offer_id: int, body: ProductIn, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    _get(db, Offer, offer_id, "Managed Service")
    _check_thresholds(body.green_min, body.yellow_min)
    product = Product(offer_id=offer_id, **body.model_dump())
    product.template_items = default_template_items()  # Standard-Onboarding-Vorlage, danach frei anpassbar
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
    _drop_product_refs(db, [product.id])
    _delete_product_contents(db, product)
    db.delete(product)
    db.commit()


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _product_out(db, _get(db, Product, product_id, "Produkt"))


# ----- Erweiterungskataloge -----
@router.post("/products/{product_id}/extensions", response_model=ExtensionOut, status_code=201)
def create_extension(product_id: int, body: ExtensionIn, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    product = _get(db, Product, product_id, "Produkt")
    if any(e.name == body.name for e in product.extensions):
        raise HTTPException(409, "Eine Erweiterung mit diesem Namen existiert bereits")
    ext = ProductExtension(product_id=product_id, position=max((e.position for e in product.extensions), default=0) + 10,
                           **body.model_dump())
    db.add(ext)
    db.commit()
    return _ext_out(db, ext)


@router.put("/extensions/{ext_id}", response_model=ExtensionOut)
def update_extension(ext_id: int, body: ExtensionIn, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    ext = _get(db, ProductExtension, ext_id, "Erweiterung")
    for k, v in body.model_dump().items():
        setattr(ext, k, v)
    db.commit()
    return _ext_out(db, ext)


@router.delete("/extensions/{ext_id}", status_code=204)
def delete_extension(ext_id: int, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    ext = _get(db, ProductExtension, ext_id, "Erweiterung")
    db.execute(delete(Parameter).where(Parameter.extension_id == ext.id))
    db.execute(delete(OnboardingTemplateItem).where(OnboardingTemplateItem.extension_id == ext.id))
    db.delete(ext)
    db.commit()


# ----- Parameter -----
@router.get("/products/{product_id}/parameters", response_model=list[ParameterOut])
def list_parameters(product_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Alle Parameter des Produkts: Basiskatalog (extension_id = null) und alle Erweiterungen."""
    return _get(db, Product, product_id, "Produkt").parameters


@router.post("/products/{product_id}/parameters", response_model=ParameterOut, status_code=201)
def create_parameter(product_id: int, body: ParameterIn, db: Session = Depends(get_db),
                     _: User = Depends(admin_user)):
    product = _get(db, Product, product_id, "Produkt")
    _check_extension(db, product_id, body.extension_id)
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
    _check_extension(db, param.product_id, body.extension_id)
    for k, v in body.model_dump().items():
        setattr(param, k, v)
    db.commit()
    return param


@router.delete("/parameters/{param_id}", status_code=204)
def delete_parameter(param_id: int, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    db.delete(_get(db, Parameter, param_id, "Parameter"))
    db.commit()


# ----- Onboarding-Vorlagen (pro Produkt, optional pro Erweiterung) -----
@router.get("/products/{product_id}/template", response_model=list[TemplateItemOut])
def get_template(product_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _get(db, Product, product_id, "Produkt").template_items


@router.post("/products/{product_id}/template", response_model=TemplateItemOut, status_code=201)
def create_template_item(product_id: int, body: TemplateItemIn, db: Session = Depends(get_db),
                         _: User = Depends(admin_user)):
    product = _get(db, Product, product_id, "Produkt")
    _check_extension(db, product_id, body.extension_id)
    data = body.model_dump()
    if not data["position"]:
        data["position"] = max((i.position for i in product.template_items), default=0) + 10
    item = OnboardingTemplateItem(product_id=product_id, **data)
    db.add(item)
    db.commit()
    return item


@router.put("/template-items/{item_id}", response_model=TemplateItemOut)
def update_template_item(item_id: int, body: TemplateItemIn, db: Session = Depends(get_db),
                         _: User = Depends(admin_user)):
    item = _get(db, OnboardingTemplateItem, item_id, "Vorlagenpunkt")
    _check_extension(db, item.product_id, body.extension_id)
    for k, v in body.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return item


@router.delete("/template-items/{item_id}", status_code=204)
def delete_template_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    db.delete(_get(db, OnboardingTemplateItem, item_id, "Vorlagenpunkt"))
    db.commit()
