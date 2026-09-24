"""ASGI entry point for the CycloAI API.

Run with::

    uvicorn cycloai.main:app

Importing this module builds the app but opens no database connection, reads
no API key, and makes no network call (see ``cycloai.api.app``).
"""

from __future__ import annotations

from cycloai.api.app import create_app

__all__ = ["app"]

app = create_app()


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    import uvicorn

    uvicorn.run("cycloai.main:app", host="127.0.0.1", port=8000)
