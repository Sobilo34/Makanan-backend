import time
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api.v1 import (
    auth,
    plans,
    meals,
    payments,
    redemptions,
    students,
    partners,
    admin,
    support,
    notifications,
    waitlist,
)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("makanan")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: auto-create tables & seed initial meal plans
    await init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware (Restricted to configured origins, local dev ports, and production cloud previews)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"^https?://.*(localhost|127\.0\.0\.1|vercel\.app|onrender\.com|makanan\.app|pxxlspace\.cv)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def security_and_tracing_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start_time = time.time()

    # Process request
    response: Response = await call_next(request)

    duration_ms = (time.time() - start_time) * 1000

    # Attach security headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    logger.info(
        f"[{request_id}] {request.method} {request.url.path} -> {response.status_code} ({duration_ms:.1f}ms)"
    )

    return response


# Root discovery endpoint
@app.get("/", status_code=status.HTTP_200_OK)
async def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "api_v1": "/api/v1",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


# API v1 Index endpoint
@app.get("/api/v1", status_code=status.HTTP_200_OK)
@app.get("/api/v1/", status_code=status.HTTP_200_OK)
async def api_v1_root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "endpoints": {
            "health": "/api/v1/health",
            "docs": "/docs",
            "plans": "/api/v1/plans",
            "meals": "/api/v1/meals",
            "auth": "/api/v1/auth",
            "payments": "/api/v1/payments",
            "students": "/api/v1/students",
            "partners": "/api/v1/partners",
            "admin": "/api/v1/admin",
        },
    }


# Mount API v1 Routers
api_v1_prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=api_v1_prefix)
app.include_router(plans.router, prefix=api_v1_prefix)
app.include_router(meals.router, prefix=api_v1_prefix)
app.include_router(payments.router, prefix=api_v1_prefix)
app.include_router(redemptions.router, prefix=api_v1_prefix)
app.include_router(students.router, prefix=api_v1_prefix)
app.include_router(partners.router, prefix=api_v1_prefix)
app.include_router(admin.router, prefix=api_v1_prefix)
app.include_router(support.router, prefix=api_v1_prefix)
app.include_router(notifications.router, prefix=api_v1_prefix)
app.include_router(waitlist.router, prefix=api_v1_prefix)


@app.get("/api/v1/health", status_code=status.HTTP_200_OK)
async def healthcheck():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "payment_mode": settings.PAYMENT_MODE,
    }
