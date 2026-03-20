# gigshield/backend/app/models/zone.py

from sqlalchemy import Column, String, Numeric, Boolean, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class Zone(Base):
    __tablename__ = "zones"

    zone_id     = Column(String(10), primary_key=True)  # e.g. BLR-01
    name        = Column(String(100), nullable=False)
    city        = Column(String(50), default="Bengaluru")
    centroid_lat = Column(Numeric(9, 6), nullable=False)
    centroid_lng = Column(Numeric(9, 6), nullable=False)
    radius_km   = Column(Numeric(4, 2), default=2.5)
    risk_tier   = Column(String(10))                    # LOW | MEDIUM | HIGH

    # {"dry":1.0, "pre_monsoon":1.6, "monsoon":2.5, "post_monsoon":1.3}
    seasonal_disruption_days = Column(JSON, nullable=False)

    is_active   = Column(Boolean, default=True)

    # Relationships
    workers           = relationship("Worker", back_populates="zone")
    policies          = relationship("Policy", back_populates="zone")
    signal_readings   = relationship("SignalReading", back_populates="zone")
    disruption_events = relationship("DisruptionEvent", back_populates="zone")
    zdi_snapshots     = relationship("ZDISnapshot", back_populates="zone")