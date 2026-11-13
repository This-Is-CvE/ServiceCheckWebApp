from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..branding import MAX_BYTES, LogoError, current_logo, inspect
from ..database import get_db
from ..models import BrandingLogo, User, now
from ..security import admin_user

router = APIRouter(prefix="/api/branding", tags=["branding"])


class BrandingOut(BaseModel):
    custom: bool
    width: int
    height: int
    updated_by: str | None = None
    updated_at: datetime | None = None


def _info(db: Session) -> BrandingOut:
    row = db.get(BrandingLogo, 1)
    if row is None:
        logo = current_logo(db)
        return BrandingOut(custom=False, width=logo.width, height=logo.height)
    return BrandingOut(custom=True, width=row.width, height=row.height, updated_by=row.updated_by, updated_at=row.updated_at)


@router.get("/logo")
def get_logo(request: Request, db: Session = Depends(get_db)):
    """Öffentlich, weil das Logo auch auf der Anmeldeseite erscheint. Der Browser prüft vor jeder Nutzung per ETag."""
    logo = current_logo(db)
    headers = {"ETag": f'"{logo.etag}"', "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}
    if request.headers.get("if-none-match") == headers["ETag"]:
        return Response(status_code=304, headers=headers)
    return Response(logo.data, media_type=logo.content_type, headers=headers)


@router.get("", response_model=BrandingOut)
def get_branding(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    return _info(db)


@router.put("/logo", response_model=BrandingOut)
def put_logo(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(admin_user)):
    data = file.file.read(MAX_BYTES + 1)
    try:
        content_type, width, height = inspect(data)
    except LogoError as exc:
        raise HTTPException(413 if len(data) > MAX_BYTES else 400, str(exc)) from None
    row = db.get(BrandingLogo, 1) or BrandingLogo(id=1)
    row.data, row.content_type, row.width, row.height = data, content_type, width, height
    row.updated_by, row.updated_at = user.username, now()
    db.add(row)
    db.commit()
    return _info(db)


@router.delete("/logo", status_code=204)
def delete_logo(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    row = db.get(BrandingLogo, 1)
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=204)
