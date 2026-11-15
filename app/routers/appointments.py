"""Appointments router for managing doctor visits and healthcare consultations."""

from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile, Appointment
from app.dependencies import get_current_user, require_editor
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/appointments", response_class=HTMLResponse)
def list_appointments(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    msg: Optional[str] = None,
):
    """List upcoming and past doctor appointments."""
    profile_id = current_user["profile_id"]
    now = datetime.now()

    all_appts = db.query(Appointment).filter(
        Appointment.profile_id == profile_id
    ).order_by(Appointment.appointment_date.asc()).all()

    upcoming_appts = [a for a in all_appts if a.appointment_date >= now]
    past_appts = [a for a in all_appts if a.appointment_date < now]
    past_appts.reverse()  # Most recent past first

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
    current_user=Depends(require_editor),
    error: Optional[str] = None,
):
    """Render form to schedule a new doctor appointment."""
    default_datetime = datetime.now().strftime("%Y-%m-%dT%H:00")
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
    location: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    current_user=Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Create a new doctor appointment."""
    profile_id = current_user["profile_id"]
    clean_doctor = doctor_name.strip()

    try:
        parsed_dt = datetime.fromisoformat(appointment_date.strip())
    except Exception:
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
    current_user=Depends(require_editor),
    db: Session = Depends(get_db),
    error: Optional[str] = None,
):
    """Render form to edit an existing appointment."""
    profile_id = current_user["profile_id"]
    appt = db.query(Appointment).filter(
        Appointment.id == appt_id,
        Appointment.profile_id == profile_id,
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    formatted_dt = appt.appointment_date.strftime("%Y-%m-%dT%H:%M")
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
    location: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    current_user=Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Update appointment details."""
    profile_id = current_user["profile_id"]
    appt = db.query(Appointment).filter(
        Appointment.id == appt_id,
        Appointment.profile_id == profile_id,
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    try:
        parsed_dt = datetime.fromisoformat(appointment_date.strip())
    except Exception:
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
    current_user=Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Delete an appointment."""
    profile_id = current_user["profile_id"]
    appt = db.query(Appointment).filter(
        Appointment.id == appt_id,
        Appointment.profile_id == profile_id,
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    doc_name = appt.doctor_name
    db.delete(appt)
    db.commit()

    return RedirectResponse(
        url=f"/appointments?msg=Appointment+with+{doc_name}+removed",
        status_code=status.HTTP_303_SEE_OTHER,
    )
