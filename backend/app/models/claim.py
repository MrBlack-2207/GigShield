# gigshield/backend/app/models/claim.py

from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Claim(Base):
    __tablename__ = "claims"

    claim_id    = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id   = Column(String(36), ForeignKey("policies.policy_id"), nullable=False)
    worker_id   = Column(String(36), ForeignKey("workers.worker_id"), nullable=False)
    disruption_event_id = Column(String(36), ForeignKey("disruption_events.event_id"), nullable=False)
    zone_id     = Column(String(10), nullable=False)

    disruption_level = Column(String(10), nullable=False)
    payout_pct       = Column(Integer, nullable=False)   # 25 | 50 | 75 | 100

    affected_hours   = Column(Numeric(5, 2), nullable=False)
    working_hours    = Column(Numeric(5, 2), default=10.0)

    # payout_pct × (affected_hours / working_hours) × income_tier × coverage_ratio
    gross_payout_inr = Column(Numeric(8, 2), nullable=False)
    cap_applied      = Column(Boolean, default=False)
    final_payout_inr = Column(Numeric(8, 2), nullable=False)  # after weekly cap

    fraud_score      = Column(Numeric(5, 4))             # 0.0000 – 1.0000
    fraud_flag       = Column(Boolean, default=False)

    status           = Column(String(15), default="PENDING")
    # PENDING | APPROVED | PAID | REJECTED | FLAGGED

    triggered_at  = Column(DateTime(timezone=True), server_default=func.now())
    processed_at  = Column(DateTime(timezone=True))
    paid_at       = Column(DateTime(timezone=True))

    # Relationships
    policy           = relationship("Policy", back_populates="claims")
    worker           = relationship("Worker", back_populates="claims")
    disruption_event = relationship("DisruptionEvent", back_populates="claims")
    payout           = relationship("Payout", back_populates="claim", uselist=False)