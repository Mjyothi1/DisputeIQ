"""Health endpoint."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness plus database reachability."""

    status: Literal["ok", "degraded"]
    database: Literal["up", "down"]


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Return ``ok`` when the API and database are reachable, ``degraded`` otherwise."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("health check: database unreachable")
        return HealthResponse(status="degraded", database="down")
    return HealthResponse(status="ok", database="up")
