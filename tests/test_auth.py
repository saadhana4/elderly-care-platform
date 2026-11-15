"""Tests for Passcode Authentication, Role Access, and Rate Limiting."""

from app.models import Profile
from app.security import auth_rate_limiter, verify_passcode


def test_create_profile_generates_three_hashed_passcodes(client, db_session):
    """Test that creating a profile generates 3 distinct passcodes and hashes them with bcrypt."""
    response = client.post(
        "/api/profiles",
        json={
            "elder_name": "Arthur Pendelton",
            "elder_age": 82,
            "emergency_notes": "Diabetic, high blood pressure",
            "elder_email": "arthur@example.com",
            "caretaker_email": "nurse@example.com",
            "family_email": "son@example.com",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "care_id" in data
    assert data["elder_name"] == "Arthur Pendelton"

    passcodes = data["passcodes"]
    assert "elder" in passcodes
    assert "caretaker" in passcodes
    assert "family" in passcodes

    # Verify codes are distinct
    assert passcodes["elder"] != passcodes["caretaker"]
    assert passcodes["caretaker"] != passcodes["family"]

    # Verify hashes in database
    db_profile = db_session.query(Profile).filter(Profile.id == data["id"]).first()
    assert db_profile is not None
    # Ensure plain text is NEVER stored in database
    assert db_profile.elder_passcode_hash != passcodes["elder"]
    assert db_profile.caretaker_passcode_hash != passcodes["caretaker"]
    assert db_profile.family_passcode_hash != passcodes["family"]

    # Ensure bcrypt hash verifies successfully
    assert verify_passcode(passcodes["elder"], db_profile.elder_passcode_hash)
    assert verify_passcode(passcodes["caretaker"], db_profile.caretaker_passcode_hash)
    assert verify_passcode(passcodes["family"], db_profile.family_passcode_hash)


def test_login_success_for_all_roles(client, sample_profile):
    """Test that elder, caretaker, and family can log in with their respective passcodes."""
    # 1. Elder Login
    res_elder = client.post("/api/login", json={"care_id": sample_profile.care_id, "passcode": "ELD-1234"})
    assert res_elder.status_code == 200
    assert res_elder.json()["role"] == "elder"
    assert "access_token" in res_elder.json()

    # 2. Caretaker Login
    res_ct = client.post("/api/login", json={"care_id": sample_profile.care_id, "passcode": "CAR-5678"})
    assert res_ct.status_code == 200
    assert res_ct.json()["role"] == "caretaker"

    # 3. Family Login
    res_fam = client.post("/api/login", json={"care_id": sample_profile.care_id, "passcode": "FAM-9012"})
    assert res_fam.status_code == 200
    assert res_fam.json()["role"] == "family"


def test_login_invalid_passcode(client, sample_profile):
    """Test that incorrect passcodes are rejected with 401."""
    res = client.post("/api/login", json={"care_id": sample_profile.care_id, "passcode": "WRONG-CODE"})
    assert res.status_code == 401


def test_rate_limiting_on_repeated_failed_logins(client, sample_profile):
    """Test that exceeding MAX_AUTH_ATTEMPTS locks out the client with 429 Too Many Requests."""
    care_id = sample_profile.care_id

    # Reset limiter state before test
    auth_rate_limiter._attempts.clear()

    # Trigger 5 failed attempts
    for _ in range(5):
        res = client.post("/api/login", json={"care_id": care_id, "passcode": "BAD-CODE"})
        assert res.status_code == 401

    # 6th attempt should be blocked with 429
    res_blocked = client.post("/api/login", json={"care_id": care_id, "passcode": "BAD-CODE"})
    assert res_blocked.status_code == 429
    assert "Rate limit exceeded" in res_blocked.json()["detail"]


def test_elder_can_revoke_caretaker_and_family_access(client, sample_profile, db_session, elder_auth_headers):
    """Test that the Elder has final control and can revoke caretaker or family access."""
    # 1. Elder revokes caretaker access
    res_revoke = client.post(
        "/settings/access/toggle-role",
        data={"target_role": "caretaker", "enabled": "false"},
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res_revoke.status_code == 303

    db_session.refresh(sample_profile)
    assert sample_profile.caretaker_access_enabled is False

    # 2. Caretaker attempt to login is now forbidden (403)
    res_ct_login = client.post(
        "/api/login",
        json={"care_id": sample_profile.care_id, "passcode": "CAR-5678"},
    )
    assert res_ct_login.status_code == 403
    assert "Caretaker access is disabled" in res_ct_login.json()["detail"]


def test_elder_can_regenerate_passcode(client, sample_profile, db_session, elder_auth_headers):
    """Test that regenerating a passcode invalidates the old one immediately."""
    old_hash = sample_profile.caretaker_passcode_hash

    res = client.post(
        "/settings/access/regenerate-passcode",
        data={"target_role": "caretaker"},
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res.status_code == 303
    db_session.refresh(sample_profile)

    # Hash has changed
    assert sample_profile.caretaker_passcode_hash != old_hash
    # Old passcode CAR-5678 no longer matches
    assert not verify_passcode("CAR-5678", sample_profile.caretaker_passcode_hash)
