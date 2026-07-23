import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


REQUEST_COUNTS: dict[str, list[float]] = {}
RATE_LIMIT = 60
RATE_WINDOW = 60


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.scope.get("type") == "websocket":
            return await call_next(request)
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if "text/html" in (response.headers.get("content-type", "")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https: https://accounts.google.com https://apis.google.com; "
                "style-src 'self' 'unsafe-inline' https:; "
                "img-src 'self' data: blob: https:; "
                "font-src 'self' data: https:; "
                "connect-src 'self' https: wss: https://accounts.google.com https://api.github.com; "
                "media-src 'self' blob: data: https:; "
                "frame-src 'self' https://accounts.google.com https://github.com; "
                "object-src 'none'; "
                "base-uri 'self'"
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if "/api" not in request.url.path:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = time.time()
        timestamps = REQUEST_COUNTS.get(client, [])
        timestamps = [t for t in timestamps if now - t < RATE_WINDOW]
        if len(timestamps) >= RATE_LIMIT:
            return Response(status_code=429, content='{"error":"rate_limit","retry_after":60}', media_type="application/json")
        timestamps.append(now)
        REQUEST_COUNTS[client] = timestamps
        return await call_next(request)
