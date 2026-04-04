import uuid

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class DarkStore(Base):
    __tablename__ = "dark_stores"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(120), nullable=False)
    platform = Column(String(20), nullable=False)  # zepto | blinkit
    zone_id = Column(String(10), ForeignKey("zones.zone_id"), nullable=False)
    location = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    zone = relationship("Zone", back_populates="dark_stores")
    workers = relationship("Worker", back_populates="home_store")
