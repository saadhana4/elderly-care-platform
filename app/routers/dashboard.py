"""Dashboard and Today view router for dose tracking and adherence monitoring."""

from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional, require_editor
from app.models import Medication, Profile
from app.services.dose_service import (
    calculate_adherence_percentage,
    compile_today_dose_slots,
    get_active_medications_for_date,
    get_recent_dose_history,
    record_dose_status,
)

router: APIRouter = APIRouter()
templates: Jinja2Templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


@router.get("/", response_class=HTMLResponse)
def index_redirect(
    current_user: dict[str, Any] | None = Depends(get_current_user_optional),
) -> RedirectResponse:
    """Redirect authenticated visitors to /today and unauthenticated visitors to /login.

    Args:
        current_user (Optional[Dict[str, Any]]): Optional user session.

    Returns:
        RedirectResponse: 302 Redirect to destination.
    """
    if current_user:
        return RedirectResponse(url="/today", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@router.get("/today", response_class=HTMLResponse)
def today_view(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
    msg: str | None = None,
) -> HTMLResponse:
    """Render the accessible Today medication dose tracking view.

    Args:
        request (Request): The incoming HTTP request.
        current_user (Dict[str, Any]): Active authenticated user session.
        db (Session): Database session.
        msg (Optional[str]): Flash feedback message if present.

    Returns:
        HTMLResponse: Rendered today.html template.
    """
    today: date = date.today()
    profile_id: int = current_user["profile_id"]
    profile: Profile | None = db.query(Profile).filter(Profile.id == profile_id).first()

    active_meds = get_active_medications_for_date(db, profile_id, today)
    today_logs = profile.dose_logs if profile else []
    today_logs_filtered = [log_entry for log_entry in today_logs if log_entry.dose_date == today]

    now_time_str = datetime.now().strftime("%H:%M")
    today_doses, today_total, today_taken, today_skipped = compile_today_dose_slots(
        active_meds, today_logs_filtered, now_time_str
    )

    adherence_pct = calculate_adherence_percentage(db, profile_id, today, today_taken, today_total)
    recent_history = get_recent_dose_history(db, profile_id)

    return templates.TemplateResponse(
        request=request,
        name="today.html",
        context={
            "current_user": current_user,
            "profile": profile,
            "today_doses": today_doses,
            "today_total_count": today_total,
            "today_taken_count": today_taken,
            "today_skipped_count": today_skipped,
            "adherence_percentage": adherence_pct,
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
    action: str = Form(...),
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Record a medication dose as 'taken' or 'skipped' (Elder and Caretaker only).

    Args:
        request (Request): The incoming HTTP request.
        medication_id (int): ID of the medication.
        dose_date (str): Calendar date string ('YYYY-MM-DD').
        scheduled_time (str): Time of the scheduled dose ('HH:MM').
        action (str): Action status ('taken' or 'skipped').
        current_user (Dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /today with feedback message.

    Raises:
        HTTPException: 400 for invalid action, 404 if medication not found.
    """
    if action not in ("taken", "skipped"):
        raise HTTPException(status_code=400, detail="Invalid dose status action.")

    try:
        parsed_date = datetime.strptime(dose_date.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        parsed_date = date.today()

    profile_id: int = current_user["profile_id"]
    med: Medication | None = (
        db.query(Medication)
        .filter(
            Medication.id == medication_id,
            Medication.profile_id == profile_id,
        )
        .first()
    )
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found.")

    record_dose_status(
        db=db,
        profile_id=profile_id,
        medication_id=medication_id,
        dose_date=parsed_date,
        scheduled_time=scheduled_time,
        action=action,
        role=current_user["role"],
    )

    status_label = "taken" if action == "taken" else "skipped"
    return RedirectResponse(
        url=f"/today?msg=Dose+for+{med.name}+marked+as+{status_label}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
