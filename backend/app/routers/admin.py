# gigshield/backend/app/routers/admin.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
import redis as redis_lib

from app.config   import get_settings
from app.database import get_db
from app.models.audit_log import AuditLog

router   = APIRouter()
settings = get_settings()


class OutageToggleRequest(BaseModel):
    zone_id:  str
    active:   bool   # True = outage ON, False = outage OFF


@router.post("/outage/toggle")
def toggle_outage(body: OutageToggleRequest):
    """
    Admin demo control — sets or clears the outage Redis flag for a zone.
    The OutageToggleAdapter reads this flag every 15 minutes.
    In production this endpoint is replaced by a StatusPage webhook receiver.
    """
    r = redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    key = f"outage:{body.zone_id}"

    if body.active:
        r.set(key, "1")
        return {"status": "outage_activated", "zone_id": body.zone_id}
    else:
        r.delete(key)
        return {"status": "outage_cleared", "zone_id": body.zone_id}


@router.get("/outage/status")
def outage_status():
    """Returns active outage flags across all zones."""
    r = redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    keys = r.keys("outage:*")
    active_zones = [k.replace("outage:", "") for k in keys if r.get(k) == "1"]
    return {"active_outages": active_zones}


@router.get("/audit", response_model=list[dict])
def recent_audit(limit: int = 50, db: Session = Depends(get_db)):
    """Last N audit log entries — used by the admin dashboard."""
    rows = (
        db.query(AuditLog)
        .order_by(AuditLog.logged_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "log_id":      r.log_id,
            "event_type":  r.event_type,
            "entity_type": r.entity_type,
            "entity_id":   r.entity_id,
            "zone_id":     r.zone_id,
            "payload":     r.payload,
            "logged_at":   r.logged_at.isoformat(),
        }
        for r in rows
    ]
