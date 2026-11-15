"""CareNest - Elderly Care & Medication Management Platform.

Main FastAPI Application Entrypoint.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Union

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import settings
from app.database import init_db
from app.routers import (
    appointments,
    auth,
    dashboard,
    medications,
    tasks,
)
from app.routers import (
    settings as settings_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown events.

    Args:
        app (FastAPI): The application instance.
    """
    init_db()
    yield


app: FastAPI = FastAPI(
    title=settings.APP_NAME,
    description="A smart, interconnected platform for elderly medication management and family collaboration.",
    version="1.0.0",
    lifespan=lifespan,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing secure browser HTTP headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process incoming request and apply OWASP-recommended security headers.

        Args:
            request (Request): Incoming HTTP request.
            call_next (RequestResponseEndpoint): Next middleware or route endpoint.

        Returns:
            Response: Response with attached security headers.
        """
        response: Response = await call_next(request)
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

# Static Assets Mount
BASE_DIR: Path = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Include Application Routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(medications.router)
app.include_router(appointments.router)
app.include_router(settings_router.router)
app.include_router(tasks.router)


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Liveness & readiness probe for container management.

    Returns:
        Dict[str, str]: Health status and environment details.
    """
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
    }


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: Exception) -> Union[RedirectResponse, JSONResponse]:
    """Handle 404 Not Found errors gracefully based on request accept headers.

    Args:
        request (Request): The failed request.
        exc (Exception): The raised 404 exception.

    Returns:
        Union[RedirectResponse, JSONResponse]: HTML redirect or JSON error detail.
    """
    accept: str = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url="/today?msg=Page+not+found", status_code=status.HTTP_303_SEE_OTHER)
    return JSONResponse(status_code=404, content={"detail": "Resource not found"})
