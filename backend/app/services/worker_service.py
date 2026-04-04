# gigshield/backend/app/services/worker_service.py

import hashlib
from sqlalchemy.orm import Session
from app.constants.platforms import normalize_platform
from app.models.dark_store import DarkStore
from app.models.worker import Worker
from app.services.audit_service import write_audit


def register_worker(
    db: Session,
    full_name: str,
    phone: str,
    income_tier: int,
    zone_id: str | None,
    platform: str,
    home_store_id: str | None = None,
    external_worker_id: str | None = None,
    aadhaar: str | None = None,
) -> Worker:
    """
    Registers a new gig worker.
    Aadhaar is hashed immediately — raw value is never persisted.
    """
    existing = db.query(Worker).filter(Worker.phone == phone).first()
    if existing:
        raise ValueError(f"Worker with phone {phone} already exists.")

    normalized_platform = normalize_platform(platform)
    if not normalized_platform:
        raise ValueError("platform must be one of: zepto, blinkit")

    external_id = external_worker_id.strip() if external_worker_id else None

    if external_id:
        existing_external_id = (
            db.query(Worker)
            .filter(
                Worker.platform == normalized_platform,
                Worker.external_worker_id == external_id,
            )
            .first()
        )
        if existing_external_id:
            raise ValueError(
                f"external_worker_id {external_id} already exists for platform {normalized_platform}."
            )

    if not zone_id and not home_store_id:
        raise ValueError("Either zone_id or home_store_id is required.")

    home_store: DarkStore | None = None
    resolved_zone_id: str | None = None

    if home_store_id:
        home_store = (
            db.query(DarkStore)
            .filter(DarkStore.id == home_store_id)
            .first()
        )
        if not home_store:
            raise ValueError(f"Dark store {home_store_id} not found.")
        if home_store.platform != normalized_platform:
            raise ValueError("worker.platform must match home_store.platform")
        if zone_id and home_store.zone_id != zone_id:
            raise ValueError("home_store_id does not belong to provided zone_id")
        resolved_zone_id = home_store.zone_id
    else:
        home_store = (
            db.query(DarkStore)
            .filter(
                DarkStore.zone_id == zone_id,
                DarkStore.platform == normalized_platform,
            )
            .first()
        )
        if not home_store:
            raise ValueError(
                f"No dark store found for zone {zone_id} and platform {normalized_platform}."
            )
        resolved_zone_id = zone_id

    if not resolved_zone_id:
        raise ValueError("Unable to resolve worker zone from zone_id/home_store_id")

    aadhaar_hash = None
    if aadhaar:
        aadhaar_hash = hashlib.sha256(aadhaar.encode()).hexdigest()

    worker = Worker(
        full_name=full_name,
        phone=phone,
        income_tier=income_tier,
        primary_zone_id=resolved_zone_id,
        platform=normalized_platform,
        external_worker_id=external_id,
        home_store_id=home_store.id,
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
        zone_id=resolved_zone_id,
        payload={
            "full_name":   full_name,
            "income_tier": income_tier,
            "platform":    normalized_platform,
            "home_store_id": home_store.id,
        },
    )
    return worker


def get_worker_by_id(db: Session, worker_id: str) -> Worker | None:
    return db.query(Worker).filter(Worker.worker_id == worker_id).first()


def get_worker_by_phone(db: Session, phone: str) -> Worker | None:
    return db.query(Worker).filter(Worker.phone == phone).first()
