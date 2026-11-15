"""Automated tasks and Cloud Scheduler endpoints."""

import hmac
from typing import Optional
from fastapi import APIRouter, Header, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.services.reminder_service import process_all_reminders
from app.dependencies import get_current_user_optional, require_editor

router = APIRouter()


@router.post("/tasks/send-reminders")
def trigger_send_reminders(
    request: Request,
    x_scheduler_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Cloud Scheduler endpoint for automated email alerts.
    
    Protected by secret header token (X-Scheduler-Token or Bearer Authorization).
    Dispatches notifications for missed doses, upcoming doses, and medical appointments.
    """
    token = x_scheduler_token
    if not token and authorization:
        if authorization.startswith("Bearer "):
            token = authorization.split(" ", 1)[1]
        else:
            token = authorization

    # Also allow authenticated logged-in elder/caretaker to trigger a test reminder
    current_user = get_current_user_optional(request, db)
    is_authenticated_editor = current_user and current_user["role"] in ("elder", "caretaker")

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

    # If triggered from web browser by logged in user, redirect with notice
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(
            url=f"/today?msg=Reminders+checked:+{report['total_alerts_found']}+alerts+found,+{report['total_emails_sent']}+emails+dispatched",
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
