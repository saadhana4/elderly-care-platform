"""Medications management router with Gemini-powered plain-language explanations."""

import json
from datetime import date, datetime
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile, Medication
from app.dependencies import get_current_user, require_editor
from app.services.gemini_service import explain_medication
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/medications", response_class=HTMLResponse)
def list_medications(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    msg: Optional[str] = None,
):
    """List all medications configured for this healthcare profile."""
    profile_id = current_user["profile_id"]
    meds = db.query(Medication).filter(
        Medication.profile_id == profile_id
    ).order_by(Medication.name.asc()).all()

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
    current_user=Depends(require_editor),
    error: Optional[str] = None,
):
    """Render form to add a new medication."""
    today_str = date.today().isoformat()
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
    end_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    current_user=Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Create a new medication record with initial plain-language explanation."""
    profile_id = current_user["profile_id"]
    clean_name = name.strip()
    clean_dosage = dosage.strip()
    
    # Validate scheduled times
    raw_times = [t.strip() for t in schedule_times.split(",") if t.strip()]
    if not raw_times:
        raw_times = ["08:00"]
    clean_schedule = ", ".join(raw_times)

    try:
        parsed_start = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
    except Exception:
        parsed_start = date.today()

    parsed_end = None
    if end_date and end_date.strip():
        try:
            parsed_end = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        except Exception:
            parsed_end = None

    # Pre-generate Gemini AI explanation
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
    current_user=Depends(require_editor),
    db: Session = Depends(get_db),
    error: Optional[str] = None,
):
    """Render edit form for a medication."""
    profile_id = current_user["profile_id"]
    med = db.query(Medication).filter(
        Medication.id == med_id,
        Medication.profile_id == profile_id,
    ).first()
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
    end_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    current_user=Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Update medication details."""
    profile_id = current_user["profile_id"]
    med = db.query(Medication).filter(
        Medication.id == med_id,
        Medication.profile_id == profile_id,
    ).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    med.name = name.strip()
    med.dosage = dosage.strip()
    med.times_per_day = max(1, times_per_day)
    
    raw_times = [t.strip() for t in schedule_times.split(",") if t.strip()]
    med.schedule_times = ", ".join(raw_times) if raw_times else "08:00"

    try:
        med.start_date = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
    except Exception:
        pass

    if end_date and end_date.strip():
        try:
            med.end_date = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        except Exception:
            med.end_date = None
    else:
        med.end_date = None

    med.notes = notes.strip() if notes else None

    # Refresh explanation if medication name changed
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
    current_user=Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Delete a medication (Elder and Caretaker only)."""
    profile_id = current_user["profile_id"]
    med = db.query(Medication).filter(
        Medication.id == med_id,
        Medication.profile_id == profile_id,
    ).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    med_name = med.name
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
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Beyond Reminders: View plain-language explanation of a medicine."""
    profile_id = current_user["profile_id"]
    med = db.query(Medication).filter(
        Medication.id == med_id,
        Medication.profile_id == profile_id,
    ).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    # Load from cache or generate
    explanation = None
    if med.plain_explanation and not refresh:
        try:
            explanation = json.loads(med.plain_explanation)
        except Exception:
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


# ---------------------------------------------------------------------------
# Programmatic JSON API Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/medications", response_model=list)
def api_list_medications(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """API endpoint to list medications for the authenticated profile."""
    profile_id = current_user["profile_id"]
    return db.query(Medication).filter(Medication.profile_id == profile_id).all()
