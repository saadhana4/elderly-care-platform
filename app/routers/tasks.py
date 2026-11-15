"""Automated tasks and scheduler endpoints for reminder dispatch."""

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user_optional
from app.services.reminder_service import process_all_reminders

router: APIRouter = APIRouter()


def _extract_scheduler_token(x_scheduler_token: str | None, authorization: str | None) -> str | None:
    """Extract raw scheduler token from either custom or bearer header.

    Args:
        x_scheduler_token (Optional[str]): Header token if set.
        authorization (Optional[str]): Authorization header value.

    Returns:
        Optional[str]: Extracted token or None.
    """
    if x_scheduler_token:
        return x_scheduler_token
    if authorization:
        if authorization.startswith("Bearer "):
            return authorization.split(" ", 1)[1]
        return authorization
    return None


def _authorize_task_request(request: Request, db: Session, token: str | None) -> None:
    """Validate that caller is an authenticated editor or provided valid scheduler token.

    Args:
        request (Request): The incoming request.
        db (Session): Database session.
        token (Optional[str]): Extracted secret token.

    Raises:
        HTTPException: 401 if unauthorized.
    """
    current_user: dict[str, Any] | None = get_current_user_optional(request, db)
    if current_user and current_user["role"] in ("elder", "caretaker"):
        return

    expected = settings.SCHEDULER_SECRET_TOKEN
    if not token or not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Missing or invalid scheduler token.",
        )

    if not hmac.compare_digest(token.strip(), expected.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid scheduler secret token.",
        )


@router.post("/tasks/send-reminders", response_class=Response)
def trigger_send_reminders(
    request: Request,
    x_scheduler_token: str | None = Header(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> Response:
    """Trigger automated email alert scan for missed doses, upcoming doses, and appointments.

    Args:
        request (Request): The incoming HTTP request.
        x_scheduler_token (Optional[str]): Secret header token.
        authorization (Optional[str]): Authorization header with Bearer token.
        db (Session): Database session.

    Returns:
        Response: JSON audit report or browser redirect.
    """
    token: str | None = _extract_scheduler_token(x_scheduler_token, authorization)
    _authorize_task_request(request, db, token)

    report = process_all_reminders(db)

    accept: str = request.headers.get("accept", "")
    if "text/html" in accept:
        alerts = report["total_alerts_found"]
        sent = report["total_emails_sent"]
        return RedirectResponse(
            url=f"/today?msg=Reminders+checked:+{alerts}+alerts+found,+{sent}+emails+dispatched",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "success",
            "message": "Reminder scan completed successfully.",
            "report": report,
        },
    )
