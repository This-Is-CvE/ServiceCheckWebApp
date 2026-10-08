import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .database import Base, SessionLocal, engine
from .routers import auth, catalog, checks, customers, onboarding
from .seed import seed_admin, seed_demo


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_admin(db)
        if config.SEED_DEMO_DATA:
            seed_demo(db)
    yield


app = FastAPI(title="Service Check & Onboarding", lifespan=lifespan)
for r in (auth, catalog, customers, checks, onboarding):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Frontend (gebauter Vite-Output) aus dem gleichen Prozess ausliefern
_static = os.path.abspath(config.FRONTEND_DIR)
if os.path.isdir(_static):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = os.path.join(_static, path)
        if path and os.path.isfile(candidate) and os.path.abspath(candidate).startswith(_static):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_static, "index.html"))
