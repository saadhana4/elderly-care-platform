"""Pytest configuration, fixtures, and in-memory test database."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Profile
from app.security import create_session_token, hash_passcode

# In-memory SQLite for high-speed, isolated testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear rate limiter attempts between tests to prevent test bleed."""
    from app.security import auth_rate_limiter

    auth_rate_limiter._attempts.clear()
    yield
    auth_rate_limiter._attempts.clear()


@pytest.fixture(scope="function")
def db_session():
    """Create fresh database tables for each test function."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def sample_profile(db_session):
    """Pre-created profile with known credentials."""
    profile = Profile(
        care_id="CARE-9999",
        elder_name="Eleanor Vance",
        elder_age=78,
        emergency_notes="Allergic to Penicillin",
        elder_passcode_hash=hash_passcode("ELD-1234"),
        caretaker_passcode_hash=hash_passcode("CAR-5678"),
        family_passcode_hash=hash_passcode("FAM-9012"),
        caretaker_access_enabled=True,
        family_access_enabled=True,
        elder_email="eleanor@example.com",
        caretaker_email="caretaker@example.com",
        family_email="family@example.com",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


@pytest.fixture(scope="function")
def elder_auth_headers(sample_profile):
    """Auth session cookie headers for Elder."""
    token = create_session_token(
        {
            "profile_id": sample_profile.id,
            "care_id": sample_profile.care_id,
            "elder_name": sample_profile.elder_name,
            "role": "elder",
        }
    )
    return {"Cookie": f"carenest_session={token}"}


@pytest.fixture(scope="function")
def caretaker_auth_headers(sample_profile):
    """Auth session cookie headers for Caretaker."""
    token = create_session_token(
        {
            "profile_id": sample_profile.id,
            "care_id": sample_profile.care_id,
            "elder_name": sample_profile.elder_name,
            "role": "caretaker",
        }
    )
    return {"Cookie": f"carenest_session={token}"}


@pytest.fixture(scope="function")
def family_auth_headers(sample_profile):
    """Auth session cookie headers for Family (View-Only)."""
    token = create_session_token(
        {
            "profile_id": sample_profile.id,
            "care_id": sample_profile.care_id,
            "elder_name": sample_profile.elder_name,
            "role": "family",
        }
    )
    return {"Cookie": f"carenest_session={token}"}
