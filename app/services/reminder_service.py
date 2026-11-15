"""Reminder processing service.

Finds missed doses, upcoming doses, and upcoming appointments for active profiles,
and dispatches email reminders to authorized elders, caretakers, and family members.
"""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import (
    REMINDER_APPOINTMENT_FORWARD_HOURS,
    REMINDER_DOSE_FORWARD_HOURS,
)
from app.models import Appointment, DoseLog, Profile
from app.services.email_service import send_batch_emails


def _get_profile_recipients(profile: Profile) -> list[str]:
    """Collect authorized email recipients for a given profile.

    Args:
        profile (Profile): The healthcare profile to extract recipients from.

    Returns:
        List[str]: List of valid email addresses.
    """
    recipients: list[str] = []
    if profile.elder_email:
        recipients.append(profile.elder_email)
    if profile.caretaker_access_enabled and profile.caretaker_email:
        recipients.append(profile.caretaker_email)
    if profile.family_access_enabled and profile.family_email:
        recipients.append(profile.family_email)
    return recipients


def _scan_profile_doses(
    profile: Profile,
    db: Session,
    today: date,
    current_time_str: str,
    upcoming_limit_str: str,
) -> tuple[list[str], list[str]]:
    """Scan today's scheduled doses for a profile to identify missed or upcoming slots.

    Args:
        profile (Profile): The healthcare profile.
        db (Session): Database session.
        today (date): Current calendar date.
        current_time_str (str): Current time in 'HH:MM'.
        upcoming_limit_str (str): Upper boundary time in 'HH:MM'.

    Returns:
        Tuple[List[str], List[str]]: (missed_doses, upcoming_doses).
    """
    missed: list[str] = []
    upcoming: list[str] = []

    active_meds = [
        m
        for m in profile.medications
        if m.start_date <= today and (m.end_date is None or m.end_date >= today)
    ]

    logs_today = (
        db.query(DoseLog)
        .filter(
            DoseLog.profile_id == profile.id,
            DoseLog.dose_date == today,
        )
        .all()
    )
    logged_keys = {
        (log_entry.medication_id, log_entry.scheduled_time): log_entry.status for log_entry in logs_today
    }

    for med in active_meds:
        times = [t.strip() for t in med.schedule_times.split(",") if t.strip()]
        for scheduled_time in times:
            status = logged_keys.get((med.id, scheduled_time))
            if status is None:
                if scheduled_time < current_time_str:
                    missed.append(f"{med.name} ({med.dosage}) scheduled for {scheduled_time}")
                elif current_time_str <= scheduled_time <= upcoming_limit_str:
                    upcoming.append(f"{med.name} ({med.dosage}) scheduled at {scheduled_time}")

    return missed, upcoming


def _scan_profile_appointments(
    profile: Profile,
    db: Session,
    now: datetime,
    window_end: datetime,
) -> list[str]:
    """Scan upcoming medical appointments within the alert window.

    Args:
        profile (Profile): The healthcare profile.
        db (Session): Database session.
        now (datetime): Current timestamp.
        window_end (datetime): Upper boundary timestamp.

    Returns:
        List[str]: Formatted descriptions of upcoming appointments.
    """
    appts = (
        db.query(Appointment)
        .filter(
            Appointment.profile_id == profile.id,
            Appointment.appointment_date >= now,
            Appointment.appointment_date <= window_end,
        )
        .order_by(Appointment.appointment_date.asc())
        .all()
    )

    formatted: list[str] = []
    for a in appts:
        appt_time = a.appointment_date.strftime("%A, %b %d at %I:%M %p")
        location_info = f" at {a.location}" if a.location else ""
        formatted.append(f"{a.doctor_name}{location_info} on {appt_time}")
    return formatted


def _compose_reminder_body(
    elder_name: str,
    care_id: str,
    missed_doses: list[str],
    upcoming_doses: list[str],
    upcoming_appointments: list[str],
) -> str:
    """Build formatted plain-text alert notification body.

    Args:
        elder_name (str): Elder's full name.
        care_id (str): Profile care identifier.
        missed_doses (list[str]): Overdue dose descriptions.
        upcoming_doses (list[str]): Imminent dose descriptions.
        upcoming_appointments (list[str]): Imminent appointment descriptions.

    Returns:
        str: Formatted multi-line email text.
    """
    lines: list[str] = [
        "Hello,",
        "",
        f"Here is the latest healthcare update for {elder_name} (Care ID: {care_id}):",
        "",
    ]
    if missed_doses:
        lines.append("⚠️ MISSED / OVERDUE DOSES TODAY:")
        for md in missed_doses:
            lines.append(f"  • {md} - Not yet logged as taken.")
        lines.append("")

    if upcoming_doses:
        lines.append(f"🕒 UPCOMING DOSES (NEXT {REMINDER_DOSE_FORWARD_HOURS} HOURS):")
        for ud in upcoming_doses:
            lines.append(f"  • {ud}")
        lines.append("")

    if upcoming_appointments:
        lines.append(f"📅 UPCOMING MEDICAL APPOINTMENTS (NEXT {REMINDER_APPOINTMENT_FORWARD_HOURS} HOURS):")
        for ua in upcoming_appointments:
            lines.append(f"  • {ua}")
        lines.append("")

    lines.append("Please check the CareNest dashboard to review and log daily care routines.")
    lines.append("CareNest - Putting elderly wellbeing at the centre of care.")
    return "\n".join(lines)


def _process_profile_reminders(
    profile: Profile,
    db: Session,
    now: datetime,
    today: date,
    current_time_str: str,
    upcoming_limit: str,
    appointment_window: datetime,
) -> tuple[int, int, dict[str, Any] | None]:
    """Scan and dispatch alerts for a single care profile.

    Returns:
        tuple[int, int, Optional[dict[str, Any]]]: (alerts_count, emails_sent, audit_record).
    """
    recipients = _get_profile_recipients(profile)
    if not recipients:
        return 0, 0, None

    missed, upcoming = _scan_profile_doses(profile, db, today, current_time_str, upcoming_limit)
    appts = _scan_profile_appointments(profile, db, now, appointment_window)
    count = len(missed) + len(upcoming) + len(appts)
    if count == 0:
        return 0, 0, None

    subject = f"CareNest Healthcare Alert for {profile.elder_name} ({profile.care_id})"
    body = _compose_reminder_body(profile.elder_name, profile.care_id, missed, upcoming, appts)
    sent = send_batch_emails(recipients, subject, body)

    audit = {
        "care_id": profile.care_id,
        "elder_name": profile.elder_name,
        "recipients": recipients,
        "missed_doses": missed,
        "upcoming_doses": upcoming,
        "upcoming_appointments": appts,
        "emails_delivered": sent,
    }
    return count, sent, audit


def process_all_reminders(db: Session) -> dict[str, Any]:
    """Scan all active profiles and dispatch email reminders for doses and appointments.

    Args:
        db (Session): Database session.

    Returns:
        dict[str, Any]: Summary audit report with counts and per-profile alert details.
    """
    now = datetime.now()
    today = date.today()
    current_time_str = now.strftime("%H:%M")
    upcoming_limit = (now + timedelta(hours=REMINDER_DOSE_FORWARD_HOURS)).strftime("%H:%M")
    appointment_window = now + timedelta(hours=REMINDER_APPOINTMENT_FORWARD_HOURS)

    profiles = db.query(Profile).all()
    results: list[dict[str, Any]] = []
    total_emails_sent = 0
    total_alerts_found = 0

    for profile in profiles:
        count, sent, audit = _process_profile_reminders(
            profile, db, now, today, current_time_str, upcoming_limit, appointment_window
        )
        if audit:
            total_alerts_found += count
            total_emails_sent += sent
            results.append(audit)

    return {
        "timestamp": now.isoformat(),
        "profiles_checked": len(profiles),
        "total_alerts_found": total_alerts_found,
        "total_emails_sent": total_emails_sent,
        "details": results,
    }
