# gigshield/backend/app/engine/disruption_manager.py

from datetime import datetime
from sqlalchemy.orm import Session
from app.models.disruption_event import DisruptionEvent
from app.engine.zdi_scorer import ZDIResult


def open_disruption(db: Session, result: ZDIResult) -> DisruptionEvent:
    """
    Called when ZDI crosses 25 for the first time for a zone.
    Creates a new DisruptionEvent row and returns it.
    """
    event = DisruptionEvent(
        zone_id=result.zone_id,
        started_at=result.snapshot_at,
        peak_zdi=result.zdi_score,
        peak_level=result.disruption_level,
        is_active=True,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def update_disruption(
    db: Session,
    event: DisruptionEvent,
    result: ZDIResult,
) -> DisruptionEvent:
    """
    Called on every ZDI tick while a disruption is active.
    Updates peak values if the new score is higher.
    """
    if result.zdi_score > (event.peak_zdi or 0):
        event.peak_zdi   = result.zdi_score
        event.peak_level = result.disruption_level
        db.commit()
        db.refresh(event)
    return event


def close_disruption(
    db: Session,
    event: DisruptionEvent,
    ended_at: datetime,
) -> DisruptionEvent:
    """
    Called when ZDI drops below 25 after an active disruption.
    Computes affected_hours and closes the event.
    Affected hours is what the claims engine uses for prorated payout.
    """
    started: datetime = event.started_at
    duration_seconds  = (ended_at - started).total_seconds()
    affected_hours    = round(duration_seconds / 3600, 2)

    event.ended_at       = ended_at
    event.affected_hours = affected_hours
    event.is_active      = False

    db.commit()
    db.refresh(event)
    return event


def get_active_disruption(
    db: Session,
    zone_id: str,
) -> DisruptionEvent | None:
    """
    Returns the currently open disruption for a zone, or None.
    """
    return (
        db.query(DisruptionEvent)
        .filter(
            DisruptionEvent.zone_id  == zone_id,
            DisruptionEvent.is_active == True,
        )
        .first()
    )