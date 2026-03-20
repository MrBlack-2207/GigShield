# gigshield/backend/app/services/zone_service.py

from sqlalchemy.orm import Session
from app.models.zone           import Zone
from app.models.signal_reading import ZDISnapshot
from app.models.disruption_event import DisruptionEvent


def get_all_zones(db: Session) -> list[Zone]:
    return db.query(Zone).filter(Zone.is_active == True).all()


def get_zone_by_id(db: Session, zone_id: str) -> Zone | None:
    return db.query(Zone).filter(Zone.zone_id == zone_id).first()


def get_latest_zdi(db: Session, zone_id: str) -> ZDISnapshot | None:
    return (
        db.query(ZDISnapshot)
        .filter(ZDISnapshot.zone_id == zone_id)
        .order_by(ZDISnapshot.snapshot_at.desc())
        .first()
    )


def get_all_latest_zdis(db: Session) -> list[ZDISnapshot]:
    """
    Returns the single most recent ZDI snapshot for every active zone.
    Used by the heatmap screen.
    """
    from sqlalchemy import func

    subq = (
        db.query(
            ZDISnapshot.zone_id,
            func.max(ZDISnapshot.snapshot_at).label("max_at"),
        )
        .group_by(ZDISnapshot.zone_id)
        .subquery()
    )

    return (
        db.query(ZDISnapshot)
        .join(subq, (ZDISnapshot.zone_id == subq.c.zone_id) &
                    (ZDISnapshot.snapshot_at == subq.c.max_at))
        .all()
    )


def get_active_disruption_for_zone(
    db: Session, zone_id: str
) -> DisruptionEvent | None:
    return (
        db.query(DisruptionEvent)
        .filter(
            DisruptionEvent.zone_id  == zone_id,
            DisruptionEvent.is_active == True,
        )
        .first()
    )
