# gigshield/backend/app/models/signal_reading.py

from sqlalchemy import Column, String, Numeric, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class SignalReading(Base):
    __tablename__ = "signal_readings"

    reading_id      = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    zone_id         = Column(String(10), ForeignKey("zones.zone_id"), nullable=False)

    signal_type     = Column(String(30), nullable=False)
    # RAINFALL | PLATFORM_OUTAGE | TRAFFIC | AQI

    raw_value       = Column(Numeric(10, 4), nullable=False)
    # rainfall mm/hr | outage 0/1 | traffic speed% | AQI index

    normalized_score = Column(Integer, nullable=False)
    # 0–100, computed by the signal adapter

    source_id       = Column(String(50), nullable=False)
    # e.g. "mock_weather_v1" | "openweathermap_v3"

    is_mocked       = Column(Boolean, default=True)
    recorded_at     = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    zone = relationship("Zone", back_populates="signal_readings")


class ZDISnapshot(Base):
    __tablename__ = "zdi_snapshots"

    snapshot_id      = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    zone_id          = Column(String(10), ForeignKey("zones.zone_id"), nullable=False)

    zdi_score        = Column(Integer, nullable=False)   # 0–100
    disruption_level = Column(String(10), nullable=False)
    # NONE | MILD | MODERATE | SEVERE | EXTREME

    payout_pct       = Column(Integer, nullable=False)   # 0|25|50|75|100

    # Individual weighted component scores (for transparency + audit)
    rain_component    = Column(Integer)
    outage_component  = Column(Integer)
    traffic_component = Column(Integer)
    aqi_component     = Column(Integer)

    snapshot_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    zone = relationship("Zone", back_populates="zdi_snapshots")