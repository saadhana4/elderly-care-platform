"""Settings and Access Control router (Elder has ultimate authority)."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import require_elder
from app.models import Profile
from app.services.profile_service import regenerate_role_passcode

router: APIRouter = APIRouter()
templates: Jinja2Templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


@router.get("/settings/access", response_class=HTMLResponse)
def access_settings_page(
    request: Request,
    current_user: dict[str, Any] = Depends(require_elder),
    db: Session = Depends(get_db),
    msg: str | None = None,
    new_code_role: str | None = None,
    new_code_value: str | None = None,
) -> HTMLResponse:
    """Render Elder access control panel to approve/revoke permissions & manage passcodes.

    Args:
        request (Request): The incoming HTTP request.
        current_user (Dict[str, Any]): Active elder user session.
        db (Session): Database session.
        msg (Optional[str]): Flash feedback message.
        new_code_role (Optional[str]): Role of recently regenerated passcode if any.
        new_code_value (Optional[str]): Plaintext value of regenerated passcode to display.

    Returns:
        HTMLResponse: Rendered profile_access.html.
    """
    profile_id: int = current_user["profile_id"]
    profile: Profile | None = db.query(Profile).filter(Profile.id == profile_id).first()

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
    target_role: str = Form(...),
    enabled: str = Form(...),
    current_user: dict[str, Any] = Depends(require_elder),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Approve or revoke caretaker and family access immediately.

    Args:
        request (Request): The incoming HTTP request.
        target_role (str): 'caretaker' or 'family'.
        enabled (str): 'true' or 'false'.
        current_user (Dict[str, Any]): Active elder user session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /settings/access with status message.

    Raises:
        HTTPException: 400 for unknown role, 404 if profile not found.
    """
    profile_id: int = current_user["profile_id"]
    profile: Profile | None = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    is_active: bool = enabled.strip().lower() == "true"
    clean_target: str = target_role.strip().lower()

    if clean_target == "caretaker":
        profile.caretaker_access_enabled = is_active
        action_text: str = "enabled" if is_active else "revoked"
        db.commit()
        return RedirectResponse(
            url=f"/settings/access?msg=Caretaker+access+has+been+{action_text}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    elif clean_target == "family":
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
    target_role: str = Form(...),
    current_user: dict[str, Any] = Depends(require_elder),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Regenerate a fresh passcode for a role, invalidating the previous one.

    Args:
        request (Request): The incoming HTTP request.
        target_role (str): 'elder', 'caretaker', or 'family'.
        current_user (Dict[str, Any]): Active elder user session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /settings/access displaying the new plain code.

    Raises:
        HTTPException: 400 for invalid role, 404 if profile not found.
    """
    profile_id: int = current_user["profile_id"]
    profile: Profile | None = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    try:
        new_code: str = regenerate_role_passcode(db, profile, target_role)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    clean_role: str = target_role.strip().lower()
    return RedirectResponse(
        url=f"/settings/access?msg=New+passcode+generated+for+{clean_role.capitalize()}&new_code_role={clean_role}&new_code_value={new_code}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/access/update-contacts")
def update_contact_emails(
    request: Request,
    elder_email: str | None = Form(None),
    caretaker_email: str | None = Form(None),
    family_email: str | None = Form(None),
    emergency_notes: str | None = Form(None),
    current_user: dict[str, Any] = Depends(require_elder),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Update notification email addresses and emergency health directives.

    Args:
        request (Request): The incoming HTTP request.
        elder_email (Optional[str]): Elder email.
        caretaker_email (Optional[str]): Caretaker email.
        family_email (Optional[str]): Family email.
        emergency_notes (Optional[str]): Medical directives notes.
        current_user (Dict[str, Any]): Active elder user session.
        db (Session): Database session.

    Returns:
        RedirectResponse: 303 Redirect to /settings/access with status message.

    Raises:
        HTTPException: 404 if profile not found.
    """
    profile_id: int = current_user["profile_id"]
    profile: Profile | None = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    profile.elder_email = elder_email.strip() if elder_email else None
    profile.caretaker_email = caretaker_email.strip() if caretaker_email else None
    profile.family_email = family_email.strip() if family_email else None
    profile.emergency_notes = emergency_notes.strip() if emergency_notes else None

    db.commit()

    return RedirectResponse(
        url="/settings/access?msg=Contact+emails+and+health+notes+updated+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
