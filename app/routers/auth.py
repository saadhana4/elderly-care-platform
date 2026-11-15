"""Authentication and profile onboarding router."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import SESSION_COOKIE_NAME, SESSION_TOKEN_EXPIRATION_SECONDS, settings
from app.database import get_db
from app.dependencies import get_current_user_optional
from app.schemas import LoginRequest, ProfileCreate
from app.security import (
    auth_rate_limiter,
    create_session_token,
)
from app.services.profile_service import (
    authenticate_passcode,
    create_care_profile,
)

router: APIRouter = APIRouter()
templates: Jinja2Templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    error: str | None = None,
    success: str | None = None,
    current_user: dict[str, Any] | None = Depends(get_current_user_optional),
) -> Response:
    """Render the login page or redirect authenticated users to /today.

    Args:
        request (Request): The incoming HTTP request.
        error (str | None): Error message if login failed.
        success (str | None): Success notice if logged out or registered.
        current_user (dict[str, Any] | None): Existing user session if active.

    Returns:
        Response: Redirect or rendered login.html.
    """
    if current_user:
        return RedirectResponse(url="/today", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": error,
            "success": success,
            "app_name": settings.APP_NAME,
        },
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    care_id: str = Form(...),
    passcode: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    """Process passcode-based authentication for elder, caretaker, or family.

    Args:
        request (Request): The incoming HTTP request.
        care_id (str): Care Profile ID entered by user.
        passcode (str): Role passcode entered by user.
        db (Session): Database session.

    Returns:
        Response: Redirect to /today on success or re-rendered login.html.
    """
    client_ip: str = request.client.host if request.client else "127.0.0.1"
    clean_care_id: str = care_id.strip().upper()

    is_limited, retry_after = auth_rate_limiter.is_rate_limited(client_ip, clean_care_id)
    if is_limited:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": f"Too many failed attempts. For security, please wait {retry_after} seconds before trying again.",
                "care_id": clean_care_id,
                "app_name": settings.APP_NAME,
            },
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    profile, role, error_msg = authenticate_passcode(db, clean_care_id, passcode)
    if error_msg:
        auth_rate_limiter.record_failure(client_ip, clean_care_id)
        status_code = (
            status.HTTP_403_FORBIDDEN if "paused or revoked" in error_msg else status.HTTP_401_UNAUTHORIZED
        )
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": error_msg,
                "care_id": clean_care_id,
                "app_name": settings.APP_NAME,
            },
            status_code=status_code,
        )

    auth_rate_limiter.record_success(client_ip, clean_care_id)
    session_token = create_session_token(
        {
            "profile_id": profile.id,
            "care_id": profile.care_id,
            "elder_name": profile.elder_name,
            "role": role,
        }
    )

    response = RedirectResponse(url="/today", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        max_age=SESSION_TOKEN_EXPIRATION_SECONDS,
    )
    return response


@router.get("/create-profile", response_class=HTMLResponse)
def create_profile_page(
    request: Request,
    error: str | None = None,
) -> Response:
    """Render the profile registration form.

    Args:
        request (Request): The incoming HTTP request.
        error (str | None): Error message if previous submission failed.

    Returns:
        Response: Rendered create_profile.html.
    """
    return templates.TemplateResponse(
        request=request,
        name="create_profile.html",
        context={
            "error": error,
            "app_name": settings.APP_NAME,
        },
    )


@router.post("/create-profile", response_class=HTMLResponse)
def create_profile_submit(
    request: Request,
    elder_name: str = Form(...),
    elder_age: int | None = Form(None),
    emergency_notes: str | None = Form(None),
    elder_email: str | None = Form(None),
    caretaker_email: str | None = Form(None),
    family_email: str | None = Form(None),
    db: Session = Depends(get_db),
) -> Response:
    """Create a new care profile and display the 3 generated role passcodes.

    Args:
        request (Request): The incoming HTTP request.
        elder_name (str): Full name of the elderly individual.
        elder_age (int | None): Age of the senior.
        emergency_notes (str | None): Emergency directives or allergies.
        elder_email (str | None): Elder's contact email.
        caretaker_email (str | None): Caretaker's contact email.
        family_email (str | None): Family contact email.
        db (Session): Database session.

    Returns:
        Response: Rendered passcodes_created.html with plain passcodes.
    """
    clean_name: str = elder_name.strip()
    if len(clean_name) < 2:
        return templates.TemplateResponse(
            request=request,
            name="create_profile.html",
            context={
                "error": "Please enter a valid elder name (at least 2 characters).",
                "app_name": settings.APP_NAME,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    profile, passcodes = create_care_profile(
        db=db,
        elder_name=clean_name,
        elder_age=elder_age,
        emergency_notes=emergency_notes,
        elder_email=elder_email,
        caretaker_email=caretaker_email,
        family_email=family_email,
    )

    return templates.TemplateResponse(
        request=request,
        name="passcodes_created.html",
        context={
            "profile": profile,
            "elder_code": passcodes["elder"],
            "caretaker_code": passcodes["caretaker"],
            "family_code": passcodes["family"],
            "app_name": settings.APP_NAME,
        },
    )


@router.get("/logout")
def logout() -> RedirectResponse:
    """Clear session cookie and redirect to login page.

    Returns:
        RedirectResponse: 302 Redirect to /login.
    """
    response: RedirectResponse = RedirectResponse(
        url="/login?success=You+have+been+signed+out+safely",
        status_code=status.HTTP_302_FOUND,
    )
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# Programmatic JSON API Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/profiles", response_model=dict, status_code=status.HTTP_201_CREATED)
def api_create_profile(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """API endpoint to create a care profile and return the 3 generated role passcodes.

    Args:
        payload (ProfileCreate): Validated request payload.
        db (Session): Database session.

    Returns:
        dict[str, Any]: Profile metadata and initial plain passcodes.
    """
    profile, passcodes = create_care_profile(
        db=db,
        elder_name=payload.elder_name,
        elder_age=payload.elder_age,
        emergency_notes=payload.emergency_notes,
        elder_email=payload.elder_email,
        caretaker_email=payload.caretaker_email,
        family_email=payload.family_email,
    )

    return {
        "id": profile.id,
        "care_id": profile.care_id,
        "elder_name": profile.elder_name,
        "passcodes": passcodes,
    }


@router.post("/api/login")
def api_login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """API endpoint to authenticate with Care ID and role passcode.

    Args:
        payload (LoginRequest): Input credentials.
        request (Request): Incoming HTTP request.
        db (Session): Database session.

    Returns:
        dict[str, Any]: Bearer access token and profile role details.

    Raises:
        HTTPException: 429 if rate-limited, 403 if role disabled, 401 if invalid.
    """
    client_ip: str = request.client.host if request.client else "127.0.0.1"
    clean_care_id: str = payload.care_id.strip().upper()

    is_limited, retry_after = auth_rate_limiter.is_rate_limited(client_ip, clean_care_id)
    if is_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Please wait {retry_after} seconds.",
        )

    profile, role, error_msg = authenticate_passcode(db, clean_care_id, payload.passcode)
    if error_msg:
        auth_rate_limiter.record_failure(client_ip, clean_care_id)
        if "paused or revoked" in error_msg:
            detail_msg = f"{role.capitalize() if role else 'Role'} access is disabled."
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail_msg)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_msg)

    auth_rate_limiter.record_success(client_ip, clean_care_id)
    token = create_session_token(
        {
            "profile_id": profile.id,
            "care_id": profile.care_id,
            "elder_name": profile.elder_name,
            "role": role,
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": role,
        "care_id": profile.care_id,
        "elder_name": profile.elder_name,
    }
