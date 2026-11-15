"""Medications management router with Gemini-powered plain-language explanations."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import DEFAULT_SCHEDULE_TIMES, settings
from app.database import get_db
from app.dependencies import get_current_user, require_editor
from app.models import Medication
from app.schemas import MedicationResponse
from app.services.gemini_service import explain_medication

router: APIRouter = APIRouter()
templates: Jinja2Templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _clean_schedule_times(raw_times_str: str) -> str:
    """Validate and format comma-separated schedule times.

    Args:
        raw_times_str (str): Input string of times.

    Returns:
        str: Comma-separated string of validated times.
    """
    parts = [t.strip() for t in raw_times_str.split(",") if t.strip()]
    return ", ".join(parts) if parts else DEFAULT_SCHEDULE_TIMES


@router.get("/medications", response_class=HTMLResponse)
def list_medications(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
    msg: str | None = None,
) -> HTMLResponse:
    """List all medications configured for this healthcare profile.

    Args:
        request (Request): The incoming HTTP request.
        current_user (Dict[str, Any]): Active authenticated user session.
        db (Session): Database session.
        msg (Optional[str]): Flash feedback message.

    Returns:
        HTMLResponse: Rendered medications.html.
    """
    profile_id: int = current_user["profile_id"]
    meds = (
        db.query(Medication).filter(Medication.profile_id == profile_id).order_by(Medication.name.asc()).all()
    )

    return templates.TemplateResponse(
        request=request,
        name="medications.html",
        context={
            "current_user": current_user,
            "medications": meds,
            "msg": msg,
            "app_name": settings.APP_NAME,
        },
    )


@router.get("/medications/new", response_class=HTMLResponse)
def new_medication_page(
    request: Request,
    current_user: dict[str, Any] = Depends(require_editor),
    error: str | None = None,
) -> HTMLResponse:
    """Render form to add a new medication.

    Args:
        request (Request): The incoming HTTP request.
        current_user (Dict[str, Any]): Authenticated editor session.
        error (Optional[str]): Error message if previous submission failed.

    Returns:
        HTMLResponse: Rendered medication_form.html.
    """
    today_str: str = date.today().isoformat()
    return templates.TemplateResponse(
        request=request,
        name="medication_form.html",
        context={
            "current_user": current_user,
            "is_edit": False,
            "medication": None,
            "today_str": today_str,
            "error": error,
            "app_name": settings.APP_NAME,
        },
    )


@router.post("/medications/new")
def create_medication(
    request: Request,
    name: str = Form(...),
    dosage: str = Form(...),
    times_per_day: int = Form(...),
    schedule_times: str = Form(...),
    start_date: str = Form(...),
    end_date: str | None = Form(None),
    notes: str | None = Form(None),
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Create a new medication record with pre-cached plain-language explanation.

    Args:
        request (Request): The incoming HTTP request.
        name (str): Drug name.
        dosage (str): Dosage strength.
        times_per_day (int): Daily frequency.
        schedule_times (str): Comma-separated HH:MM times.
        start_date (str): Prescription start date.
        end_date (Optional[str]): Optional end date.
        notes (Optional[str]): Doctor instructions.
        current_user (Dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /medications with status message.
    """
    profile_id: int = current_user["profile_id"]
    clean_name: str = name.strip()
    clean_dosage: str = dosage.strip()
    clean_schedule: str = _clean_schedule_times(schedule_times)

    try:
        parsed_start = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        parsed_start = date.today()

    parsed_end: date | None = None
    if end_date and end_date.strip():
        try:
            parsed_end = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            parsed_end = None

    explanation_data = explain_medication(clean_name, clean_dosage, notes or "")
    explanation_json = json.dumps(explanation_data)

    new_med = Medication(
        profile_id=profile_id,
        name=clean_name,
        dosage=clean_dosage,
        times_per_day=max(1, times_per_day),
        schedule_times=clean_schedule,
        start_date=parsed_start,
        end_date=parsed_end,
        notes=notes.strip() if notes else None,
        plain_explanation=explanation_json,
    )
    db.add(new_med)
    db.commit()
    db.refresh(new_med)

    return RedirectResponse(
        url=f"/medications?msg=Medication+{new_med.name}+added+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/medications/{med_id}/edit", response_class=HTMLResponse)
def edit_medication_page(
    med_id: int,
    request: Request,
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
    error: str | None = None,
) -> HTMLResponse:
    """Render edit form for an existing medication.

    Args:
        med_id (int): Medication database ID.
        request (Request): The incoming HTTP request.
        current_user (Dict[str, Any]): Authenticated editor session.
        db (Session): Database session.
        error (Optional[str]): Form error message.

    Returns:
        HTMLResponse: Rendered medication_form.html.

    Raises:
        HTTPException: 404 if medication not found.
    """
    profile_id: int = current_user["profile_id"]
    med: Medication | None = (
        db.query(Medication)
        .filter(
            Medication.id == med_id,
            Medication.profile_id == profile_id,
        )
        .first()
    )
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    return templates.TemplateResponse(
        request=request,
        name="medication_form.html",
        context={
            "current_user": current_user,
            "is_edit": True,
            "medication": med,
            "today_str": date.today().isoformat(),
            "error": error,
            "app_name": settings.APP_NAME,
        },
    )


@router.post("/medications/{med_id}/edit")
def update_medication(
    med_id: int,
    request: Request,
    name: str = Form(...),
    dosage: str = Form(...),
    times_per_day: int = Form(...),
    schedule_times: str = Form(...),
    start_date: str = Form(...),
    end_date: str | None = Form(None),
    notes: str | None = Form(None),
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Update medication details and refresh its explanation.

    Args:
        med_id (int): Medication database ID.
        request (Request): The incoming HTTP request.
        name (str): Drug name.
        dosage (str): Dosage strength.
        times_per_day (int): Daily frequency.
        schedule_times (str): Comma-separated HH:MM times.
        start_date (str): Prescription start date.
        end_date (Optional[str]): Optional end date.
        notes (Optional[str]): Instructions.
        current_user (Dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /medications with status message.

    Raises:
        HTTPException: 404 if medication not found.
    """
    profile_id: int = current_user["profile_id"]
    med: Medication | None = (
        db.query(Medication)
        .filter(
            Medication.id == med_id,
            Medication.profile_id == profile_id,
        )
        .first()
    )
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    med.name = name.strip()
    med.dosage = dosage.strip()
    med.times_per_day = max(1, times_per_day)
    med.schedule_times = _clean_schedule_times(schedule_times)

    try:
        med.start_date = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        pass

    if end_date and end_date.strip():
        try:
            med.end_date = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            med.end_date = None
    else:
        med.end_date = None

    med.notes = notes.strip() if notes else None

    explanation_data = explain_medication(med.name, med.dosage, med.notes or "")
    med.plain_explanation = json.dumps(explanation_data)

    db.commit()
    return RedirectResponse(
        url=f"/medications?msg=Medication+{med.name}+updated+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/medications/{med_id}/delete")
def delete_medication(
    med_id: int,
    request: Request,
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Delete a medication (Elder and Caretaker only).

    Args:
        med_id (int): Medication database ID.
        request (Request): The incoming HTTP request.
        current_user (Dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /medications with status message.

    Raises:
        HTTPException: 404 if medication not found.
    """
    profile_id: int = current_user["profile_id"]
    med: Medication | None = (
        db.query(Medication)
        .filter(
            Medication.id == med_id,
            Medication.profile_id == profile_id,
        )
        .first()
    )
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    med_name: str = med.name
    db.delete(med)
    db.commit()

    return RedirectResponse(
        url=f"/medications?msg=Medication+{med_name}+removed",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/medications/{med_id}/explain", response_class=HTMLResponse)
def explain_medication_view(
    med_id: int,
    request: Request,
    refresh: bool = False,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Beyond Reminders: View plain-language explanation of a medicine.

    Args:
        med_id (int): Medication database ID.
        request (Request): The incoming HTTP request.
        refresh (bool): Force refresh of AI explanation.
        current_user (Dict[str, Any]): Active user session.
        db (Session): Database session.

    Returns:
        HTMLResponse: Rendered medication_explain.html.

    Raises:
        HTTPException: 404 if medication not found.
    """
    profile_id: int = current_user["profile_id"]
    med: Medication | None = (
        db.query(Medication)
        .filter(
            Medication.id == med_id,
            Medication.profile_id == profile_id,
        )
        .first()
    )
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

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

    return templates.TemplateResponse(
        request=request,
        name="medication_explain.html",
        context={
            "current_user": current_user,
            "medication": med,
            "explanation": explanation,
            "app_name": settings.APP_NAME,
        },
    )


@router.get("/api/medications", response_model=list[MedicationResponse])
def api_list_medications(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Medication]:
    """API endpoint to list medications for the authenticated profile.

    Args:
        current_user (Dict[str, Any]): Active user session.
        db (Session): Database session.

    Returns:
        List[Medication]: List of active medications.
    """
    profile_id: int = current_user["profile_id"]
    return db.query(Medication).filter(Medication.profile_id == profile_id).all()
