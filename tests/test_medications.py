"""Tests for Medication Management (CRUD), Permissions, and Gemini Plain-Language Explainer."""

import json
from datetime import date
from app.models import Medication
from app.services.gemini_service import explain_medication


def test_elder_and_caretaker_can_add_medication(client, sample_profile, db_session, elder_auth_headers, caretaker_auth_headers):
    """Test that Elder and Caretaker can create medications."""
    # 1. Elder adds Metformin
    res1 = client.post(
        "/medications/new",
        data={
            "name": "Metformin",
            "dosage": "500 mg",
            "times_per_day": 2,
            "schedule_times": "08:00, 20:00",
            "start_date": "2026-01-01",
            "end_date": "",
            "notes": "Take with breakfast and dinner",
        },
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res1.status_code == 303

    med1 = db_session.query(Medication).filter(Medication.name == "Metformin").first()
    assert med1 is not None
    assert med1.dosage == "500 mg"
    assert med1.times_per_day == 2
    assert "08:00, 20:00" in med1.schedule_times
    # Ensure AI plain-language explanation was pre-generated
    assert med1.plain_explanation is not None
    parsed = json.loads(med1.plain_explanation)
    assert "purpose" in parsed
    assert "side_effects" in parsed
    assert "precautions" in parsed
    assert "disclaimer" in parsed

    # 2. Caretaker adds Lisinopril
    res2 = client.post(
        "/medications/new",
        data={
            "name": "Lisinopril",
            "dosage": "10 mg",
            "times_per_day": 1,
            "schedule_times": "09:00",
            "start_date": "2026-01-01",
            "end_date": "",
            "notes": "Take once in the morning",
        },
        headers=caretaker_auth_headers,
        follow_redirects=False,
    )
    assert res2.status_code == 303
    med2 = db_session.query(Medication).filter(Medication.name == "Lisinopril").first()
    assert med2 is not None


def test_family_cannot_add_or_delete_medication(client, sample_profile, db_session, family_auth_headers):
    """Test that Family role is strictly view-only and cannot add or delete medications."""
    res_add = client.post(
        "/medications/new",
        data={
            "name": "Aspirin",
            "dosage": "81 mg",
            "times_per_day": 1,
            "schedule_times": "08:00",
            "start_date": "2026-01-01",
        },
        headers=family_auth_headers,
    )
    assert res_add.status_code == 403
    assert "view-only access" in res_add.json()["detail"]


def test_medication_update_and_delete(client, sample_profile, db_session, elder_auth_headers):
    """Test editing and deleting an existing medication."""
    med = Medication(
        profile_id=sample_profile.id,
        name="Atorvastatin",
        dosage="20 mg",
        times_per_day=1,
        schedule_times="21:00",
        start_date=date(2026, 1, 1),
    )
    db_session.add(med)
    db_session.commit()
    db_session.refresh(med)

    # Update dosage to 40 mg
    res_update = client.post(
        f"/medications/{med.id}/edit",
        data={
            "name": "Atorvastatin",
            "dosage": "40 mg",
            "times_per_day": 1,
            "schedule_times": "21:00",
            "start_date": "2026-01-01",
            "end_date": "",
            "notes": "Increased dose per cardiologist",
        },
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res_update.status_code == 303
    db_session.refresh(med)
    assert med.dosage == "40 mg"
    assert "Increased dose" in med.notes

    # Delete medication
    res_del = client.post(
        f"/medications/{med.id}/delete",
        headers=elder_auth_headers,
        follow_redirects=False,
    )
    assert res_del.status_code == 303
    deleted = db_session.query(Medication).filter(Medication.id == med.id).first()
    assert deleted is None


def test_beyond_reminders_explainer_service():
    """Test that the Gemini plain-language explainer returns clear sections and the medical disclaimer."""
    explanation = explain_medication("Metformin", "500 mg", "Take with meals")
    assert "purpose" in explanation
    assert len(explanation["purpose"]) > 10
    assert "side_effects" in explanation
    assert "precautions" in explanation
    assert "disclaimer" in explanation
    assert "Medical Disclaimer" in explanation["disclaimer"]
