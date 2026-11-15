"""FastAPI dependencies for authentication, role enforcement, and session management."""

from typing import Optional, Dict, Any
from fastapi import Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile
from app.security import decode_session_token


SESSION_COOKIE_NAME = "carenest_session"


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[Dict[str, Any]]:
    """Retrieve the authenticated user session from cookie or Authorization header, if any."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        # Also check Authorization header for API testing
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    if not token:
        return None

    payload = decode_session_token(token)
    if not payload:
        return None

    profile_id = payload.get("profile_id")
    role = payload.get("role")
    if not profile_id or not role:
        return None

    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return None

    # Check elder access permissions for non-elder roles
    if role == "caretaker" and not profile.caretaker_access_enabled:
        return None
    if role == "family" and not profile.family_access_enabled:
        return None

    return {
        "profile_id": profile.id,
        "care_id": profile.care_id,
        "elder_name": profile.elder_name,
        "role": role,
        "profile": profile,
    }


def get_current_user(
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    """Require an authenticated user. Redirects to /login for HTML requests or raises 401."""
    if not current_user:
        # If client accepts text/html, redirect to login page
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Location": "/login?error=Please+sign+in+with+your+passcode"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in with your passcode.",
        )
    return current_user


def require_editor(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Require Elder or Caretaker role. Family members are view-only."""
    if current_user["role"] not in ("elder", "caretaker"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Family members have view-only access. Only the Elder or Caretaker can edit records.",
        )
    return current_user


def require_elder(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Require Elder role for master profile management."""
    if current_user["role"] != "elder":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access management is reserved exclusively for the Elder.",
        )
    return current_user
