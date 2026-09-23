"""App factory for the CycloAI API.

Import-safety contract: calling :func:`create_app` — and importing this
module — opens NO database connection, reads NO API key, and makes NO network
call. Every collaborator (engine, model client, embedder) is built lazily at
request time inside the dependencies, so tests can import and build the app
with nothing configured.
"""

from __future__ import annotations

from fastapi import FastAPI

from cycloai.api.routes_auth import router as auth_router
from cycloai.api.routes_conversations import router as conversations_router
from cycloai.api.routes_generate import router as generate_router
from cycloai.api.routes_profile import router as profile_router

__all__ = ["create_app"]


def create_app() -> FastAPI:
    """Build the FastAPI application with the auth, generation,
    conversation/message and profile/onboarding routers."""
    app = FastAPI(
        title="CycloAI API",
        description="Cycling workout generation with validated, athlete-owned plans.",
        version="0.1.0",
    )
    app.include_router(auth_router)
    app.include_router(generate_router)
    app.include_router(profile_router)
    app.include_router(conversations_router)
    return app
