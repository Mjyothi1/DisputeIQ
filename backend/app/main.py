"""DisputeIQ FastAPI application entrypoint."""

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import disputes, health, meta, portal
from app.core.config import get_settings
from app.core.logging import configure_logging


def _bootstrap_in_background() -> None:
    """Fill an empty database with demo data without blocking startup (the port opens at once)."""

    def work() -> None:
        try:
            from data_gen.bootstrap import run_startup_bootstrap

            run_startup_bootstrap()
        except Exception:
            logging.getLogger(__name__).exception("demo data bootstrap failed")

    threading.Thread(target=work, name="demo-bootstrap", daemon=True).start()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.bootstrap_demo_data or settings.bootstrap_demo_customers:
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
        allow_headers=["Authorization", "Content-Type"],
    )
    @app.middleware("http")
    async def limit_body(request: Request, call_next):  # type: ignore[no-untyped-def]
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_request_bytes:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return await call_next(request)

    app.include_router(health.router)
    app.include_router(disputes.router)
    app.include_router(meta.router)
    app.include_router(portal.router)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).exception("unhandled error")
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    return app


app = create_app()
