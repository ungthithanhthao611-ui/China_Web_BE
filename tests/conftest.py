from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.db.base  # noqa: F401
from app.api.deps import get_db
from app.api.router import api_router
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminUser
from app.models.base import Base
from app.models.taxonomy import Language


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    db_path = tmp_path / "test_navigation_e2e.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)
    with testing_session_local() as db:
        db.add(Language(id=1, code="en", name="English", is_default=True, status="active"))
        db.add(
            AdminUser(
                username=settings.initial_admin_username,
                password_hash=hash_password(settings.initial_admin_password),
                role="admin",
                is_active=True,
            )
        )
        db.commit()

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def admin_headers() -> dict[str, str]:
    token = create_access_token(subject=settings.initial_admin_username, role="admin")
    return {"Authorization": f"Bearer {token}"}
