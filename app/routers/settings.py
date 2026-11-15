"""Settings and Access Control router (Elder has ultimate authority)."""

from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile
from app.dependencies import require_elder
from app.security import generate_passcode, hash_passcode
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/settings/access", response_class=HTMLResponse)
def access_settings_page(
    request: Request,
    current_user=Depends(require_elder),
    db: Session = Depends(get_db),
    msg: Optional[str] = None,
    new_code_role: Optional[str] = None,
    new_code_value: Optional[str] = None,
):
    """Elder access control panel: approve/revoke permissions & manage passcodes."""
    profile_id = current_user["profile_id"]
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    return templates.TemplateResponse(
        request=request,
        name="profile_access.html",
        context={
            "current_user": current_user,
            "profile": profile,
            "msg": msg,
            "new_code_role": new_code_role,
            "new_code_value": new_code_value,
            "app_name": settings.APP_NAME,
        },
    )


@router.post("/settings/access/toggle-role")
def toggle_role_access(
    request: Request,
    target_role: str = Form(...),  # "caretaker" or "family"
    enabled: str = Form(...),      # "true" or "false"
    current_user=Depends(require_elder),
    db: Session = Depends(get_db),
):
    """Elder can approve or revoke caretaker and family access immediately."""
    profile_id = current_user["profile_id"]
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    is_active = (enabled.lower() == "true")

    if target_role == "caretaker":
        profile.caretaker_access_enabled = is_active
        action_text = "enabled" if is_active else "revoked"
        db.commit()
        return RedirectResponse(
            url=f"/settings/access?msg=Caretaker+access+has+been+{action_text}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    elif target_role == "family":
        profile.family_access_enabled = is_active
        action_text = "enabled" if is_active else "revoked"
        db.commit()
        return RedirectResponse(
            url=f"/settings/access?msg=Family+access+has+been+{action_text}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid role specified.")


@router.post("/settings/access/regenerate-passcode")
def regenerate_passcode(
    request: Request,
    target_role: str = Form(...),  # "elder", "caretaker", or "family"
    current_user=Depends(require_elder),
    db: Session = Depends(get_db),
):
    """Elder can regenerate a fresh passcode for any role, invalidating the old one."""
    profile_id = current_user["profile_id"]
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    new_code = generate_passcode(target_role)
    new_hash = hash_passcode(new_code)

    if target_role == "elder":
        profile.elder_passcode_hash = new_hash
    elif target_role == "caretaker":
        profile.caretaker_passcode_hash = new_hash
    elif target_role == "family":
        profile.family_passcode_hash = new_hash
    else:
        raise HTTPException(status_code=400, detail="Invalid target role.")

    db.commit()

    return RedirectResponse(
        url=f"/settings/access?msg=New+passcode+generated+for+{target_role.capitalize()}&new_code_role={target_role}&new_code_value={new_code}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/access/update-contacts")
def update_contact_emails(
    request: Request,
    elder_email: Optional[str] = Form(None),
    caretaker_email: Optional[str] = Form(None),
    family_email: Optional[str] = Form(None),
    emergency_notes: Optional[str] = Form(None),
    current_user=Depends(require_elder),
    db: Session = Depends(get_db),
):
    """Update reminder email addresses and emergency health notes."""
    profile_id = current_user["profile_id"]
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    profile.elder_email = elder_email.strip() if elder_email else None
    profile.caretaker_email = caretaker_email.strip() if caretaker_email else None
    profile.family_email = family_email.strip() if family_email else None
    profile.emergency_notes = emergency_notes.strip() if emergency_notes else None

    db.commit()

    return RedirectResponse(
        url="/settings/access?msg=Contact+emails+and+health+notes+updated+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
