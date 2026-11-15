"""Dashboard and Today view router for dose tracking and adherence monitoring."""

from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile, Medication, DoseLog
from app.dependencies import get_current_user, get_current_user_optional, require_editor
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def index_redirect(current_user=Depends(get_current_user_optional)):
    """Landing route: redirect authenticated users to /today, else to /login."""
    if current_user:
        return RedirectResponse(url="/today", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@router.get("/today", response_class=HTMLResponse)
def today_view(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    msg: Optional[str] = None,
):
    """Render the accessible 'Today' medication dose tracking view."""
    today = date.today()
    profile_id = current_user["profile_id"]
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    # 1. Fetch active medications for today
    active_meds = db.query(Medication).filter(
        Medication.profile_id == profile_id,
        Medication.start_date <= today,
    ).all()
    # Filter end_date in Python to safely handle None
    active_meds = [m for m in active_meds if m.end_date is None or m.end_date >= today]

    # 2. Fetch today's dose logs
    today_logs = db.query(DoseLog).filter(
        DoseLog.profile_id == profile_id,
        DoseLog.dose_date == today,
    ).all()
    logs_map = {(l.medication_id, l.scheduled_time): l for l in today_logs}

    # 3. Construct dose slots for today
    now_time_str = datetime.now().strftime("%H:%M")
    today_doses = []
    today_total_count = 0
    today_taken_count = 0
    today_skipped_count = 0

    for med in active_meds:
        times = [t.strip() for t in med.schedule_times.split(",") if t.strip()]
        for t in times:
            today_total_count += 1
            log = logs_map.get((med.id, t))
            dose_status = "pending"
            if log:
                dose_status = log.status
                if log.status == "taken":
                    today_taken_count += 1
                elif log.status == "skipped":
                    today_skipped_count += 1
            else:
                if t < now_time_str:
                    dose_status = "overdue"

            today_doses.append({
                "medication_id": med.id,
                "name": med.name,
                "dosage": med.dosage,
                "notes": med.notes,
                "scheduled_time": t,
                "status": dose_status,
                "log": log,
            })

    # Sort doses chronologically
    today_doses.sort(key=lambda d: d["scheduled_time"])

    # 4. Calculate 7-Day Adherence Percentage
    seven_days_ago = today - timedelta(days=7)
    past_logs = db.query(DoseLog).filter(
        DoseLog.profile_id == profile_id,
        DoseLog.dose_date >= seven_days_ago,
        DoseLog.dose_date <= today,
    ).all()

    past_taken = sum(1 for l in past_logs if l.status == "taken")
    past_total = len(past_logs)
    
    if past_total > 0:
        adherence_percentage = round((past_taken / past_total) * 100)
    elif today_total_count > 0:
        adherence_percentage = round((today_taken_count / today_total_count) * 100)
    else:
        adherence_percentage = 100

    # 5. Fetch recent dose history
    recent_history = db.query(DoseLog).filter(
        DoseLog.profile_id == profile_id,
    ).order_by(DoseLog.dose_date.desc(), DoseLog.logged_at.desc()).limit(10).all()

    return templates.TemplateResponse(
        request=request,
        name="today.html",
        context={
            "current_user": current_user,
            "profile": profile,
            "today_doses": today_doses,
            "today_total_count": today_total_count,
            "today_taken_count": today_taken_count,
            "today_skipped_count": today_skipped_count,
            "adherence_percentage": adherence_percentage,
            "recent_history": recent_history,
            "today_date_str": today.strftime("%A, %B %d, %Y"),
            "today_iso_date": today.isoformat(),
            "msg": msg,
            "app_name": settings.APP_NAME,
        },
    )


@router.post("/doses/log")
def log_dose(
    request: Request,
    medication_id: int = Form(...),
    dose_date: str = Form(...),
    scheduled_time: str = Form(...),
    action: str = Form(...),  # "taken" or "skipped"
    current_user=Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Record medication dose as 'taken' or 'skipped' (Elder and Caretaker only)."""
    if action not in ("taken", "skipped"):
        raise HTTPException(status_code=400, detail="Invalid dose status action.")

    try:
        parsed_date = datetime.strptime(dose_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        parsed_date = date.today()

    clean_time = scheduled_time.strip()
    profile_id = current_user["profile_id"]

    # Verify medication belongs to profile
    med = db.query(Medication).filter(
        Medication.id == medication_id,
        Medication.profile_id == profile_id,
    ).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found.")

    # Find existing log or create new
    existing_log = db.query(DoseLog).filter(
        DoseLog.profile_id == profile_id,
        DoseLog.medication_id == medication_id,
        DoseLog.dose_date == parsed_date,
        DoseLog.scheduled_time == clean_time,
    ).first()

    if existing_log:
        existing_log.status = action
        existing_log.logged_at = datetime.now(timezone.utc)
        existing_log.logged_by_role = current_user["role"]
    else:
        new_log = DoseLog(
            profile_id=profile_id,
            medication_id=medication_id,
            dose_date=parsed_date,
            scheduled_time=clean_time,
            status=action,
            logged_at=datetime.now(timezone.utc),
            logged_by_role=current_user["role"],
        )
        db.add(new_log)

    db.commit()

    # Return redirect or JSON
    status_label = "taken" if action == "taken" else "skipped"
    return RedirectResponse(
        url=f"/today?msg=Dose+for+{med.name}+marked+as+{status_label}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
