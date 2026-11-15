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


@router.post("/tasks/send-reminders", response_class=Response)
def trigger_send_reminders(
    request: Request,
    x_scheduler_token: str | None = Header(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> Response:
    """Trigger automated email alert scan for missed doses, upcoming doses, and appointments.

    Protected by secret token via X-Scheduler-Token or Authorization Bearer header.
    Also accessible by authenticated editors (Elder or Caretaker) directly from UI.

    Args:
        request (Request): The incoming HTTP request.
        x_scheduler_token (Optional[str]): Secret header token.
        authorization (Optional[str]): Authorization header with Bearer token.
        db (Session): Database session.

    Returns:
        Union[JSONResponse, RedirectResponse]: JSON audit report or browser redirect.

    Raises:
        HTTPException: 401 if scheduler token is missing or invalid.
    """
    token: str | None = x_scheduler_token
    if not token and authorization:
        if authorization.startswith("Bearer "):
            token = authorization.split(" ", 1)[1]
        else:
            token = authorization

    current_user: dict[str, Any] | None = get_current_user_optional(request, db)
    is_authenticated_editor: bool = bool(current_user and current_user["role"] in ("elder", "caretaker"))

    if not is_authenticated_editor:
        if not token or not settings.SCHEDULER_SECRET_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Missing or invalid scheduler token.",
            )

        if not hmac.compare_digest(token.strip(), settings.SCHEDULER_SECRET_TOKEN.strip()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Invalid scheduler secret token.",
            )

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
