from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


settings = get_settings()

engine = create_engine(settings.database_url, future=True, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autoflush=False, autocommit=False, future=True)
SessionLocal.configure(bind=engine)


def init_engine(database_url: str | None = None):
    global engine

    target_url = database_url or settings.database_url
    try:
        engine.dispose()
    except Exception:  # noqa: BLE001
        pass
    engine = create_engine(target_url, future=True, connect_args={"check_same_thread": False})
    SessionLocal.configure(bind=engine)
    return engine


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
