# gigshield/backend/app/models/policy.py

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint("tenure_months IN (1, 3, 6, 12)", name="ck_policies_tenure_months"),
        CheckConstraint("billing_cycle = 'weekly'", name="ck_policies_billing_cycle_weekly"),
        CheckConstraint(
            "status IN ('pending_activation', 'active', 'inactive', 'expired', 'cancelled')",
            name="ck_policies_status_lifecycle",
        ),
    )

    policy_id   = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    worker_id   = Column(String(36), ForeignKey("workers.worker_id"), nullable=False)
    zone_id     = Column(String(10), ForeignKey("zones.zone_id"), nullable=False)

    income_tier         = Column(Integer, nullable=False)   # 400 | 600 | 800
    weekly_premium_inr  = Column(Numeric(8, 2), nullable=False)
    coverage_ratio      = Column(Numeric(4, 2), default=0.30)
    weekly_payout_cap   = Column(Numeric(8, 2), nullable=False)
    # = coverage_ratio × income_tier

    season_at_purchase  = Column(String(15), nullable=False)
    # dry | pre_monsoon | monsoon | post_monsoon

    tenure_months = Column(Integer, nullable=False, default=1)
    start_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    end_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    billing_cycle = Column(String(20), nullable=False, default="weekly")
    last_premium_paid_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    next_premium_due_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    cooldown_ends_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Legacy fields retained for backward compatibility.
    week_start  = Column(Date, nullable=False)
    week_end    = Column(Date, nullable=False)

    status      = Column(String(25), default="pending_activation", nullable=False)
    # pending_activation | active | inactive | expired | cancelled

    # Legacy compatibility field. New eligibility uses cooldown_ends_at.
    lookback_exclusion_until = Column(DateTime(timezone=True))

    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    worker  = relationship("Worker", back_populates="policies")
    zone    = relationship("Zone", back_populates="policies")
    claims  = relationship("Claim", back_populates="policy")
