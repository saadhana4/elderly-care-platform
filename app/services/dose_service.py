"""Dose tracking, schedule slot compilation, and adherence calculation service."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import (
    ADHERENCE_DEFAULT_PERCENTAGE,
    ADHERENCE_LOOKBACK_DAYS,
    RECENT_HISTORY_LIMIT,
)
from app.models import DoseLog, Medication


def get_active_medications_for_date(db: Session, profile_id: int, target_date: date) -> list[Medication]:
    """Retrieve medications active on a specific calendar date.

    Args:
        db (Session): Database session.
        profile_id (int): Healthcare profile ID.
        target_date (date): Target evaluation date.

    Returns:
        List[Medication]: Active medications whose start and end dates span target_date.
    """
    candidates = (
        db.query(Medication)
        .filter(
            Medication.profile_id == profile_id,
            Medication.start_date <= target_date,
        )
        .all()
    )
    return [m for m in candidates if m.end_date is None or m.end_date >= target_date]


def _resolve_slot_status(slot_time: str, current_time: str, log: DoseLog | None) -> tuple[str, int, int]:
    """Determine dose slot status and count increment."""
    if log:
        if log.status == "taken":
            return log.status, 1, 0
        if log.status == "skipped":
            return log.status, 0, 1
        return log.status, 0, 0
    if slot_time < current_time:
        return "overdue", 0, 0
    return "pending", 0, 0


def compile_today_dose_slots(
    active_meds: list[Medication],
    today_logs: list[DoseLog],
    current_time_str: str,
) -> tuple[list[dict[str, Any]], int, int, int]:
    """Compile scheduled dose slots for today and compute today's counts.

    Args:
        active_meds (list[Medication]): Active medications for today.
        today_logs (list[DoseLog]): Existing dose logs recorded for today.
        current_time_str (str): Current time in 'HH:MM' format.

    Returns:
        tuple[list[dict[str, Any]], int, int, int]:
            - today_doses: Sorted list of dose slot dictionaries.
            - total_count: Total scheduled doses today.
            - taken_count: Doses marked as taken today.
            - skipped_count: Doses marked as skipped today.
    """
    logs_map: dict[tuple[int, str], DoseLog] = {
        (entry.medication_id, entry.scheduled_time): entry for entry in today_logs
    }

    today_doses: list[dict[str, Any]] = []
    total_count = taken_count = skipped_count = 0

    for med in active_meds:
        times = [t.strip() for t in med.schedule_times.split(",") if t.strip()]
        for t in times:
            total_count += 1
            log = logs_map.get((med.id, t))
            dose_status, t_inc, s_inc = _resolve_slot_status(t, current_time_str, log)
            taken_count += t_inc
            skipped_count += s_inc

            today_doses.append(
                {
                    "medication_id": med.id,
                    "name": med.name,
                    "dosage": med.dosage,
                    "notes": med.notes,
                    "scheduled_time": t,
                    "status": dose_status,
                    "log": log,
                }
            )

    today_doses.sort(key=lambda d: d["scheduled_time"])
    return today_doses, total_count, taken_count, skipped_count


def calculate_adherence_percentage(
    db: Session,
    profile_id: int,
    today: date,
    today_taken: int,
    today_total: int,
) -> int:
    """Calculate the adherence percentage over a 7-day lookback window or today.

    Args:
        db (Session): Database session.
        profile_id (int): Healthcare profile ID.
        today (date): Current calendar date.
        today_taken (int): Taken doses logged today.
        today_total (int): Total doses scheduled today.

    Returns:
        int: Adherence score rounded to nearest whole percentage (0-100).
    """
    lookback_start = today - timedelta(days=ADHERENCE_LOOKBACK_DAYS)
    past_logs = (
        db.query(DoseLog)
        .filter(
            DoseLog.profile_id == profile_id,
            DoseLog.dose_date >= lookback_start,
            DoseLog.dose_date <= today,
        )
        .all()
    )

    past_total = len(past_logs)
    if past_total > 0:
        past_taken = sum(1 for log_entry in past_logs if log_entry.status == "taken")
        return round((past_taken / past_total) * 100)
    elif today_total > 0:
        return round((today_taken / today_total) * 100)
    return ADHERENCE_DEFAULT_PERCENTAGE


def _find_existing_dose_log(
    db: Session,
    profile_id: int,
    medication_id: int,
    dose_date: date,
    clean_time: str,
) -> DoseLog | None:
    """Query existing dose log entry by composite keys."""
    return (
        db.query(DoseLog)
        .filter(
            DoseLog.profile_id == profile_id,
            DoseLog.medication_id == medication_id,
            DoseLog.dose_date == dose_date,
            DoseLog.scheduled_time == clean_time,
        )
        .first()
    )


def record_dose_status(
    db: Session,
    profile_id: int,
    medication_id: int,
    dose_date: date,
    scheduled_time: str,
    action: str,
    role: str,
) -> DoseLog:
    """Upsert a dose status log entry (Taken or Skipped).

    Args:
        db (Session): Database session.
        profile_id (int): Healthcare profile ID.
        medication_id (int): Medication ID.
        dose_date (date): Calendar date of the scheduled dose.
        scheduled_time (str): Time slot string ('HH:MM').
        action (str): 'taken' or 'skipped'.
        role (str): Role of the actor ('elder' or 'caretaker').

    Returns:
        DoseLog: The created or updated DoseLog database record.
    """
    clean_time: str = scheduled_time.strip()
    existing: DoseLog | None = _find_existing_dose_log(db, profile_id, medication_id, dose_date, clean_time)
    now_utc = datetime.now(UTC)

    if existing:
        existing.status = action
        existing.logged_at = now_utc
        existing.logged_by_role = role
        db.commit()
        return existing

    new_log = DoseLog(
        profile_id=profile_id,
        medication_id=medication_id,
        dose_date=dose_date,
        scheduled_time=clean_time,
        status=action,
        logged_at=now_utc,
        logged_by_role=role,
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return new_log


def get_recent_dose_history(db: Session, profile_id: int, limit: int = RECENT_HISTORY_LIMIT) -> list[DoseLog]:
    """Retrieve the most recent logged dose events for audit and display.

    Args:
        db (Session): Database session.
        profile_id (int): Healthcare profile ID.
        limit (int): Maximum records to retrieve.

    Returns:
        List[DoseLog]: Chronological list of recent DoseLog records.
    """
    return (
        db.query(DoseLog)
        .filter(
            DoseLog.profile_id == profile_id,
        )
        .order_by(DoseLog.dose_date.desc(), DoseLog.logged_at.desc())
        .limit(limit)
        .all()
    )
