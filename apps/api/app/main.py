from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.content_rules import ensure_content_rule_defaults


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db = SessionLocal()
    try:
        ensure_content_rule_defaults(db)
    except Exception:
        db.rollback()
    finally:
        db.close()
    yield


app = FastAPI(
    title="Home Dry Lab Content Machine API",
    version="0.1.0",
    description="Local-first backend foundation for research-backed content workflows.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
