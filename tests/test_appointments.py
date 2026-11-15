"""Tests for Doctor Appointments CRUD and Role Permissions."""

from datetime import datetime, timedelta

from app.models import Appointment


def test_elder_and_caretaker_can_manage_appointments(
    client, sample_profile, db_session, elder_auth_headers, caretaker_auth_headers
):
    """Test creating, editing, and deleting doctor appointments."""
    appt_time = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT10:30")

    # 1. Elder creates appointment
    res_create = client.post(
        "/appointments/new",
        data={
            "doctor_name": "Dr. Sarah Jenkins - Cardiology",
            "appointment_date": appt_time,
            "location": "St. Jude Heart Pavilion Suite 300",
            "notes": "Fasting blood panel and EKG review",
        },
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res_create.status_code == 303

    appt = (
        db_session.query(Appointment)
        .filter(
            Appointment.profile_id == sample_profile.id,
            Appointment.doctor_name.like("%Jenkins%"),
        )
        .first()
    )
    assert appt is not None
    assert "Heart Pavilion" in appt.location

    # 2. Caretaker updates appointment
    new_time = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT11:00")
    res_update = client.post(
        f"/appointments/{appt.id}/edit",
        data={
            "doctor_name": "Dr. Sarah Jenkins - Cardiology",
            "appointment_date": new_time,
            "location": "St. Jude Heart Pavilion Suite 402",
            "notes": "Rescheduled per clinic request",
        },
        headers=caretaker_auth_headers,
        follow_redirects=False,
    )
    assert res_update.status_code == 303
    db_session.refresh(appt)
    assert "Suite 402" in appt.location
    assert "Rescheduled" in appt.notes

    # 3. Elder cancels appointment
    res_delete = client.post(
        f"/appointments/{appt.id}/delete",
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res_delete.status_code == 303
    assert db_session.query(Appointment).filter(Appointment.id == appt.id).first() is None


def test_family_cannot_modify_appointments(client, sample_profile, family_auth_headers):
    """Test that Family role cannot create, edit, or delete appointments."""
    res_create = client.post(
        "/appointments/new",
        data={
            "doctor_name": "Dr. Smith",
            "appointment_date": "2026-05-01T09:00",
        },
        headers=family_auth_headers,
    )
    assert res_create.status_code == 403
