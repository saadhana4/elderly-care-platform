"""CareNest - Elderly Care & Medication Management Platform.

Main FastAPI Application Entrypoint.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db
from app.routers import (
    auth,
    dashboard,
    medications,
    appointments,
    settings as settings_router,
    tasks,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown events."""
    # Initialize SQLite database schema
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="A smart, interconnected platform for elderly medication management and family collaboration.",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self';"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ---------------------------------------------------------------------------
# Static Assets Mount
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ---------------------------------------------------------------------------
# Include Application Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(medications.router)
app.include_router(appointments.router)
app.include_router(settings_router.router)
app.include_router(tasks.router)


# ---------------------------------------------------------------------------
# Health Check Endpoint (Google Cloud Run ready)
# ---------------------------------------------------------------------------
@app.get("/health", tags=["System"])
def health_check():
    """Liveness & readiness probe for Cloud Run container management."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
    }


# ---------------------------------------------------------------------------
# Custom Exception Handlers
# ---------------------------------------------------------------------------
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url="/today?msg=Page+not+found", status_code=status.HTTP_303_SEE_OTHER)
    return JSONResponse(status_code=404, content={"detail": "Resource not found"})
