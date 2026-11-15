"""CareNest - Elderly Care & Medication Management Platform.

Main FastAPI Application Entrypoint.
"""

import hmac
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Union

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    logger,
    settings,
    validate_production_secrets,
)
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
from app.security import generate_csrf_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown events.

    Args:
        app (FastAPI): The application instance.
    """
    validate_production_secrets()
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
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response


def _is_untrusted_cross_origin(origin: str | None, host: str | None) -> bool:
    """Check if origin header indicates an untrusted cross-origin request.

    Args:
        origin (Optional[str]): Incoming Origin header.
        host (Optional[str]): Incoming Host header.

    Returns:
        bool: True if origin is untrusted cross-origin.
    """
    if not origin or not host:
        return False
    origin_host = origin.split("://")[-1].rstrip("/")
    host_clean = host.rstrip("/")
    is_local = (
        origin_host.startswith("localhost")
        or origin_host.startswith("127.0.0.1")
        or origin_host == "testserver"
    )
    return origin_host != host_clean and not is_local


def _is_invalid_submitted_token(submitted: str | None, cookie_token: str | None) -> bool:
    """Check if explicit CSRF header token is provided but does not match cookie.

    Args:
        submitted (Optional[str]): Header token submitted by client.
        cookie_token (Optional[str]): Token stored in client cookie.

    Returns:
        bool: True if submitted token failed validation.
    """
    if not submitted:
        return False
    if not cookie_token:
        return True
    return not hmac.compare_digest(submitted.strip(), cookie_token.strip())


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing Cross-Site Request Forgery (CSRF) protections for state changes."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Validate origin and CSRF tokens on state-changing requests.

        Args:
            request (Request): Incoming HTTP request.
            call_next (RequestResponseEndpoint): Next middleware or route endpoint.

        Returns:
            Response: Response from downstream route or 403 Forbidden.
        """
        cookie_csrf: str | None = request.cookies.get(CSRF_COOKIE_NAME)
        csrf_token: str = cookie_csrf or generate_csrf_token()
        request.state.csrf_token = csrf_token

        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.headers.get("sec-fetch-site") == "cross-site":
                logger.warning("CSRF blocked: cross-site fetch detected on %s", request.url.path)
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Forbidden: Cross-site request rejected."},
                )

            if _is_untrusted_cross_origin(request.headers.get("origin"), request.headers.get("host")):
                logger.warning("CSRF blocked: untrusted origin on %s", request.url.path)
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Forbidden: Untrusted cross-origin request rejected."},
                )

            hdr = request.headers.get(CSRF_HEADER_NAME.lower()) or request.headers.get(CSRF_HEADER_NAME)
            if _is_invalid_submitted_token(hdr, cookie_csrf):
                logger.warning("CSRF blocked: invalid token submitted on %s", request.url.path)
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Forbidden: Invalid CSRF token."},
                )

        response: Response = await call_next(request)
        if not cookie_csrf:
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=csrf_token,
                httponly=False,
                samesite="lax",
                secure=settings.ENVIRONMENT.lower() == "production",
                max_age=86400 * 7,
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFProtectionMiddleware)

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


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> Response:
    """Catch-all generic exception handler to avoid leaking internal stack traces or details.

    Args:
        request (Request): The incoming request that failed.
        exc (Exception): The uncaught exception.

    Returns:
        Response: Generic JSON or redirected error response without internal details.
    """
    if isinstance(exc, HTTPException):
        # Allow standard HTTPExceptions to propagate to FastAPI default handler
        raise exc

    logger.error(
        "Internal unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True
    )
    accept: str = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(
            url="/today?msg=An+unexpected+error+occurred.+Please+try+again.",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."},
    )
