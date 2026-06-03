from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.base import Base
from app.db import session as db_session


@pytest.fixture(autouse=True)
def isolated_test_database(tmp_path):
    test_db_path = tmp_path / "test-app.db"
    db_session.init_engine(f"sqlite:///{test_db_path.as_posix()}")
    Base.metadata.create_all(bind=db_session.engine)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=db_session.engine)
        db_session.init_engine()
