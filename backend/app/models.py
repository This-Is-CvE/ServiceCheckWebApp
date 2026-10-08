from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="consultant")  # admin | consultant
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------- Katalog ----------

class Offer(Base):
    """Managed Service Offer, z. B. 'Managed Virtual Infrastructure'."""
    __tablename__ = "offers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    products: Mapped[list["Product"]] = relationship(
        back_populates="offer", cascade="all, delete-orphan", order_by="Product.name")
    template_items: Mapped[list["OnboardingTemplateItem"]] = relationship(
        cascade="all, delete-orphan", order_by="OnboardingTemplateItem.position")


class Product(Base):
    """Unterstütztes Produkt eines Offers, z. B. 'VMware vSphere (inkl. vSAN)'."""
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    green_min: Mapped[float] = mapped_column(Float, default=80)
    yellow_min: Mapped[float] = mapped_column(Float, default=50)
    offer: Mapped[Offer] = relationship(back_populates="products")
    parameters: Mapped[list["Parameter"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="Parameter.position, Parameter.id")


class Parameter(Base):
    __tablename__ = "parameters"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    category: Mapped[str] = mapped_column(String(200), default="Allgemein")
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[int] = mapped_column(Integer, default=5)  # 1..10
    is_blocker: Mapped[bool] = mapped_column(Boolean, default=False)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    product: Mapped[Product] = relationship(back_populates="parameters")


# ---------- Kunden ----------

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_email: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")


# ---------- Service Check (Modul 1) ----------

class ServiceCheck(Base):
    __tablename__ = "service_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    offer_name: Mapped[str] = mapped_column(String(200))
    product_name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    system_description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | completed
    green_min: Mapped[float] = mapped_column(Float, default=80)
    yellow_min: Mapped[float] = mapped_column(Float, default=50)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    light: Mapped[str] = mapped_column(String(10), default="grey")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Customer] = relationship()
    created_by: Mapped[User | None] = relationship()
    items: Mapped[list["CheckItem"]] = relationship(
        cascade="all, delete-orphan", order_by="CheckItem.position, CheckItem.id")


class CheckItem(Base):
    """Snapshot eines Katalogparameters im Check; spätere Katalogänderungen wirken nicht zurück."""
    __tablename__ = "check_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("service_checks.id"))
    category: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[int] = mapped_column(Integer, default=5)
    is_blocker: Mapped[bool] = mapped_column(Boolean, default=False)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    answer: Mapped[str | None] = mapped_column(String(10), nullable=True)  # yes | partial | no | na
    comment: Mapped[str] = mapped_column(Text, default="")


# ---------- Onboarding (Modul 2) ----------

class OnboardingTemplateItem(Base):
    __tablename__ = "onboarding_template_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"))
    section: Mapped[str] = mapped_column(String(20))  # general | checklist | readiness
    label: Mapped[str] = mapped_column(String(300))
    help: Mapped[str] = mapped_column(Text, default="")
    field_type: Mapped[str] = mapped_column(String(20), default="text")  # text | textarea | date (nur general)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Onboarding(Base):
    __tablename__ = "onboardings"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id"), nullable=True)
    offer_name: Mapped[str] = mapped_column(String(200))
    service_check_id: Mapped[int | None] = mapped_column(ForeignKey("service_checks.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | completed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Customer] = relationship()
    items: Mapped[list["OnboardingItem"]] = relationship(
        cascade="all, delete-orphan", order_by="OnboardingItem.position, OnboardingItem.id")
    assets: Mapped[list["OnboardingAsset"]] = relationship(
        cascade="all, delete-orphan", order_by="OnboardingAsset.id")


class OnboardingItem(Base):
    __tablename__ = "onboarding_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    onboarding_id: Mapped[int] = mapped_column(ForeignKey("onboardings.id"))
    section: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(300))
    help: Mapped[str] = mapped_column(Text, default="")
    field_type: Mapped[str] = mapped_column(String(20), default="text")
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    value: Mapped[str] = mapped_column(Text, default="")
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str] = mapped_column(Text, default="")


class OnboardingAsset(Base):
    """Installierte technische Basis des Kunden."""
    __tablename__ = "onboarding_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    onboarding_id: Mapped[int] = mapped_column(ForeignKey("onboardings.id"))
    category: Mapped[str] = mapped_column(String(100), default="Server")
    name: Mapped[str] = mapped_column(String(300))
    product_version: Mapped[str] = mapped_column(String(200), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    location: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
