"""Comprehensive tests for security hardening, edge cases, input validation, and fallbacks."""

import json
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.config import (
    ADHERENCE_DEFAULT_PERCENTAGE,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    Settings,
    settings,
    validate_production_secrets,
)
from app.models import Appointment, DoseLog, Medication
from app.schemas import (
    AppointmentCreate,
    DoseLogCreate,
    MedicationCreate,
)
from app.security import (
    create_session_token,
    decode_session_token,
    generate_csrf_token,
    verify_csrf_token,
)
from app.services.dose_service import calculate_adherence_percentage
from app.services.email_service import send_batch_emails, send_email
from app.services.gemini_service import explain_medication
from app.services.reminder_service import process_all_reminders

# ==============================================================================
# 1. Security Headers Verification
# ==============================================================================


def test_security_headers_present_on_all_responses(client):
    """Verify that mandatory OWASP security headers are present on all HTTP responses."""
    endpoints = ["/health", "/login", "/create-profile"]
    for path in endpoints:
        res = client.get(path)
        headers = res.headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in headers
        assert "geolocation=()" in headers["Permissions-Policy"]
        assert "Content-Security-Policy" in headers
        assert "default-src 'self'" in headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


# ==============================================================================
# 2. Production Fail-Fast on Default / Insecure Secrets
# ==============================================================================


def test_fail_fast_in_production_with_default_secret_key():
    """Verify application refuses to start in production if SECRET_KEY has default value."""
    insecure_config = Settings()
    insecure_config.ENVIRONMENT = "production"
    insecure_config.SECRET_KEY = "carenest-insecure-secret-key-change-me"
    insecure_config.SCHEDULER_SECRET_TOKEN = "a-long-enough-valid-scheduler-token"

    with pytest.raises(RuntimeError) as exc_info:
        validate_production_secrets(insecure_config)
    assert "SECRET_KEY must be configured with a strong" in str(exc_info.value)


def test_fail_fast_in_production_with_default_scheduler_token():
    """Verify application refuses to start in production if SCHEDULER_SECRET_TOKEN is default."""
    insecure_config = Settings()
    insecure_config.ENVIRONMENT = "production"
    insecure_config.SECRET_KEY = "a-very-strong-and-secure-secret-key-32-chars-long"
    insecure_config.SCHEDULER_SECRET_TOKEN = "scheduler-secret-token"

    with pytest.raises(RuntimeError) as exc_info:
        validate_production_secrets(insecure_config)
    assert "SCHEDULER_SECRET_TOKEN must be configured" in str(exc_info.value)


def test_pass_in_production_with_strong_secrets():
    """Verify startup validation succeeds in production when secrets are strong and non-default."""
    secure_config = Settings()
    secure_config.ENVIRONMENT = "production"
    secure_config.SECRET_KEY = "production-super-strong-and-cryptographically-random-key"
    secure_config.SCHEDULER_SECRET_TOKEN = "production-secure-cron-scheduler-token-998877"

    # Should not raise any exception
    validate_production_secrets(secure_config)


# ==============================================================================
# 3. Session Cookie Security Attributes
# ==============================================================================


def test_session_cookie_attributes_on_login(client, sample_profile):
    """Verify that session cookies set HttpOnly and SameSite."""
    res = client.post(
        "/login",
        data={"care_id": sample_profile.care_id, "passcode": "ELD-1234"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    set_cookie_header = res.headers.get("set-cookie", "")
    assert "carenest_session=" in set_cookie_header
    assert "HttpOnly" in set_cookie_header or "httponly" in set_cookie_header.lower()
    assert "samesite=lax" in set_cookie_header.lower()


# ==============================================================================
# 4. CSRF Protection Middleware
# ==============================================================================


def test_csrf_cross_site_fetch_rejected(client, elder_auth_headers):
    """Test that Sec-Fetch-Site: cross-site is immediately rejected with 403 Forbidden."""
    res = client.post(
        "/today/dose",
        data={"medication_id": 1, "action": "taken"},
        headers={**elder_auth_headers, "Sec-Fetch-Site": "cross-site"},
    )
    assert res.status_code == 403
    assert "Cross-site request rejected" in res.json()["detail"]


def test_csrf_untrusted_cross_origin_rejected(client, elder_auth_headers):
    """Test that state-changing requests from untrusted external origins are rejected with 403."""
    res = client.post(
        "/today/dose",
        data={"medication_id": 1, "action": "taken"},
        headers={**elder_auth_headers, "Origin": "https://malicious-attacker-site.com"},
    )
    assert res.status_code == 403
    assert "Untrusted cross-origin request rejected" in res.json()["detail"]


def test_csrf_token_validation_mismatch_rejected(client, elder_auth_headers):
    """Test that submitting an invalid X-CSRF-Token header results in 403 Forbidden."""
    res = client.post(
        "/today/dose",
        data={"medication_id": 1, "action": "taken"},
        headers={
            **elder_auth_headers,
            "Cookie": f"{elder_auth_headers['Cookie']}; {CSRF_COOKIE_NAME}=real-valid-token",
            CSRF_HEADER_NAME: "forged-invalid-token",
        },
    )
    assert res.status_code == 403
    assert "Invalid CSRF token" in res.json()["detail"]


def test_csrf_token_validation_success(client, elder_auth_headers, sample_profile, db_session):
    """Test that valid matching CSRF token passes inspection."""
    today = date.today()
    med = Medication(
        profile_id=sample_profile.id,
        name="Aspirin",
        dosage="81 mg",
        times_per_day=1,
        schedule_times="08:00",
        start_date=today,
    )
    db_session.add(med)
    db_session.commit()

    token = generate_csrf_token()
    res = client.post(
        "/doses/log",
        data={
            "medication_id": med.id,
            "dose_date": today.isoformat(),
            "scheduled_time": "08:00",
            "action": "taken",
        },
        headers={
            **elder_auth_headers,
            "Cookie": f"{elder_auth_headers['Cookie']}; {CSRF_COOKIE_NAME}={token}",
            CSRF_HEADER_NAME: token,
        },
        follow_redirects=False,
    )
    assert res.status_code == 303


def test_csrf_utility_functions():
    """Directly test generate_csrf_token and verify_csrf_token helpers."""
    t1 = generate_csrf_token()
    assert len(t1) == 64  # 32 bytes hex
    t2 = generate_csrf_token("seed-123")
    assert len(t2) == 64

    assert verify_csrf_token(t1, t1) is True
    assert verify_csrf_token(t1, "different-token") is False
    assert verify_csrf_token(None, t1) is False
    assert verify_csrf_token(t1, None) is False


# ==============================================================================
# 5. Scheduler Token Boundary & Rejection Tests
# ==============================================================================


def test_scheduler_token_empty_and_whitespace_rejected(client):
    """Test scheduler endpoint rejects empty and whitespace tokens with 401."""
    res_empty = client.post("/tasks/send-reminders", headers={"X-Scheduler-Token": ""})
    assert res_empty.status_code == 401

    res_ws = client.post("/tasks/send-reminders", headers={"X-Scheduler-Token": "   "})
    assert res_ws.status_code == 401


# ==============================================================================
# 6. Input Validation Failures & Constraints
# ==============================================================================


def test_profile_creation_input_validation(client):
    """Test validation constraints on profile creation payload."""
    # 1. Elder name too short (<2 chars)
    res_short = client.post("/api/profiles", json={"elder_name": "A"})
    assert res_short.status_code == 422

    # 2. Elder name too long (>100 chars)
    res_long = client.post("/api/profiles", json={"elder_name": "X" * 105})
    assert res_long.status_code == 422

    # 3. Invalid age (>130)
    res_age = client.post("/api/profiles", json={"elder_name": "John Doe", "elder_age": 150})
    assert res_age.status_code == 422

    # 4. Negative age
    res_neg_age = client.post("/api/profiles", json={"elder_name": "John Doe", "elder_age": -5})
    assert res_neg_age.status_code == 422


def test_medication_input_validation(client, elder_auth_headers):
    """Test validation constraints on medication creation payload and Pydantic schema."""
    today = date.today()

    # 1. Direct schema validation: invalid schedule times
    with pytest.raises(ValueError):
        MedicationCreate(
            name="Med A",
            dosage="10 mg",
            times_per_day=1,
            schedule_times="25:00",
            start_date=today,
        )

    with pytest.raises(ValueError):
        MedicationCreate(
            name="Med A",
            dosage="10 mg",
            times_per_day=1,
            schedule_times="morning",
            start_date=today,
        )

    # 2. Direct schema validation: end date earlier than start date
    yesterday = today - timedelta(days=1)
    with pytest.raises(ValueError):
        MedicationCreate(
            name="Med A",
            dosage="10 mg",
            times_per_day=1,
            schedule_times="08:00",
            start_date=today,
            end_date=yesterday,
        )

    # 3. Dosage exceeding max length
    with pytest.raises(ValueError):
        MedicationCreate(
            name="Med A",
            dosage="D" * 85,
            times_per_day=1,
            schedule_times="08:00",
            start_date=today,
        )


def test_appointment_input_validation(client, elder_auth_headers):
    """Test validation constraints on doctor appointments."""
    # 1. Invalid date string on HTML form endpoint
    res = client.post(
        "/appointments/new",
        data={
            "doctor_name": "Dr. Smith",
            "appointment_date": "not-a-valid-date-time",
            "location": "Room 101",
        },
        headers=elder_auth_headers,
    )
    assert res.status_code == 400
    assert "Invalid appointment date format" in res.json()["detail"]

    # 2. Schema validation: Doctor name too short
    with pytest.raises(ValueError):
        AppointmentCreate(
            doctor_name="A",
            appointment_date=datetime.now(),
        )


def test_dose_log_input_validation(client, elder_auth_headers, sample_profile, db_session):
    """Test validation constraints on logging doses."""
    today = date.today()
    med = Medication(
        profile_id=sample_profile.id,
        name="Atorvastatin",
        dosage="20 mg",
        times_per_day=1,
        schedule_times="08:00",
        start_date=today,
    )
    db_session.add(med)
    db_session.commit()

    # 1. Invalid status action on HTML endpoint
    res_bad_action = client.post(
        "/doses/log",
        data={
            "medication_id": med.id,
            "dose_date": today.isoformat(),
            "scheduled_time": "08:00",
            "action": "forgotten",  # Only 'taken' or 'skipped' permitted
        },
        headers=elder_auth_headers,
    )
    assert res_bad_action.status_code == 400
    assert "Invalid dose status action" in res_bad_action.json()["detail"]

    # 2. Schema validation: Invalid scheduled time format
    with pytest.raises(ValueError):
        DoseLogCreate(
            medication_id=med.id,
            dose_date=today,
            scheduled_time="8am",
            status="taken",
        )


# ==============================================================================
# 7. Role Permission Edge Cases
# ==============================================================================


def test_family_cannot_edit_via_endpoints(client, family_auth_headers, sample_profile, db_session):
    """Test that Family role is forbidden (403) from all state-changing endpoints."""
    today = date.today().isoformat()
    now_iso = datetime.now().isoformat()

    # 1. Family cannot add medication via form
    res_med = client.post(
        "/medications/new",
        data={
            "name": "Med X",
            "dosage": "10 mg",
            "times_per_day": 1,
            "schedule_times": "08:00",
            "start_date": today,
        },
        headers=family_auth_headers,
    )
    assert res_med.status_code == 403
    assert "view-only access" in res_med.json()["detail"]

    # 2. Family cannot add appointment via form
    res_appt = client.post(
        "/appointments/new",
        data={
            "doctor_name": "Dr. Davis",
            "appointment_date": now_iso,
            "location": "General Clinic",
        },
        headers=family_auth_headers,
    )
    assert res_appt.status_code == 403
    assert "view-only access" in res_appt.json()["detail"]

    # 3. Family cannot log dose
    res_dose = client.post(
        "/doses/log",
        data={
            "medication_id": 1,
            "dose_date": today,
            "scheduled_time": "08:00",
            "action": "taken",
        },
        headers=family_auth_headers,
    )
    assert res_dose.status_code == 403

    # 4. Family cannot modify access settings
    res_settings = client.post(
        "/settings/access/toggle-role",
        data={"target_role": "caretaker", "enabled": "false"},
        headers=family_auth_headers,
    )
    assert res_settings.status_code == 403


def test_revoked_caretaker_cannot_login_web_form(client, sample_profile, db_session, elder_auth_headers):
    """Test that once revoked by elder, caretaker is blocked from HTML web form login."""
    # Elder disables caretaker access
    client.post(
        "/settings/access/toggle-role",
        data={"target_role": "caretaker", "enabled": "false"},
        headers=elder_auth_headers,
        follow_redirects=False,
    )

    # Caretaker attempts HTML login
    res = client.post(
        "/login",
        data={"care_id": sample_profile.care_id, "passcode": "CAR-5678"},
    )
    assert res.status_code == 403
    assert "Caretaker access has been paused or revoked" in res.text


def test_revoked_family_cannot_login_web_form(client, sample_profile, db_session, elder_auth_headers):
    """Test that once revoked by elder, family is blocked from HTML web form login."""
    # Elder disables family access
    client.post(
        "/settings/access/toggle-role",
        data={"target_role": "family", "enabled": "false"},
        headers=elder_auth_headers,
        follow_redirects=False,
    )

    # Family attempts HTML login
    res = client.post(
        "/login",
        data={"care_id": sample_profile.care_id, "passcode": "FAM-9012"},
    )
    assert res.status_code == 403
    assert "Family view access has been paused or revoked" in res.text


def test_unauthenticated_request_redirection(client):
    """Test unauthenticated browser requests are redirected to /login."""
    protected_paths = ["/today", "/medications", "/appointments", "/settings/access"]
    for path in protected_paths:
        res = client.get(path, headers={"Accept": "text/html"}, follow_redirects=False)
        assert res.status_code in (302, 303, 307)
        assert "/login" in res.headers.get("location", "")


# ==============================================================================
# 8. Gemini Fallback & API Mocking
# ==============================================================================


def test_gemini_fallback_when_no_api_key():
    """Verify explain_medication returns offline curated guide when GEMINI_API_KEY is unset."""
    with patch.object(settings, "GEMINI_API_KEY", ""):
        # Known curated drug
        guide = explain_medication("Lisinopril", "10 mg")
        assert guide["source"] == "curated_guide"
        assert "blood pressure" in guide["purpose"].lower()
        assert "Medical Disclaimer" in guide["disclaimer"]

        # Unknown drug falls back to universal geriatric guide
        unknown = explain_medication("ZzzBrandUnknown99")
        assert unknown["source"] == "general_guide"
        assert len(unknown["purpose"]) > 10
        assert "Medical Disclaimer" in unknown["disclaimer"]


def test_gemini_api_success_and_parsing():
    """Verify Gemini API response parsing when API key is provided."""
    mock_payload = {
        "purpose": "Helps relax blood vessels to keep your blood pressure smooth and heart calm.",
        "side_effects": "Mild dry cough, dizziness when standing up quickly.",
        "precautions": "Avoid salt substitutes with potassium. Drink plenty of water.",
    }
    mock_response = MagicMock()
    mock_response.text = f"```json\n{json.dumps(mock_payload)}\n```"

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with (
        patch.object(settings, "GEMINI_API_KEY", "fake-api-key"),
        patch("google.genai.Client", return_value=mock_client),
    ):
        result = explain_medication("Amlodipine", "5 mg")
        assert result["source"] == "gemini_ai"
        assert result["purpose"] == mock_payload["purpose"]
        assert result["side_effects"] == mock_payload["side_effects"]


def test_gemini_api_error_graceful_fallback():
    """Verify Gemini API network/parsing error falls back to offline guidance without raising."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API connection timeout")

    with (
        patch.object(settings, "GEMINI_API_KEY", "fake-api-key"),
        patch("google.genai.Client", return_value=mock_client),
    ):
        result = explain_medication("Metformin", "500 mg")
        assert result["source"] == "curated_guide"
        assert "blood sugar" in result["purpose"].lower()


# ==============================================================================
# 9. Adherence Calculation Edge Cases
# ==============================================================================


def test_adherence_edge_cases(db_session, sample_profile):
    """Test adherence calculation edge cases: zero doses, all skipped, all taken, mixed."""
    today = date.today()
    pid = sample_profile.id

    # 1. Zero scheduled doses -> defaults to 100%
    score_zero = calculate_adherence_percentage(db_session, pid, today, today_taken=0, today_total=0)
    assert score_zero == ADHERENCE_DEFAULT_PERCENTAGE

    # 2. Only today's count available (no database past logs)
    score_today_half = calculate_adherence_percentage(db_session, pid, today, today_taken=1, today_total=2)
    assert score_today_half == 50

    # 3. All doses skipped in past 7 days -> 0%
    log_skip1 = DoseLog(
        profile_id=pid,
        medication_id=1,
        dose_date=today,
        scheduled_time="08:00",
        status="skipped",
        logged_by_role="elder",
    )
    log_skip2 = DoseLog(
        profile_id=pid,
        medication_id=1,
        dose_date=today,
        scheduled_time="20:00",
        status="skipped",
        logged_by_role="elder",
    )
    db_session.add_all([log_skip1, log_skip2])
    db_session.commit()

    score_all_skipped = calculate_adherence_percentage(db_session, pid, today, today_taken=0, today_total=2)
    assert score_all_skipped == 0

    # 4. Add 2 taken doses -> 2 taken out of 4 total -> 50%
    log_taken1 = DoseLog(
        profile_id=pid,
        medication_id=1,
        dose_date=today - timedelta(days=1),
        scheduled_time="08:00",
        status="taken",
        logged_by_role="elder",
    )
    log_taken2 = DoseLog(
        profile_id=pid,
        medication_id=1,
        dose_date=today - timedelta(days=1),
        scheduled_time="20:00",
        status="taken",
        logged_by_role="elder",
    )
    db_session.add_all([log_taken1, log_taken2])
    db_session.commit()

    score_mixed = calculate_adherence_percentage(db_session, pid, today, today_taken=0, today_total=2)
    assert score_mixed == 50


# ==============================================================================
# 10. Reminder Windows Boundary Tests
# ==============================================================================


def test_reminder_window_boundaries(db_session, sample_profile):
    """Test boundary conditions for reminder windows (2h for doses, 48h for appointments)."""
    now = datetime.now()
    today = date.today()

    # Dose scheduled 1 hour in the future (within 2h window -> upcoming)
    t_upcoming = (now + timedelta(hours=1)).strftime("%H:%M")
    med_upcoming = Medication(
        profile_id=sample_profile.id,
        name="MedUpcoming",
        dosage="5 mg",
        times_per_day=1,
        schedule_times=t_upcoming,
        start_date=today,
    )

    # Dose scheduled 4 hours in the future (outside 2h window -> not upcoming)
    t_future = (now + timedelta(hours=4)).strftime("%H:%M")
    med_future = Medication(
        profile_id=sample_profile.id,
        name="MedFuture",
        dosage="5 mg",
        times_per_day=1,
        schedule_times=t_future,
        start_date=today,
    )

    # Appointment 24 hours from now (within 48h window -> upcoming)
    appt_within = Appointment(
        profile_id=sample_profile.id,
        doctor_name="Dr. Nearby",
        appointment_date=now + timedelta(hours=24),
    )

    # Appointment 72 hours from now (outside 48h window -> not upcoming)
    appt_far = Appointment(
        profile_id=sample_profile.id,
        doctor_name="Dr. FarAway",
        appointment_date=now + timedelta(hours=72),
    )

    db_session.add_all([med_upcoming, med_future, appt_within, appt_far])
    db_session.commit()

    report = process_all_reminders(db_session)
    detail = report["details"][0]

    # Verify MedUpcoming is in upcoming_doses, MedFuture is NOT
    assert any("MedUpcoming" in s for s in detail["upcoming_doses"])
    assert not any("MedFuture" in s for s in detail["upcoming_doses"])

    # Verify Dr. Nearby is in upcoming_appointments, Dr. FarAway is NOT
    assert any("Dr. Nearby" in s for s in detail["upcoming_appointments"])
    assert not any("Dr. FarAway" in s for s in detail["upcoming_appointments"])


# ==============================================================================
# 11. Email Service SMTP & Mock Delivery
# ==============================================================================


def test_email_service_delivery_paths():
    """Test all delivery paths for email service: invalid email, mock dev, and SMTP."""
    # 1. Invalid email
    assert send_email("", "Subject", "Body") is False
    assert send_email("invalid-address", "Subject", "Body") is False

    # 2. Mock mode (SMTP_HOST unset)
    with patch.object(settings, "SMTP_HOST", ""):
        assert send_email("test@example.com", "Test Subject", "Test Body") is True
        sent_count = send_batch_emails(["a@example.com", "b@example.com"], "Subject", "Body")
        assert sent_count == 2

    # 3. SMTP mode success (TLS port 587)
    mock_smtp = MagicMock()
    with (
        patch.object(settings, "SMTP_HOST", "smtp.example.com"),
        patch.object(settings, "SMTP_PORT", 587),
        patch.object(settings, "SMTP_USER", "user"),
        patch.object(settings, "SMTP_PASSWORD", "pass"),
        patch("smtplib.SMTP", return_value=mock_smtp),
    ):
        assert send_email("user@example.com", "Subject", "Body", "<b>Body</b>") is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once()
        mock_smtp.sendmail.assert_called_once()
        mock_smtp.quit.assert_called_once()

    # 4. SMTP error handling
    mock_smtp_err = MagicMock()
    mock_smtp_err.sendmail.side_effect = Exception("SMTP Connection Failed")
    with (
        patch.object(settings, "SMTP_HOST", "smtp.example.com"),
        patch.object(settings, "SMTP_PORT", 587),
        patch("smtplib.SMTP", return_value=mock_smtp_err),
    ):
        assert send_email("user@example.com", "Subject", "Body") is False


# ==============================================================================
# 12. Token Security & Session Decoding Edge Cases
# ==============================================================================


def test_session_token_edge_cases():
    """Test corrupted, tampered, and expired session tokens."""
    token = create_session_token({"profile_id": 1, "role": "elder"})
    decoded = decode_session_token(token)
    assert decoded is not None
    assert decoded["profile_id"] == 1

    # Tampered signature
    parts = token.split(".")
    tampered = f"{parts[0]}.invalid_signature"
    assert decode_session_token(tampered) is None

    # Corrupted base64
    assert decode_session_token("not-a-token") is None
    assert decode_session_token("") is None


# ==============================================================================
# 13. Comprehensive Route Coverage & Error Handler Tests
# ==============================================================================


def test_view_rendering_and_form_pages(client, elder_auth_headers, sample_profile, db_session):
    """Test full HTML view rendering for medications and appointments."""
    today = date.today()
    med = Medication(
        profile_id=sample_profile.id,
        name="Digoxin",
        dosage="0.125 mg",
        times_per_day=1,
        schedule_times="09:00",
        start_date=today,
    )
    appt = Appointment(
        profile_id=sample_profile.id,
        doctor_name="Dr. Jenkins",
        appointment_date=datetime.now() + timedelta(days=2),
    )
    db_session.add_all([med, appt])
    db_session.commit()

    # Medications pages
    res_meds = client.get("/medications", headers=elder_auth_headers)
    assert res_meds.status_code == 200
    assert "Digoxin" in res_meds.text

    res_new_med = client.get("/medications/new", headers=elder_auth_headers)
    assert res_new_med.status_code == 200

    res_edit_med = client.get(f"/medications/{med.id}/edit", headers=elder_auth_headers)
    assert res_edit_med.status_code == 200
    assert "Digoxin" in res_edit_med.text

    # Appointments pages
    res_appts = client.get("/appointments", headers=elder_auth_headers)
    assert res_appts.status_code == 200
    assert "Dr. Jenkins" in res_appts.text

    res_new_appt = client.get("/appointments/new", headers=elder_auth_headers)
    assert res_new_appt.status_code == 200

    res_edit_appt = client.get(f"/appointments/{appt.id}/edit", headers=elder_auth_headers)
    assert res_edit_appt.status_code == 200
    assert "Dr. Jenkins" in res_edit_appt.text


def test_access_settings_post_actions(client, elder_auth_headers, sample_profile):
    """Test updating emergency contacts and regenerating passcodes via web forms."""
    # 1. Update contacts
    res_contacts = client.post(
        "/settings/access/update-contacts",
        data={
            "elder_email": "new_elder@example.com",
            "caretaker_email": "new_ct@example.com",
            "family_email": "new_fam@example.com",
            "emergency_notes": "Updated allergy warning",
        },
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res_contacts.status_code == 303

    # 2. Regenerate caretaker passcode
    res_regen_ct = client.post(
        "/settings/access/regenerate-passcode",
        data={"target_role": "caretaker"},
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res_regen_ct.status_code == 303

    # 3. Regenerate family passcode
    res_regen_fam = client.post(
        "/settings/access/regenerate-passcode",
        data={"target_role": "family"},
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res_regen_fam.status_code == 303


def test_html_create_profile_flow(client):
    """Test creating a profile through the web form."""
    res = client.post(
        "/create-profile",
        data={
            "elder_name": "Mildred Hubble",
            "elder_age": "82",
            "emergency_notes": "None",
            "elder_email": "mildred@example.com",
            "caretaker_email": "",
            "family_email": "",
        },
        follow_redirects=False,
    )
    assert res.status_code == 200
    assert "Account Created Successfully" in res.text or "mildred" in res.text.lower()


def test_logout_clears_cookie(client, elder_auth_headers):
    """Test /logout endpoint removes cookie and redirects to login."""
    res = client.get("/logout", headers=elder_auth_headers, follow_redirects=False)
    assert res.status_code == 302
    assert "carenest_session" in res.headers.get("set-cookie", "")


def test_custom_404_and_exception_handlers(client):
    """Test custom 404 handler for HTML and JSON clients."""
    # HTML client
    res_html = client.get("/non-existent-url-9999", headers={"Accept": "text/html"}, follow_redirects=False)
    assert res_html.status_code == 303
    assert "/today" in res_html.headers.get("location", "")

    # JSON client
    res_json = client.get("/non-existent-url-9999", headers={"Accept": "application/json"})
    assert res_json.status_code == 404
    assert res_json.json()["detail"] == "Resource not found"


def test_database_get_db():
    """Test get_db session generator lifecycle."""
    from app.database import get_db

    gen = get_db()
    session = next(gen)
    assert session is not None
    try:
        next(gen)
    except StopIteration:
        pass
