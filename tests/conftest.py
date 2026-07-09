import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

TEST_DB = tempfile.NamedTemporaryFile(prefix="executiveos-test-", suffix=".db", delete=False)
TEST_DB.close()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.name}"

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed_data  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()
    yield
