# gigshield/backend/app/models/disruption_event.py

from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class DisruptionEvent(Base):
    __tablename__ = "disruption_events"

    event_id    = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    zone_id     = Column(String(10), ForeignKey("zones.zone_id"), nullable=False)

    started_at  = Column(DateTime(timezone=True), nullable=False)
    ended_at    = Column(DateTime(timezone=True))       # NULL = still active

    peak_zdi    = Column(Integer)
    peak_level  = Column(String(10))
    # NONE | MILD | MODERATE | SEVERE | EXTREME

    affected_hours = Column(Numeric(5, 2))              # computed on event close
    is_active      = Column(Boolean, default=True)

    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    zone   = relationship("Zone", back_populates="disruption_events")
    claims = relationship("Claim", back_populates="disruption_event")