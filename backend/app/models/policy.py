# gigshield/backend/app/models/policy.py

from sqlalchemy import Column, String, Integer, Numeric, Date, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Policy(Base):
    __tablename__ = "policies"

    policy_id   = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    worker_id   = Column(String(36), ForeignKey("workers.worker_id"), nullable=False)
    zone_id     = Column(String(10), ForeignKey("zones.zone_id"), nullable=False)

    income_tier         = Column(Integer, nullable=False)   # 400 | 600 | 800
    weekly_premium_inr  = Column(Numeric(8, 2), nullable=False)
    coverage_ratio      = Column(Numeric(4, 2), default=0.80)
    weekly_payout_cap   = Column(Numeric(8, 2), nullable=False)
    # = coverage_ratio × income_tier × 5

    season_at_purchase  = Column(String(15), nullable=False)
    # dry | pre_monsoon | monsoon | post_monsoon

    week_start  = Column(Date, nullable=False)
    week_end    = Column(Date, nullable=False)

    status      = Column(String(15), default="ACTIVE")
    # ACTIVE | EXPIRED | CANCELLED | SUSPENDED

    # 48-hour lookback exclusion window from policy activation
    lookback_exclusion_until = Column(DateTime(timezone=True))

    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    worker  = relationship("Worker", back_populates="policies")
    zone    = relationship("Zone", back_populates="policies")
    claims  = relationship("Claim", back_populates="policy")