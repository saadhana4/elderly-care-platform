"""Medication domain service handling CRUD operations and AI explanation lifecycle."""

import json
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import DEFAULT_SCHEDULE_TIMES
from app.models import Medication
from app.services.gemini_service import explain_medication


def clean_schedule_times(raw_times_str: str) -> str:
    """Validate and format comma-separated schedule times.

    Args:
        raw_times_str (str): Input string of times.

    Returns:
        str: Comma-separated string of validated times.
    """
    parts: list[str] = [t.strip() for t in raw_times_str.split(",") if t.strip()]
    return ", ".join(parts) if parts else DEFAULT_SCHEDULE_TIMES


def parse_date_safe(date_str: str | None, default: date | None = None) -> date | None:
    """Parse an ISO date string safely without raising exceptions.

    Args:
        date_str (Optional[str]): String in YYYY-MM-DD format.
        default (Optional[date]): Fallback date if parsing fails.

    Returns:
        Optional[date]: Parsed date or fallback.
    """
    if not date_str or not date_str.strip():
        return default
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return default


def get_profile_medications(db: Session, profile_id: int) -> list[Medication]:
    """Retrieve all medications for a profile ordered by name.

    Args:
        db (Session): Database session.
        profile_id (int): Healthcare profile ID.

    Returns:
        list[Medication]: List of active medications.
    """
    return (
        db.query(Medication).filter(Medication.profile_id == profile_id).order_by(Medication.name.asc()).all()
    )


def get_medication_or_404(db: Session, profile_id: int, med_id: int) -> Medication:
    """Fetch a medication belonging to a profile or raise 404.

    Args:
        db (Session): Database session.
        profile_id (int): Healthcare profile ID.
        med_id (int): Medication database ID.

    Returns:
        Medication: The matching medication record.

    Raises:
        HTTPException: 404 if not found or unauthorized.
    """
    med: Medication | None = (
        db.query(Medication)
        .filter(
            Medication.id == med_id,
            Medication.profile_id == profile_id,
        )
        .first()
    )
    if not med:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found",
        )
    return med


def create_medication_record(
    db: Session,
    profile_id: int,
    name: str,
    dosage: str,
    times_per_day: int,
    schedule_times: str,
    start_date: str,
    end_date: str | None = None,
    notes: str | None = None,
) -> Medication:
    """Create a new medication record and cache its AI explanation.

    Args:
        db (Session): Database session.
        profile_id (int): Healthcare profile ID.
        name (str): Drug name.
        dosage (str): Dosage strength.
        times_per_day (int): Daily frequency.
        schedule_times (str): Comma-separated HH:MM times.
        start_date (str): Prescription start date.
        end_date (Optional[str]): Optional end date.
        notes (Optional[str]): Doctor instructions.

    Returns:
        Medication: The newly persisted medication instance.
    """
    clean_name: str = name.strip()
    clean_dosage: str = dosage.strip()
    clean_schedule: str = clean_schedule_times(schedule_times)
    clean_notes: str | None = notes.strip() if notes and notes.strip() else None

    parsed_start: date = parse_date_safe(start_date, default=date.today()) or date.today()
    parsed_end: date | None = parse_date_safe(end_date, default=None)

    explanation_data: dict[str, Any] = explain_medication(clean_name, clean_dosage, clean_notes or "")
    explanation_json: str = json.dumps(explanation_data)

    new_med = Medication(
        profile_id=profile_id,
        name=clean_name,
        dosage=clean_dosage,
        times_per_day=max(1, times_per_day),
        schedule_times=clean_schedule,
        start_date=parsed_start,
        end_date=parsed_end,
        notes=clean_notes,
        plain_explanation=explanation_json,
    )
    db.add(new_med)
    db.commit()
    db.refresh(new_med)
    return new_med


def update_medication_record(
    db: Session,
    med: Medication,
    name: str,
    dosage: str,
    times_per_day: int,
    schedule_times: str,
    start_date: str,
    end_date: str | None = None,
    notes: str | None = None,
) -> Medication:
    """Update an existing medication record and refresh its explanation.

    Args:
        db (Session): Database session.
        med (Medication): Target medication instance to update.
        name (str): Updated drug name.
        dosage (str): Updated dosage strength.
        times_per_day (int): Updated frequency.
        schedule_times (str): Updated HH:MM times.
        start_date (str): Updated start date.
        end_date (Optional[str]): Updated end date.
        notes (Optional[str]): Updated instructions.

    Returns:
        Medication: The updated medication instance.
    """
    med.name = name.strip()
    med.dosage = dosage.strip()
    med.times_per_day = max(1, times_per_day)
    med.schedule_times = clean_schedule_times(schedule_times)

    parsed_start: date | None = parse_date_safe(start_date)
    if parsed_start:
        med.start_date = parsed_start

    med.end_date = parse_date_safe(end_date)
    med.notes = notes.strip() if notes and notes.strip() else None

    explanation_data: dict[str, Any] = explain_medication(med.name, med.dosage, med.notes or "")
    med.plain_explanation = json.dumps(explanation_data)

    db.commit()
    db.refresh(med)
    return med


def delete_medication_record(db: Session, med: Medication) -> str:
    """Delete a medication record from the database.

    Args:
        db (Session): Database session.
        med (Medication): Medication instance to delete.

    Returns:
        str: Name of the deleted medication.
    """
    med_name: str = med.name
    db.delete(med)
    db.commit()
    return med_name


def get_or_refresh_explanation(db: Session, med: Medication, refresh: bool = False) -> dict[str, Any]:
    """Retrieve cached AI explanation or regenerate and save if missing/requested.

    Args:
        db (Session): Database session.
        med (Medication): Target medication record.
        refresh (bool): Whether to force regeneration.

    Returns:
        dict[str, Any]: Structured explanation payload.
    """
    explanation: dict[str, Any] | None = None
    if med.plain_explanation and not refresh:
        try:
            explanation = json.loads(med.plain_explanation)
        except (json.JSONDecodeError, TypeError):
            explanation = None

    if not explanation or refresh:
        explanation = explain_medication(med.name, med.dosage, med.notes or "")
        med.plain_explanation = json.dumps(explanation)
        db.commit()

    return explanation
