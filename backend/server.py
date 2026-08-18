"""Warehouse Autopilot — FastAPI main."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from dotenv import load_dotenv
import os
import logging
import sys
import time

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT.parent / "frontend" / "public"

# Load backend/.env
ENV_FILE = ROOT / ".env"
load_dotenv(ENV_FILE, override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# Make repo root importable
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db import init_db
from backend.seed import seed_demo
from backend.routers import (
    products,
    orders,
    ops,
    misc,
    chat,
    notifications,
)

logger.info(
    "Warehouse Autopilot starting — ENV: %s | exists=%s | GEMINI=%s",
    ENV_FILE, ENV_FILE.exists(), bool(os.getenv("GEMINI_API_KEY"))
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialise DB and seed demo data on startup."""
    init_db()
    seed_demo()
    yield


app = FastAPI(
    title="Warehouse Autopilot",
    description="Autonomous AI warehouse operations & supply chain command center.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "*").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)


# ── SECURITY HEADERS MIDDLEWARE ─────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Attach security headers to every HTTP response."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = round((time.perf_counter() - start) * 1000, 1)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Response-Time"] = f"{elapsed}ms"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self'"
    )
    return response


# ── GLOBAL ERROR HANDLER ────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Return structured JSON errors — never expose raw tracebacks in production."""
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method, request.url.path, exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "path": request.url.path},
    )


# ── ROUTERS ─────────────────────────────────────────────────────────────────────
app.include_router(products.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(ops.router, prefix="/api")
app.include_router(misc.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")


# ── STATIC FRONTEND ─────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def index():
    """Serve the Glassmorphism SPA frontend."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/app.js", include_in_schema=False)
def app_js():
    """Serve the frontend application script."""
    return FileResponse(FRONTEND_DIR / "app.js")


@app.get("/style.css", include_in_schema=False)
def style_css():
    """Serve the frontend stylesheet."""
    return FileResponse(FRONTEND_DIR / "style.css")


@app.get("/skip-link.css", include_in_schema=False)
def skip_link_css():
    """Serve the accessibility skip-link stylesheet."""
    return FileResponse(FRONTEND_DIR / "skip-link.css")


@app.get("/api")
def api_root():
    """Health check / API root."""
    return {
        "name": "Warehouse Autopilot",
        "version": "1.0.0",
        "status": "ok",
        "docs": "/api/docs",
    }
