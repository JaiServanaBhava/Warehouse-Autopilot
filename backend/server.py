"""Warehouse Autopilot — FastAPI main."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from dotenv import load_dotenv
import os
import logging
import sys

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT.parent / "frontend" / "public"

# ALWAYS load app/backend/.env
ENV_FILE = ROOT / ".env"
load_dotenv(ENV_FILE, override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# Make project root importable
PROJECT_ROOT = ROOT.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.backend.db import init_db
from app.backend.seed import seed_demo
from app.backend.routers import (
    products,
    orders,
    ops,
    misc,
    chat,
    notifications,
)

print("======================================")
print("WAREHOUSE AUTOPILOT")
print("ENV FILE:", ENV_FILE)
print("ENV EXISTS:", ENV_FILE.exists())
print("GEMINI KEY LOADED:", bool(os.getenv("GEMINI_API_KEY")))
print("GEMINI MODEL:", os.getenv("GEMINI_MODEL"))
print("======================================")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_demo()
    yield


app = FastAPI(
    title="Warehouse Autopilot",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(products.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(ops.router, prefix="/api")
app.include_router(misc.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/app.js")
def app_js():
    return FileResponse(FRONTEND_DIR / "app.js")


@app.get("/style.css")
def style_css():
    return FileResponse(FRONTEND_DIR / "style.css")


@app.get("/api")
def root():
    return {
        "name": "Warehouse Autopilot",
        "status": "ok",
    }