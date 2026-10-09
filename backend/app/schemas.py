from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----- Auth / Benutzer -----
class UserOut(ORM):
    id: int
    username: str
    full_name: str
    role: str
    active: bool
    sso: bool = False


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=100)
    full_name: str = ""
    password: str = Field(min_length=8)
    role: Literal["admin", "consultant"] = "consultant"


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=8)
    role: Literal["admin", "consultant"] | None = None
    active: bool | None = None


# ----- Katalog -----
class ParameterIn(BaseModel):
    extension_id: int | None = None  # None = Basiskatalog des Produkts
    category: str = Field(default="Allgemein", max_length=200)
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    weight: int = Field(default=5, ge=1, le=10)
    is_blocker: bool = False
    recommendation: str = ""
    position: int = 0


class ParameterOut(ParameterIn, ORM):
    id: int
    product_id: int


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    green_min: float = Field(default=80, ge=0, le=100)
    yellow_min: float = Field(default=50, ge=0, le=100)


class ExtensionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ExtensionOut(ExtensionIn, ORM):
    id: int
    product_id: int
    parameter_count: int = 0


class ProductOut(ProductIn, ORM):
    id: int
    offer_id: int
    parameter_count: int = 0  # Basiskatalog
    extensions: list[ExtensionOut] = []


class OfferIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class OfferOut(OfferIn, ORM):
    id: int
    products: list[ProductOut] = []


# ----- Kunden -----
class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kt_number: str = Field(default="", max_length=50)
    contact_name: str = ""
    contact_email: str = ""
    notes: str = ""


class CustomerOut(CustomerIn, ORM):
    id: int


# ----- Service Check -----
Answer = Literal["yes", "partial", "no", "na"]


class CheckCreate(BaseModel):
    customer_id: int
    product_id: int
    extension_ids: list[int] = []
    title: str = ""
    system_description: str = ""


class ExtensionSelection(BaseModel):
    extension_ids: list[int] = []


class CheckUpdate(BaseModel):
    title: str | None = None
    system_description: str | None = None


class CheckItemUpdate(BaseModel):
    answer: Answer | None = None
    comment: str | None = None


class CheckItemOut(ORM):
    id: int
    category: str
    extension_name: str | None
    section: str
    name: str
    description: str
    weight: int
    is_blocker: bool
    recommendation: str
    answer: str | None
    comment: str


class CheckListOut(ORM):
    id: int
    title: str
    product_id: int | None
    customer_id: int
    customer_name: str
    customer_kt_number: str
    offer_name: str
    product_name: str
    status: str
    score: float | None
    light: str
    created_at: datetime
    completed_at: datetime | None


class CheckOut(CheckListOut):
    system_description: str
    extensions: list[dict]
    green_min: float
    yellow_min: float
    created_by: str | None
    items: list[CheckItemOut]
    result: dict


# ----- Onboarding -----
Section = Literal["general", "checklist", "readiness"]


class TemplateItemIn(BaseModel):
    extension_id: int | None = None  # None = Basisvorlage des Produkts
    section: Section
    label: str = Field(min_length=1, max_length=300)
    help: str = ""
    field_type: Literal["text", "textarea", "date"] = "text"
    required: bool = True
    position: int = 0


class TemplateItemOut(TemplateItemIn, ORM):
    id: int
    product_id: int


class OnboardingCreate(BaseModel):
    customer_id: int
    product_id: int
    extension_ids: list[int] = []
    title: str = ""
    service_check_id: int | None = None


class OnboardingItemUpdate(BaseModel):
    value: str | None = None
    done: bool | None = None
    comment: str | None = None


class OnboardingItemOut(ORM):
    id: int
    extension_name: str | None
    section: str
    label: str
    help: str
    field_type: str
    required: bool
    value: str
    done: bool
    comment: str


class AssetIn(BaseModel):
    category: str = "Server"
    name: str = Field(min_length=1, max_length=300)
    model: str = ""
    serial_number: str = ""
    product_version: str = ""
    quantity: int = Field(default=1, ge=1)
    location: str = ""
    notes: str = ""


class AssetOut(AssetIn, ORM):
    id: int


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = ""
    phone: str = ""
    mobile: str = ""
    email: str = ""
    notes: str = ""


class ContactOut(ContactIn, ORM):
    id: int


class DocumentOut(ORM):
    id: int
    filename: str
    size: int
    created_by: str
    created_at: datetime


class OnboardingListOut(ORM):
    id: int
    title: str
    product_id: int | None
    customer_id: int
    customer_name: str
    customer_kt_number: str
    offer_name: str
    product_name: str
    status: str
    progress: float
    created_at: datetime


class OnboardingOut(OnboardingListOut):
    service_check_id: int | None
    extensions: list[dict]
    completed_at: datetime | None
    items: list[OnboardingItemOut]
    assets: list[AssetOut]
    contacts: list[ContactOut]
    open_required: list[str]
    documents: list[DocumentOut]
