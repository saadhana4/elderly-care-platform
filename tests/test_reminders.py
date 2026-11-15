"""Tests for Automated Email Reminders and Cloud Scheduler Trigger."""

from datetime import date, datetime, timedelta

from app.config import settings
from app.models import Appointment, Medication
from app.services.reminder_service import process_all_reminders


def test_scheduler_endpoint_security(client):
    """Test that /tasks/send-reminders requires valid scheduler secret token."""
    # 1. Missing token
    res_no_token = client.post("/tasks/send-reminders")
    assert res_no_token.status_code == 401
    assert "Missing or invalid scheduler token" in res_no_token.json()["detail"]

    # 2. Invalid token
    res_bad_token = client.post(
        "/tasks/send-reminders",
        headers={"X-Scheduler-Token": "completely-wrong-token"},
    )
    assert res_bad_token.status_code == 401

    # 3. Valid token via X-Scheduler-Token
    res_valid = client.post(
        "/tasks/send-reminders",
        headers={"X-Scheduler-Token": settings.SCHEDULER_SECRET_TOKEN},
    )
    assert res_valid.status_code == 200
    data = res_valid.json()
    assert data["status"] == "success"
    assert "report" in data

    # 4. Valid token via Bearer Authorization
    res_bearer = client.post(
        "/tasks/send-reminders",
        headers={"Authorization": f"Bearer {settings.SCHEDULER_SECRET_TOKEN}"},
    )
    assert res_bearer.status_code == 200


def test_reminder_logic_detects_missed_doses_and_appointments(db_session, sample_profile):
    """Test that reminder scanner correctly flags missed doses and upcoming doctor visits."""
    now = datetime.now()
    today = date.today()

    # Create a medication with a past dose time today (e.g. 06:00 AM) to simulate missed dose
    med = Medication(
        profile_id=sample_profile.id,
        name="Aspirin",
        dosage="81 mg",
        times_per_day=1,
        schedule_times="00:01",  # Past time today
        start_date=today,
    )
    db_session.add(med)

    # Create an upcoming appointment tomorrow
    appt = Appointment(
        profile_id=sample_profile.id,
        doctor_name="Dr. Jenkins - Heart Clinic",
        appointment_date=now + timedelta(hours=24),
        location="Room 301",
        notes="Fasting check",
    )
    db_session.add(appt)
    db_session.commit()

    # Run reminder processor
    report = process_all_reminders(db_session)
    assert report["profiles_checked"] >= 1
    assert report["total_alerts_found"] >= 2  # At least 1 missed dose + 1 upcoming appointment

    # Check details
    profile_result = next((r for r in report["details"] if r["care_id"] == sample_profile.care_id), None)
    assert profile_result is not None
    assert len(profile_result["missed_doses"]) >= 1
    assert "Aspirin" in profile_result["missed_doses"][0]
    assert len(profile_result["upcoming_appointments"]) >= 1
    assert "Dr. Jenkins" in profile_result["upcoming_appointments"][0]
    # Recipients should include elder, caretaker, and family
    assert "eleanor@example.com" in profile_result["recipients"]
    assert "caretaker@example.com" in profile_result["recipients"]
    assert "family@example.com" in profile_result["recipients"]
