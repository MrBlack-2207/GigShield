# gigshield/backend/app/services/worker_service.py

import hashlib
from sqlalchemy.orm import Session
from app.models.worker import Worker
from app.services.audit_service import write_audit


def register_worker(
    db:          Session,
    full_name:   str,
    phone:       str,
    income_tier: int,
    zone_id:     str,
    platform:    str,
    aadhaar:     str | None = None,
) -> Worker:
    """
    Registers a new gig worker.
    Aadhaar is hashed immediately — raw value is never persisted.
    """
    existing = db.query(Worker).filter(Worker.phone == phone).first()
    if existing:
        raise ValueError(f"Worker with phone {phone} already exists.")

    aadhaar_hash = None
    if aadhaar:
        aadhaar_hash = hashlib.sha256(aadhaar.encode()).hexdigest()

    worker = Worker(
        full_name=full_name,
        phone=phone,
        income_tier=income_tier,
        primary_zone_id=zone_id,
        platform=platform,
        aadhaar_hash=aadhaar_hash,
        kyc_status="PENDING",
        is_active=True,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)

    write_audit(
        db=db,
        event_type="WORKER_REGISTERED",
        entity_type="Worker",
        entity_id=worker.worker_id,
        zone_id=zone_id,
        payload={
            "full_name":   full_name,
            "income_tier": income_tier,
            "platform":    platform,
        },
    )
    return worker


def get_worker_by_id(db: Session, worker_id: str) -> Worker | None:
    return db.query(Worker).filter(Worker.worker_id == worker_id).first()


def get_worker_by_phone(db: Session, phone: str) -> Worker | None:
    return db.query(Worker).filter(Worker.phone == phone).first()