# gigshield/backend/app/services/audit_service.py

from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def write_audit(
    db:           Session,
    event_type:   str,
    entity_type:  str  = None,
    entity_id:    str  = None,
    zone_id:      str  = None,
    payload:      dict = None,
    model_version: str = None,
    is_mocked:    bool = False,
) -> AuditLog:
    """
    Append-only audit log writer.
    Call this after every significant system event.
    Never raises — audit failure must never crash the pipeline.
    """
    try:
        entry = AuditLog(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            zone_id=zone_id,
            payload=payload or {},
            model_version=model_version or "zdi_scorer_v1.0",
            is_mocked=is_mocked,
        )
        db.add(entry)
        db.commit()
        return entry
    except Exception as e:
        print(f"[AuditService] WARNING: Failed to write audit log: {e}")
        db.rollback()