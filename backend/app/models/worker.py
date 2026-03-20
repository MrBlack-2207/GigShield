# gigshield/backend/app/models/worker.py

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class Worker(Base):
    __tablename__ = "workers"

    worker_id    = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name    = Column(String(100), nullable=False)
    phone        = Column(String(15), unique=True, nullable=False)
    aadhaar_hash = Column(String(64), unique=True)      # SHA-256, never raw

    primary_zone_id = Column(String(10), ForeignKey("zones.zone_id"), nullable=False)

    # 400 | 600 | 800 — declared daily income tier in INR
    income_tier  = Column(Integer, nullable=False)

    platform     = Column(String(20))                   # ZEPTO | BLINKIT | BOTH
    kyc_status   = Column(String(10), default="PENDING") # PENDING | VERIFIED
    is_active    = Column(Boolean, default=True)

    # Relationships
    zone     = relationship("Zone", back_populates="workers")
    policies = relationship("Policy", back_populates="worker")
    claims   = relationship("Claim", back_populates="worker")
    payouts  = relationship("Payout", back_populates="worker")