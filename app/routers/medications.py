"""Medications management router with Gemini-powered plain-language explanations."""

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_editor
from app.models import Medication
from app.schemas import MedicationResponse
from app.services import medication_service

router: APIRouter = APIRouter()
templates: Jinja2Templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


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
        current_user (dict[str, Any]): Active authenticated user session.
        db (Session): Database session.
        msg (str | None): Flash feedback message.

    Returns:
        HTMLResponse: Rendered medications.html.
    """
    profile_id: int = current_user["profile_id"]
    meds = medication_service.get_profile_medications(db, profile_id)

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
        current_user (dict[str, Any]): Authenticated editor session.
        error (str | None): Error message if previous submission failed.

    Returns:
        HTMLResponse: Rendered medication_form.html.
    """
    return templates.TemplateResponse(
        request=request,
        name="medication_form.html",
        context={
            "current_user": current_user,
            "is_edit": False,
            "medication": None,
            "today_str": date.today().isoformat(),
            "error": error,
            "app_name": settings.APP_NAME,
        },
    )


@router.post("/medications/new")
def create_medication(
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
        name (str): Drug name.
        dosage (str): Dosage strength.
        times_per_day (int): Daily frequency.
        schedule_times (str): Comma-separated HH:MM times.
        start_date (str): Prescription start date.
        end_date (str | None): Optional end date.
        notes (str | None): Doctor instructions.
        current_user (dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /medications with status message.
    """
    profile_id: int = current_user["profile_id"]
    new_med = medication_service.create_medication_record(
        db=db,
        profile_id=profile_id,
        name=name,
        dosage=dosage,
        times_per_day=times_per_day,
        schedule_times=schedule_times,
        start_date=start_date,
        end_date=end_date,
        notes=notes,
    )

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
        current_user (dict[str, Any]): Authenticated editor session.
        db (Session): Database session.
        error (str | None): Form error message.

    Returns:
        HTMLResponse: Rendered medication_form.html.
    """
    profile_id: int = current_user["profile_id"]
    med: Medication = medication_service.get_medication_or_404(db, profile_id, med_id)

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
        name (str): Drug name.
        dosage (str): Dosage strength.
        times_per_day (int): Daily frequency.
        schedule_times (str): Comma-separated HH:MM times.
        start_date (str): Prescription start date.
        end_date (str | None): Optional end date.
        notes (str | None): Instructions.
        current_user (dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /medications with status message.
    """
    profile_id: int = current_user["profile_id"]
    med: Medication = medication_service.get_medication_or_404(db, profile_id, med_id)

    updated_med = medication_service.update_medication_record(
        db=db,
        med=med,
        name=name,
        dosage=dosage,
        times_per_day=times_per_day,
        schedule_times=schedule_times,
        start_date=start_date,
        end_date=end_date,
        notes=notes,
    )

    return RedirectResponse(
        url=f"/medications?msg=Medication+{updated_med.name}+updated+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/medications/{med_id}/delete")
def delete_medication(
    med_id: int,
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Delete a medication (Elder and Caretaker only).

    Args:
        med_id (int): Medication database ID.
        current_user (dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /medications with status message.
    """
    profile_id: int = current_user["profile_id"]
    med: Medication = medication_service.get_medication_or_404(db, profile_id, med_id)

    deleted_name: str = medication_service.delete_medication_record(db, med)

    return RedirectResponse(
        url=f"/medications?msg=Medication+{deleted_name}+removed",
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
        current_user (dict[str, Any]): Active user session.
        db (Session): Database session.

    Returns:
        HTMLResponse: Rendered medication_explain.html.
    """
    profile_id: int = current_user["profile_id"]
    med: Medication = medication_service.get_medication_or_404(db, profile_id, med_id)

    explanation = medication_service.get_or_refresh_explanation(db=db, med=med, refresh=refresh)

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
        current_user (dict[str, Any]): Active user session.
        db (Session): Database session.

    Returns:
        list[Medication]: List of active medications.
    """
    profile_id: int = current_user["profile_id"]
    return medication_service.get_profile_medications(db, profile_id)
