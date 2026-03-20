# gigshield/backend/app/models/payout.py

from sqlalchemy import Column, String, Numeric, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Payout(Base):
    __tablename__ = "payouts"

    payout_id   = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id    = Column(String(36), ForeignKey("claims.claim_id"), nullable=False)
    worker_id   = Column(String(36), ForeignKey("workers.worker_id"), nullable=False)

    amount_inr  = Column(Numeric(8, 2), nullable=False)
    method      = Column(String(20), default="UPI_MOCK")
    gateway_ref = Column(String(100))
    # Razorpay ref in production | "MOCK_TXN_XXXXX" in demo

    is_mocked   = Column(Boolean, default=True)

    status      = Column(String(15), default="INITIATED")
    # INITIATED | SETTLED | FAILED

    initiated_at = Column(DateTime(timezone=True), server_default=func.now())
    settled_at   = Column(DateTime(timezone=True))

    # Relationships
    claim  = relationship("Claim", back_populates="payout")
    worker = relationship("Worker", back_populates="payouts")