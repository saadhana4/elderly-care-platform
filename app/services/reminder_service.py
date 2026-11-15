"""Reminder processing service.

Finds missed doses, upcoming doses, and upcoming appointments for all active profiles,
and dispatches email reminders to authorized elders, caretakers, and family members.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models import Profile, Medication, DoseLog, Appointment
from app.services.email_service import send_batch_emails


def process_all_reminders(db: Session) -> Dict[str, Any]:
    """Scan all profiles and dispatch necessary reminders for doses and appointments.
    
    Returns a summary report suitable for API response and audit logging.
    """
    now = datetime.now()
    today = date.today()
    current_time_str = now.strftime("%H:%M")
    
    # 2-hour forward window for upcoming doses
    upcoming_limit = (now + timedelta(hours=2)).strftime("%H:%M")
    # 48-hour forward window for appointments
    appointment_window = now + timedelta(hours=48)

    profiles = db.query(Profile).all()
    results = []
    total_emails_sent = 0
    total_alerts_found = 0

    for profile in profiles:
        recipients = []
        if profile.elder_email:
            recipients.append(profile.elder_email)
        if profile.caretaker_access_enabled and profile.caretaker_email:
            recipients.append(profile.caretaker_email)
        if profile.family_access_enabled and profile.family_email:
            recipients.append(profile.family_email)

        if not recipients:
            continue

        missed_doses = []
        upcoming_doses = []
        upcoming_appointments = []

        # 1. Check Medications & Doses for Today
        active_meds = [
            m for m in profile.medications
            if m.start_date <= today and (m.end_date is None or m.end_date >= today)
        ]

        # Get existing logs for today
        logs_today = db.query(DoseLog).filter(
            DoseLog.profile_id == profile.id,
            DoseLog.dose_date == today,
        ).all()
        logged_keys = {(l.medication_id, l.scheduled_time): l.status for l in logs_today}

        for med in active_meds:
            times = [t.strip() for t in med.schedule_times.split(",") if t.strip()]
            for scheduled_time in times:
                status = logged_keys.get((med.id, scheduled_time))
                if status is None:
                    # Dose has not been recorded yet today
                    if scheduled_time < current_time_str:
                        # Time has passed -> Missed dose
                        missed_doses.append(f"{med.name} ({med.dosage}) scheduled for {scheduled_time}")
                    elif current_time_str <= scheduled_time <= upcoming_limit:
                        # Time is approaching within next 2 hours -> Upcoming dose
                        upcoming_doses.append(f"{med.name} ({med.dosage}) scheduled at {scheduled_time}")

        # 2. Check Upcoming Appointments within 48 Hours
        appts = db.query(Appointment).filter(
            Appointment.profile_id == profile.id,
            Appointment.appointment_date >= now,
            Appointment.appointment_date <= appointment_window,
        ).order_by(Appointment.appointment_date.asc()).all()

        for a in appts:
            appt_time = a.appointment_date.strftime("%A, %b %d at %I:%M %p")
            location_info = f" at {a.location}" if a.location else ""
            upcoming_appointments.append(f"{a.doctor_name}{location_info} on {appt_time}")

        # If there are any alerts for this profile, compose and send notification
        alerts_count = len(missed_doses) + len(upcoming_doses) + len(upcoming_appointments)
        if alerts_count > 0:
            total_alerts_found += alerts_count
            subject = f"CareNest Healthcare Alert for {profile.elder_name} ({profile.care_id})"

            body_lines = [
                f"Hello,",
                f"",
                f"Here is the latest healthcare update for {profile.elder_name} (Care ID: {profile.care_id}):",
                f"",
            ]

            if missed_doses:
                body_lines.append("⚠️ MISSED / OVERDUE DOSES TODAY:")
                for md in missed_doses:
                    body_lines.append(f"  • {md} - Not yet logged as taken.")
                body_lines.append("")

            if upcoming_doses:
                body_lines.append("🕒 UPCOMING DOSES (NEXT 2 HOURS):")
                for ud in upcoming_doses:
                    body_lines.append(f"  • {ud}")
                body_lines.append("")

            if upcoming_appointments:
                body_lines.append("📅 UPCOMING MEDICAL APPOINTMENTS (NEXT 48 HOURS):")
                for ua in upcoming_appointments:
                    body_lines.append(f"  • {ua}")
                body_lines.append("")

            body_lines.append("Please check the CareNest dashboard to review and log daily care routines.")
            body_lines.append("CareNest - Putting elderly wellbeing at the centre of care.")

            body_text = "\n".join(body_lines)
            sent = send_batch_emails(recipients, subject, body_text)
            total_emails_sent += sent

            results.append({
                "care_id": profile.care_id,
                "elder_name": profile.elder_name,
                "recipients": recipients,
                "missed_doses": missed_doses,
                "upcoming_doses": upcoming_doses,
                "upcoming_appointments": upcoming_appointments,
                "emails_delivered": sent,
            })

    return {
        "timestamp": now.isoformat(),
        "profiles_checked": len(profiles),
        "total_alerts_found": total_alerts_found,
        "total_emails_sent": total_emails_sent,
        "details": results,
    }
