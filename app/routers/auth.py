"""Authentication and profile onboarding router."""

from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from app.database import get_db
from app.models import Profile
from app.config import settings
from app.schemas import ProfileCreate, LoginRequest
from app.security import (
    generate_care_id,
    generate_passcode,
    hash_passcode,
    verify_passcode,
    create_session_token,
    auth_rate_limiter,
)
from app.dependencies import SESSION_COOKIE_NAME, get_current_user_optional

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    error: Optional[str] = None,
    success: Optional[str] = None,
    current_user=Depends(get_current_user_optional),
):
    """Render the login page."""
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


@router.post("/login")
def login_submit(
    request: Request,
    care_id: str = Form(...),
    passcode: str = Form(...),
    db: Session = Depends(get_db),
):
    """Process passcode-based authentication for elder, caretaker, or family."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    clean_care_id = care_id.strip().upper()
    clean_passcode = passcode.strip().upper()

    # 1. Rate Limiting Check
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

    # 2. Lookup Profile
    profile = db.query(Profile).filter(Profile.care_id == clean_care_id).first()
    if not profile:
        auth_rate_limiter.record_failure(client_ip, clean_care_id)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Invalid Care ID or Passcode. Please verify your credentials.",
                "care_id": clean_care_id,
                "app_name": settings.APP_NAME,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # 3. Check passcodes across roles
    matched_role = None
    if verify_passcode(clean_passcode, profile.elder_passcode_hash):
        matched_role = "elder"
    elif verify_passcode(clean_passcode, profile.caretaker_passcode_hash):
        if not profile.caretaker_access_enabled:
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error": "Caretaker access has been paused or revoked by the primary elder account.",
                    "care_id": clean_care_id,
                    "app_name": settings.APP_NAME,
                },
                status_code=status.HTTP_403_FORBIDDEN,
            )
        matched_role = "caretaker"
    elif verify_passcode(clean_passcode, profile.family_passcode_hash):
        if not profile.family_access_enabled:
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error": "Family view access has been paused or revoked by the primary elder account.",
                    "care_id": clean_care_id,
                    "app_name": settings.APP_NAME,
                },
                status_code=status.HTTP_403_FORBIDDEN,
            )
        matched_role = "family"

    if not matched_role:
        auth_rate_limiter.record_failure(client_ip, clean_care_id)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Invalid Passcode. Please check the code provided for your role.",
                "care_id": clean_care_id,
                "app_name": settings.APP_NAME,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # 4. Successful login: Clear rate limiter & generate session token
    auth_rate_limiter.record_success(client_ip, clean_care_id)
    session_token = create_session_token({
        "profile_id": profile.id,
        "care_id": profile.care_id,
        "elder_name": profile.elder_name,
        "role": matched_role,
    })

    response = RedirectResponse(url="/today", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        max_age=86400 * 7,
    )
    return response


@router.get("/create-profile", response_class=HTMLResponse)
def create_profile_page(request: Request, error: Optional[str] = None):
    """Render the profile registration form."""
    return templates.TemplateResponse(
        request=request,
        name="create_profile.html",
        context={
            "error": error,
            "app_name": settings.APP_NAME,
        },
    )


@router.post("/create-profile")
def create_profile_submit(
    request: Request,
    elder_name: str = Form(...),
    elder_age: Optional[int] = Form(None),
    emergency_notes: Optional[str] = Form(None),
    elder_email: Optional[str] = Form(None),
    caretaker_email: Optional[str] = Form(None),
    family_email: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Create a new profile and generate 3 role passcodes."""
    clean_name = elder_name.strip()
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

    care_id = generate_care_id()
    # Ensure care_id is unique
    while db.query(Profile).filter(Profile.care_id == care_id).first():
        care_id = generate_care_id()

    elder_code = generate_passcode("elder")
    caretaker_code = generate_passcode("caretaker")
    family_code = generate_passcode("family")

    profile = Profile(
        care_id=care_id,
        elder_name=clean_name,
        elder_age=elder_age if (elder_age and elder_age > 0) else None,
        emergency_notes=emergency_notes.strip() if emergency_notes else None,
        elder_passcode_hash=hash_passcode(elder_code),
        caretaker_passcode_hash=hash_passcode(caretaker_code),
        family_passcode_hash=hash_passcode(family_code),
        caretaker_access_enabled=True,
        family_access_enabled=True,
        elder_email=elder_email.strip() if elder_email else None,
        caretaker_email=caretaker_email.strip() if caretaker_email else None,
        family_email=family_email.strip() if family_email else None,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    # Render passcodes page (displayed once with prominent warnings to write down)
    return templates.TemplateResponse(
        request=request,
        name="passcodes_created.html",
        context={
            "profile": profile,
            "elder_code": elder_code,
            "caretaker_code": caretaker_code,
            "family_code": family_code,
            "app_name": settings.APP_NAME,
        },
    )


@router.get("/logout")
def logout():
    """Clear session cookie and redirect to login."""
    response = RedirectResponse(url="/login?success=You+have+been+signed+out+safely", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# Programmatic JSON API Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/profiles", response_model=dict, status_code=status.HTTP_201_CREATED)
def api_create_profile(payload: ProfileCreate, db: Session = Depends(get_db)):
    """API endpoint to create profile and return the 3 generated role passcodes."""
    care_id = generate_care_id()
    while db.query(Profile).filter(Profile.care_id == care_id).first():
        care_id = generate_care_id()

    elder_code = generate_passcode("elder")
    caretaker_code = generate_passcode("caretaker")
    family_code = generate_passcode("family")

    profile = Profile(
        care_id=care_id,
        elder_name=payload.elder_name,
        elder_age=payload.elder_age,
        emergency_notes=payload.emergency_notes,
        elder_passcode_hash=hash_passcode(elder_code),
        caretaker_passcode_hash=hash_passcode(caretaker_code),
        family_passcode_hash=hash_passcode(family_code),
        caretaker_access_enabled=True,
        family_access_enabled=True,
        elder_email=payload.elder_email,
        caretaker_email=payload.caretaker_email,
        family_email=payload.family_email,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return {
        "id": profile.id,
        "care_id": profile.care_id,
        "elder_name": profile.elder_name,
        "passcodes": {
            "elder": elder_code,
            "caretaker": caretaker_code,
            "family": family_code,
        },
    }


@router.post("/api/login")
def api_login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """API endpoint to login with care_id and passcode."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    clean_care_id = payload.care_id.strip().upper()
    clean_passcode = payload.passcode.strip().upper()

    is_limited, retry_after = auth_rate_limiter.is_rate_limited(client_ip, clean_care_id)
    if is_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Please wait {retry_after} seconds.",
        )

    profile = db.query(Profile).filter(Profile.care_id == clean_care_id).first()
    if not profile:
        auth_rate_limiter.record_failure(client_ip, clean_care_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    matched_role = None
    if verify_passcode(clean_passcode, profile.elder_passcode_hash):
        matched_role = "elder"
    elif verify_passcode(clean_passcode, profile.caretaker_passcode_hash):
        if not profile.caretaker_access_enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Caretaker access is disabled.")
        matched_role = "caretaker"
    elif verify_passcode(clean_passcode, profile.family_passcode_hash):
        if not profile.family_access_enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Family access is disabled.")
        matched_role = "family"

    if not matched_role:
        auth_rate_limiter.record_failure(client_ip, clean_care_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid passcode.")

    auth_rate_limiter.record_success(client_ip, clean_care_id)
    token = create_session_token({
        "profile_id": profile.id,
        "care_id": profile.care_id,
        "elder_name": profile.elder_name,
        "role": matched_role,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": matched_role,
        "care_id": profile.care_id,
        "elder_name": profile.elder_name,
    }
