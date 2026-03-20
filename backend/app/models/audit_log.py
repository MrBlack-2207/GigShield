# gigshield/backend/app/models/audit_log.py

from sqlalchemy import Column, String, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import uuid


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id      = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    event_type  = Column(String(50), nullable=False)
    # ZDI_COMPUTED | DISRUPTION_OPENED | DISRUPTION_CLOSED
    # CLAIM_TRIGGERED | FRAUD_CHECK | PAYOUT_INITIATED
    # POLICY_CREATED | WORKER_REGISTERED

    entity_type = Column(String(30))   # Zone | Worker | Policy | Claim | Payout
    entity_id   = Column(String(36))   # UUID of the entity involved
    zone_id     = Column(String(10))

    payload     = Column(JSON)         # full snapshot of event data at time of logging
    model_version = Column(String(20)) # e.g. "zdi_scorer_v1.0"
    is_mocked   = Column(Boolean, default=False)

    logged_at   = Column(DateTime(timezone=True), server_default=func.now())