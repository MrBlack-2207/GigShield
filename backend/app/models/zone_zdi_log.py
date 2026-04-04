import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ZoneZDILog(Base):
    __tablename__ = "zone_zdi_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    zone_id = Column(String(10), ForeignKey("zones.zone_id"), nullable=False)
    zdi_value = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    zone = relationship("Zone", back_populates="zdi_logs")

    __table_args__ = (
        Index("ix_zone_zdi_logs_timestamp", "timestamp"),
    )
