"""FastAPI dependencies for authentication, role enforcement, and session management."""

from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import SESSION_COOKIE_NAME
from app.database import get_db
from app.models import Profile
from app.security import decode_session_token


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any] | None:
    """Retrieve the authenticated user session from cookie or Authorization header, if present.

    Args:
        request (Request): The incoming FastAPI request.
        db (Session): Database session.

    Returns:
        Optional[Dict[str, Any]]: User session dictionary if valid and active, None otherwise.
    """
    token: str | None = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        auth_header: str | None = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    if not token:
        return None

    payload: dict[str, Any] | None = decode_session_token(token)
    if not payload:
        return None

    profile_id: int | None = payload.get("profile_id")
    role: str | None = payload.get("role")
    if not profile_id or not role:
        return None

    profile: Profile | None = db.query(Profile).filter(Profile.id == profile_id).first()
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
    current_user: dict[str, Any] | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Require an authenticated user; redirects HTML requests to login or raises HTTP 401.

    Args:
        request (Request): The incoming FastAPI request.
        current_user (Optional[Dict[str, Any]]): Result of get_current_user_optional dependency.

    Returns:
        Dict[str, Any]: The active user session dictionary.

    Raises:
        HTTPException: 307 Temporary Redirect for browser requests, 401 Unauthorized for API clients.
    """
    if not current_user:
        accept: str = request.headers.get("accept", "")
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
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Require Elder or Caretaker role. Family members have view-only access.

    Args:
        current_user (Dict[str, Any]): Active authenticated user session.

    Returns:
        Dict[str, Any]: Verified editor user session dictionary.

    Raises:
        HTTPException: 403 Forbidden if user is a Family member.
    """
    if current_user["role"] not in ("elder", "caretaker"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Family members have view-only access. Only the Elder or Caretaker can edit records.",
        )
    return current_user


def require_elder(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Require Elder role for primary access management and passcode configuration.

    Args:
        current_user (Dict[str, Any]): Active authenticated user session.

    Returns:
        Dict[str, Any]: Verified primary elder user session dictionary.

    Raises:
        HTTPException: 403 Forbidden if caller is not the primary elder.
    """
    if current_user["role"] != "elder":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access management is reserved exclusively for the Elder.",
        )
    return current_user
