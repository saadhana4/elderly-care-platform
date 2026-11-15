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
from app.models import Profile
from app.services.dose_service import (
    calculate_adherence_percentage,
    compile_today_dose_slots,
    get_active_medications_for_date,
    get_recent_dose_history,
    record_dose_status,
)
from app.services.medication_service import get_medication_or_404

router: APIRouter = APIRouter()
templates: Jinja2Templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _build_today_context(
    db: Session,
    profile_id: int,
    current_user: dict[str, Any],
    msg: str | None,
) -> dict[str, Any]:
    """Compile template rendering context for the Today routine view.

    Args:
        db (Session): Database session.
        profile_id (int): Profile primary ID.
        current_user (dict[str, Any]): Active user session.
        msg (Optional[str]): Flash message.

    Returns:
        dict[str, Any]: Variables for template rendering.
    """
    today: date = date.today()
    profile: Profile | None = db.query(Profile).filter(Profile.id == profile_id).first()
    active_meds = get_active_medications_for_date(db, profile_id, today)

    today_logs = profile.dose_logs if profile else []
    today_logs_filtered = [entry for entry in today_logs if entry.dose_date == today]

    now_time_str: str = datetime.now().strftime("%H:%M")
    doses, total_count, taken_count, skipped_count = compile_today_dose_slots(
        active_meds, today_logs_filtered, now_time_str
    )

    adherence_pct: int = calculate_adherence_percentage(db, profile_id, today, taken_count, total_count)
    recent_history = get_recent_dose_history(db, profile_id)

    return {
        "current_user": current_user,
        "profile": profile,
        "today_doses": doses,
        "today_total_count": total_count,
        "today_taken_count": taken_count,
        "today_skipped_count": skipped_count,
        "adherence_percentage": adherence_pct,
        "recent_history": recent_history,
        "today_date_str": today.strftime("%A, %B %d, %Y"),
        "today_iso_date": today.isoformat(),
        "msg": msg,
        "app_name": settings.APP_NAME,
    }


def _parse_dose_date(dose_date_str: str) -> date:
    """Parse dose calendar date or fallback to current day.

    Args:
        dose_date_str (str): Input date string.

    Returns:
        date: Validated calendar date.
    """
    try:
        return datetime.strptime(dose_date_str.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return date.today()


@router.get("/", response_class=HTMLResponse)
def index_redirect(
    current_user: dict[str, Any] | None = Depends(get_current_user_optional),
) -> RedirectResponse:
    """Redirect authenticated visitors to /today and unauthenticated visitors to /login.

    Args:
        current_user (dict[str, Any] | None): Optional user session.

    Returns:
        RedirectResponse: 302 Redirect to destination.
    """
    target = "/today" if current_user else "/login"
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)


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
        current_user (dict[str, Any]): Active authenticated user session.
        db (Session): Database session.
        msg (str | None): Flash feedback message if present.

    Returns:
        HTMLResponse: Rendered today.html template.
    """
    context = _build_today_context(db, current_user["profile_id"], current_user, msg)
    return templates.TemplateResponse(request=request, name="today.html", context=context)


@router.post("/doses/log")
def log_dose(
    medication_id: int = Form(...),
    dose_date: str = Form(...),
    scheduled_time: str = Form(...),
    action: str = Form(...),
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Record a medication dose as 'taken' or 'skipped' (Elder and Caretaker only).

    Args:
        medication_id (int): ID of the medication.
        dose_date (str): Calendar date string ('YYYY-MM-DD').
        scheduled_time (str): Time of the scheduled dose ('HH:MM').
        action (str): Action status ('taken' or 'skipped').
        current_user (dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /today with feedback message.

    Raises:
        HTTPException: 400 for invalid action, 404 if medication not found.
    """
    if action not in ("taken", "skipped"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid dose status action.")

    profile_id: int = current_user["profile_id"]
    med = get_medication_or_404(db, profile_id, medication_id)
    parsed_date: date = _parse_dose_date(dose_date)

    record_dose_status(
        db=db,
        profile_id=profile_id,
        medication_id=medication_id,
        dose_date=parsed_date,
        scheduled_time=scheduled_time,
        action=action,
        role=current_user["role"],
    )

    label: str = "taken" if action == "taken" else "skipped"
    return RedirectResponse(
        url=f"/today?msg=Dose+for+{med.name}+marked+as+{label}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
