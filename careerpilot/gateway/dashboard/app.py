"""
Run with:
    uvicorn careerpilot.gateway.dashboard.app:app --reload --port 7777
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from careerpilot.gateway.dashboard import runtime_settings, conversations_store
from careerpilot.memory.episodic.sqlite_store import init_db as init_episodic_db
from careerpilot.gateway.dashboard.routers import (
    applications,
    chat,
    conversations,
    memory,
    settings as settings_router,
    skills,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime_settings.load_overlay()
    init_episodic_db()
    conversations_store.init_db()
    yield


app = FastAPI(title="CareerPilot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": str(exc.detail)},
    )


@app.exception_handler(Exception)
def _handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(applications.router)
app.include_router(memory.router)
app.include_router(settings_router.router)
app.include_router(skills.router)


@app.get("/health")
def health() -> dict:
    return {"success": True, "status": "ok"}
