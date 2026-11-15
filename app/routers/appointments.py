"""Appointments router for managing doctor visits and healthcare consultations."""

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_editor
from app.models import Appointment

router: APIRouter = APIRouter()
templates: Jinja2Templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


@router.get("/appointments", response_class=HTMLResponse)
def list_appointments(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
    msg: str | None = None,
) -> HTMLResponse:
    """List upcoming and past doctor appointments.

    Args:
        request (Request): The incoming HTTP request.
        current_user (Dict[str, Any]): Active authenticated user session.
        db (Session): Database session.
        msg (Optional[str]): Flash feedback message.

    Returns:
        HTMLResponse: Rendered appointments.html.
    """
    profile_id: int = current_user["profile_id"]
    now: datetime = datetime.now()

    all_appts: list[Appointment] = (
        db.query(Appointment)
        .filter(Appointment.profile_id == profile_id)
        .order_by(Appointment.appointment_date.asc())
        .all()
    )

    upcoming_appts: list[Appointment] = [a for a in all_appts if a.appointment_date >= now]
    past_appts: list[Appointment] = [a for a in all_appts if a.appointment_date < now]
    past_appts.reverse()

    return templates.TemplateResponse(
        request=request,
        name="appointments.html",
        context={
            "current_user": current_user,
            "upcoming_appts": upcoming_appts,
            "past_appts": past_appts,
            "msg": msg,
            "app_name": settings.APP_NAME,
        },
    )


@router.get("/appointments/new", response_class=HTMLResponse)
def new_appointment_page(
    request: Request,
    current_user: dict[str, Any] = Depends(require_editor),
    error: str | None = None,
) -> HTMLResponse:
    """Render form to schedule a new doctor appointment.

    Args:
        request (Request): The incoming HTTP request.
        current_user (Dict[str, Any]): Authenticated editor session.
        error (Optional[str]): Error message if previous submission failed.

    Returns:
        HTMLResponse: Rendered appointment_form.html.
    """
    default_datetime: str = datetime.now().strftime("%Y-%m-%dT%H:00")
    return templates.TemplateResponse(
        request=request,
        name="appointment_form.html",
        context={
            "current_user": current_user,
            "is_edit": False,
            "appointment": None,
            "default_datetime": default_datetime,
            "error": error,
            "app_name": settings.APP_NAME,
        },
    )


@router.post("/appointments/new")
def create_appointment(
    request: Request,
    doctor_name: str = Form(...),
    appointment_date: str = Form(...),
    location: str | None = Form(None),
    notes: str | None = Form(None),
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Create a new doctor appointment.

    Args:
        request (Request): The incoming HTTP request.
        doctor_name (str): Doctor or clinic title.
        appointment_date (str): ISO formatted datetime string.
        location (Optional[str]): Physical clinic address or room.
        notes (Optional[str]): Preparation instructions.
        current_user (Dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /appointments with status message.

    Raises:
        HTTPException: 400 if appointment date cannot be parsed.
    """
    profile_id: int = current_user["profile_id"]
    clean_doctor: str = doctor_name.strip()

    try:
        parsed_dt: datetime = datetime.fromisoformat(appointment_date.strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid appointment date format.")

    new_appt = Appointment(
        profile_id=profile_id,
        doctor_name=clean_doctor,
        appointment_date=parsed_dt,
        location=location.strip() if location else None,
        notes=notes.strip() if notes else None,
    )
    db.add(new_appt)
    db.commit()
    db.refresh(new_appt)

    return RedirectResponse(
        url=f"/appointments?msg=Appointment+with+{new_appt.doctor_name}+scheduled+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/appointments/{appt_id}/edit", response_class=HTMLResponse)
def edit_appointment_page(
    appt_id: int,
    request: Request,
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
    error: str | None = None,
) -> HTMLResponse:
    """Render form to edit an existing appointment.

    Args:
        appt_id (int): Appointment database ID.
        request (Request): The incoming HTTP request.
        current_user (Dict[str, Any]): Authenticated editor session.
        db (Session): Database session.
        error (Optional[str]): Error message if previous update failed.

    Returns:
        HTMLResponse: Rendered appointment_form.html.

    Raises:
        HTTPException: 404 if appointment not found.
    """
    profile_id: int = current_user["profile_id"]
    appt: Appointment | None = (
        db.query(Appointment)
        .filter(
            Appointment.id == appt_id,
            Appointment.profile_id == profile_id,
        )
        .first()
    )
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    formatted_dt: str = appt.appointment_date.strftime("%Y-%m-%dT%H:%M")
    return templates.TemplateResponse(
        request=request,
        name="appointment_form.html",
        context={
            "current_user": current_user,
            "is_edit": True,
            "appointment": appt,
            "default_datetime": formatted_dt,
            "error": error,
            "app_name": settings.APP_NAME,
        },
    )


@router.post("/appointments/{appt_id}/edit")
def update_appointment(
    appt_id: int,
    request: Request,
    doctor_name: str = Form(...),
    appointment_date: str = Form(...),
    location: str | None = Form(None),
    notes: str | None = Form(None),
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Update appointment details.

    Args:
        appt_id (int): Appointment database ID.
        request (Request): The incoming HTTP request.
        doctor_name (str): Doctor or clinic title.
        appointment_date (str): ISO formatted datetime string.
        location (Optional[str]): Clinic location.
        notes (Optional[str]): Notes.
        current_user (Dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /appointments with status message.

    Raises:
        HTTPException: 400 for bad date format, 404 if appointment not found.
    """
    profile_id: int = current_user["profile_id"]
    appt: Appointment | None = (
        db.query(Appointment)
        .filter(
            Appointment.id == appt_id,
            Appointment.profile_id == profile_id,
        )
        .first()
    )
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    try:
        parsed_dt: datetime = datetime.fromisoformat(appointment_date.strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid appointment date format.")

    appt.doctor_name = doctor_name.strip()
    appt.appointment_date = parsed_dt
    appt.location = location.strip() if location else None
    appt.notes = notes.strip() if notes else None

    db.commit()
    return RedirectResponse(
        url=f"/appointments?msg=Appointment+with+{appt.doctor_name}+updated",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/appointments/{appt_id}/delete")
def delete_appointment(
    appt_id: int,
    request: Request,
    current_user: dict[str, Any] = Depends(require_editor),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Delete an appointment.

    Args:
        appt_id (int): Appointment database ID.
        request (Request): The incoming HTTP request.
        current_user (Dict[str, Any]): Authenticated editor session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /appointments with status message.

    Raises:
        HTTPException: 404 if appointment not found.
    """
    profile_id: int = current_user["profile_id"]
    appt: Appointment | None = (
        db.query(Appointment)
        .filter(
            Appointment.id == appt_id,
            Appointment.profile_id == profile_id,
        )
        .first()
    )
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    doc_name: str = appt.doctor_name
    db.delete(appt)
    db.commit()

    return RedirectResponse(
        url=f"/appointments?msg=Appointment+with+{doc_name}+removed",
        status_code=status.HTTP_303_SEE_OTHER,
    )
