"""DisputeIQ FastAPI application entrypoint."""

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import disputes, health, meta
from app.core.config import get_settings
from app.core.logging import configure_logging


def _bootstrap_in_background() -> None:
    """Fill an empty database with demo data without blocking startup (the port opens at once)."""

    def work() -> None:
        try:
            from data_gen.bootstrap import ensure_demo_data

            ensure_demo_data()
        except Exception:
            logging.getLogger(__name__).exception("demo data bootstrap failed")

    threading.Thread(target=work, name="demo-bootstrap", daemon=True).start()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if get_settings().bootstrap_demo_data:
        _bootstrap_in_background()
    yield


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title="DisputeIQ",
        description="AI dispute resolution agent for card issuers.",
        version="0.5.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(disputes.router)
    app.include_router(meta.router)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).exception("unhandled error")
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    return app


app = create_app()
