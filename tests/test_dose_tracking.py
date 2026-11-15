"""Tests for Daily Dose Tracking (Taken / Skipped) and Adherence Percentage."""

from datetime import date

from app.models import DoseLog, Medication


def test_elder_and_caretaker_can_log_dose(
    client, sample_profile, db_session, elder_auth_headers, caretaker_auth_headers
):
    """Test recording a dose as Taken and Skipped."""
    today = date.today()
    med = Medication(
        profile_id=sample_profile.id,
        name="Metformin",
        dosage="500 mg",
        times_per_day=2,
        schedule_times="08:00, 20:00",
        start_date=today,
    )
    db_session.add(med)
    db_session.commit()
    db_session.refresh(med)

    # 1. Elder marks 08:00 dose as Taken
    res1 = client.post(
        "/doses/log",
        data={
            "medication_id": med.id,
            "dose_date": today.isoformat(),
            "scheduled_time": "08:00",
            "action": "taken",
        },
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res1.status_code == 303

    log1 = (
        db_session.query(DoseLog)
        .filter(
            DoseLog.profile_id == sample_profile.id,
            DoseLog.medication_id == med.id,
            DoseLog.scheduled_time == "08:00",
        )
        .first()
    )
    assert log1 is not None
    assert log1.status == "taken"
    assert log1.logged_by_role == "elder"

    # 2. Caretaker marks 20:00 dose as Skipped
    res2 = client.post(
        "/doses/log",
        data={
            "medication_id": med.id,
            "dose_date": today.isoformat(),
            "scheduled_time": "20:00",
            "action": "skipped",
        },
        headers=caretaker_auth_headers,
        follow_redirects=False,
    )
    assert res2.status_code == 303

    log2 = (
        db_session.query(DoseLog)
        .filter(
            DoseLog.profile_id == sample_profile.id,
            DoseLog.medication_id == med.id,
            DoseLog.scheduled_time == "20:00",
        )
        .first()
    )
    assert log2 is not None
    assert log2.status == "skipped"
    assert log2.logged_by_role == "caretaker"


def test_family_cannot_log_doses(client, sample_profile, db_session, family_auth_headers):
    """Test that Family role cannot log or alter doses."""
    today = date.today()
    med = Medication(
        profile_id=sample_profile.id,
        name="Amlodipine",
        dosage="5 mg",
        times_per_day=1,
        schedule_times="08:00",
        start_date=today,
    )
    db_session.add(med)
    db_session.commit()

    res = client.post(
        "/doses/log",
        data={
            "medication_id": med.id,
            "dose_date": today.isoformat(),
            "scheduled_time": "08:00",
            "action": "taken",
        },
        headers=family_auth_headers,
    )
    assert res.status_code == 403
    assert "view-only access" in res.json()["detail"]


def test_today_view_and_adherence_calculation(client, sample_profile, db_session, elder_auth_headers):
    """Test that /today renders correctly and calculates adherence score."""
    today = date.today()
    med = Medication(
        profile_id=sample_profile.id,
        name="Lisinopril",
        dosage="10 mg",
        times_per_day=2,
        schedule_times="08:00, 20:00",
        start_date=today,
    )
    db_session.add(med)
    db_session.commit()

    # Log 1 dose taken
    log = DoseLog(
        profile_id=sample_profile.id,
        medication_id=med.id,
        dose_date=today,
        scheduled_time="08:00",
        status="taken",
        logged_by_role="elder",
    )
    db_session.add(log)
    db_session.commit()

    res = client.get("/today", headers=elder_auth_headers)
    assert res.status_code == 200
    assert "Today's Medication Routine" in res.text
    assert "Lisinopril" in res.text
    # 1 of 2 doses taken today -> adherence percentage should be displayed
    assert "%" in res.text
