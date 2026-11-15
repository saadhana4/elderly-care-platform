"""Tests for Accessibility (WCAG 2.2 AA/AAA) and Problem Statement Alignment.

Validates semantic HTML landmarks, skip links, aria attributes, screen reader
announcement regions, Web Speech read aloud triggers, and elder-centred design.
"""

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Profile
from app.security import hash_passcode


def _create_sample_profile(db_session: Session) -> Profile:
    """Helper to create an active profile for testing."""
    profile = Profile(
        care_id="CARE-ACC1",
        elder_name="Eleanor Accessibility",
        elder_passcode_hash=hash_passcode("ELD-1111"),
        caretaker_passcode_hash=hash_passcode("CAR-2222"),
        family_passcode_hash=hash_passcode("FAM-3333"),
        caretaker_access_enabled=True,
        family_access_enabled=True,
        elder_email="eleanor@test.com",
        caretaker_email="nurse@test.com",
        family_email="sarah@test.com",
        emergency_notes="Allergic to Penicillin",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


def test_base_layout_accessibility_landmarks_and_skip_link(client: TestClient) -> None:
    """Verifies WCAG landmarks, lang attribute, skip link, and aria-live status region."""
    response = client.get("/login")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    # 1. <html> must have lang attribute
    html_tag = soup.find("html")
    assert html_tag is not None
    assert html_tag.get("lang") == "en"

    # 2. Skip link pointing to #main-content
    skip_link = soup.find("a", class_="skip-link")
    assert skip_link is not None
    assert skip_link.get("href") == "#main-content"

    # 3. Landmarks
    header = soup.find("header", class_="app-header")
    assert header is not None
    assert header.get("role") == "banner"

    main = soup.find("main", id="main-content")
    assert main is not None
    assert main.get("role") == "main"
    assert main.get("tabindex") == "-1"

    footer = soup.find("footer", class_="app-footer")
    assert footer is not None
    assert footer.get("role") == "contentinfo"

    # 4. Persistent screen reader live announcement region
    announcer = soup.find("div", id="status-announcer")
    assert announcer is not None
    assert announcer.get("role") == "status"
    assert announcer.get("aria-live") == "polite"
    assert "sr-only" in announcer.get("class", [])

    # 5. Accessibility toolbar buttons
    text_size_btn = soup.find("button", id="toggle-text-size")
    assert text_size_btn is not None
    contrast_btn = soup.find("button", id="toggle-contrast")
    assert contrast_btn is not None


def test_login_and_create_profile_form_accessibility(client: TestClient) -> None:
    """Verifies that all form controls have visible labels, aria-required, and aria-describedby."""
    # Check /login
    login_resp = client.get("/login")
    soup_login = BeautifulSoup(login_resp.text, "html.parser")

    care_id_input = soup_login.find("input", id="care_id")
    assert care_id_input is not None
    assert care_id_input.get("aria-required") == "true"
    assert care_id_input.get("aria-describedby") == "care_id_hint"

    care_id_label = soup_login.find("label", attrs={"for": "care_id"})
    assert care_id_label is not None

    passcode_input = soup_login.find("input", id="passcode")
    assert passcode_input is not None
    assert passcode_input.get("aria-required") == "true"
    assert passcode_input.get("aria-describedby") == "passcode_hint"

    # Exactly one h1 per page
    h1s = soup_login.find_all("h1")
    assert len(h1s) == 1

    # Check /create-profile
    create_resp = client.get("/create-profile")
    soup_create = BeautifulSoup(create_resp.text, "html.parser")

    name_input = soup_create.find("input", id="elder_name")
    assert name_input is not None
    assert name_input.get("aria-required") == "true"
    assert name_input.get("aria-describedby") == "name_hint"

    h1_create = soup_create.find_all("h1")
    assert len(h1_create) == 1


def test_today_view_accessibility_and_problem_alignment(
    client: TestClient, db_session: Session
) -> None:
    """Verifies read aloud button, table captions/scope, and elder-centred design banners."""
    _create_sample_profile(db_session)

    # Log in as elder
    login_resp = client.post(
        "/login",
        data={"care_id": "CARE-ACC1", "passcode": "ELD-1111"},
        follow_redirects=True,
    )
    assert login_resp.status_code == 200

    today_resp = client.get("/today")
    assert today_resp.status_code == 200
    soup = BeautifulSoup(today_resp.text, "html.parser")

    # 1. Read aloud button present for speech synthesis
    read_aloud_btn = soup.find("button", id="btn-read-aloud")
    assert read_aloud_btn is not None
    assert "Read today's medication routine aloud" in read_aloud_btn.get("aria-label", "")

    # 2. Collaborative care circle banner explaining elder sovereign control and proactive alerts
    care_circle_text = soup.get_text()
    assert "Elder-Centred Care Circle" in care_circle_text
    assert "Elder Sovereign Control" in care_circle_text
    assert "proactive email alerts" in care_circle_text

    # 3. Exactly one h1 on the page
    h1s = soup.find_all("h1")
    assert len(h1s) == 1
    assert "Today's Medication Routine" in h1s[0].get_text()


def test_access_management_elder_control_and_passcode_guidance(
    client: TestClient, db_session: Session
) -> None:
    """Verifies that access settings clearly explain elder authority and role passcodes."""
    _create_sample_profile(db_session)

    # Log in as elder
    client.post(
        "/login",
        data={"care_id": "CARE-ACC1", "passcode": "ELD-1111"},
        follow_redirects=True,
    )

    settings_resp = client.get("/settings/access")
    assert settings_resp.status_code == 200
    soup = BeautifulSoup(settings_resp.text, "html.parser")

    text = soup.get_text()
    # Plain language guidance
    assert "Why Role Passcodes Instead of Passwords?" in text
    assert "Elder (You): Sovereign decision-maker" in text
    assert "Caretaker: Day-to-day healthcare assistant" in text
    assert "Family: Monitoring and peace of mind" in text
    assert "automated email alerts for missed doses" in text

    # Elder has revoke & regenerate buttons
    assert "Revoke Caretaker Access" in text or "Re-Enable Caretaker Access" in text
    assert "Generate Fresh Caretaker Passcode" in text
    assert "Revoke Family Access" in text or "Re-Enable Family Access" in text
    assert "Generate Fresh Family Passcode" in text
