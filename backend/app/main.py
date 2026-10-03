from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


def ensure_case_qty_column() -> None:
    """轻量迁移：老库没有 lanes.case_qty 时补上（默认 1 = 按件补）。"""
    inspector = inspect(engine)
    if "lanes" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("lanes")}
    if "case_qty" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE lanes ADD COLUMN case_qty INTEGER NOT NULL DEFAULT 1"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_case_qty_column()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="VendFill", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
