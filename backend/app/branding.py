"""Firmenlogo: eigenes Logo aus der Datenbank, sonst das mitgelieferte Standardlogo (app/assets/logo.png).

Erlaubt sind nur PNG und JPEG. SVG bewusst nicht: Es kann Skripte enthalten und lässt sich im PDF nicht verwenden.
"""
import hashlib
import io
import os
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image as PILImage
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import BrandingLogo

DEFAULT_LOGO = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
MAX_BYTES = 1_000_000
MAX_SIDE = 4000
MIN_SIDE = 16
FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg"}


@dataclass(frozen=True)
class Logo:
    data: bytes
    content_type: str
    width: int
    height: int

    @property
    def etag(self) -> str:
        return hashlib.sha256(self.data).hexdigest()[:24]


class LogoError(ValueError):
    """Die hochgeladene Datei ist als Logo nicht zulässig (Meldung ist für den Benutzer bestimmt)."""


def inspect(data: bytes) -> tuple[str, int, int]:
    """Prüft die Datei und liefert (Content-Type, Breite, Höhe). Wirft LogoError."""
    if not data:
        raise LogoError("Die Datei ist leer.")
    if len(data) > MAX_BYTES:
        raise LogoError(f"Die Datei ist zu groß (höchstens {MAX_BYTES // 1_000_000} MB).")
    try:
        img = PILImage.open(io.BytesIO(data))
        fmt, (w, h) = img.format, img.size  # liest nur den Kopf der Datei
        if fmt not in FORMATS:
            raise LogoError("Nur PNG- und JPEG-Dateien sind erlaubt.")
        if not (MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= h <= MAX_SIDE):
            raise LogoError(f"Das Bild muss zwischen {MIN_SIDE} und {MAX_SIDE} Pixel breit und hoch sein (ist {w} × {h}).")
        img.verify()  # prüft die Datei auf Beschädigung
    except LogoError:
        raise
    except Exception:
        raise LogoError("Die Datei ist kein gültiges PNG- oder JPEG-Bild.") from None
    return FORMATS[fmt], w, h


@lru_cache(maxsize=1)
def _default() -> Logo:
    with open(DEFAULT_LOGO, "rb") as f:
        data = f.read()
    content_type, w, h = inspect(data)
    return Logo(data, content_type, w, h)


def current_logo(db: Session | None = None) -> Logo:
    """Das gültige Logo. Ohne Sitzung öffnet die Funktion selbst eine (z. B. beim Erzeugen von PDFs)."""
    if db is None:
        with SessionLocal() as own:
            return current_logo(own)
    row = db.get(BrandingLogo, 1)
    if row is None:
        return _default()
    return Logo(row.data, row.content_type, row.width, row.height)
