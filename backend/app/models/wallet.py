import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    worker_id = Column(String(36), ForeignKey("workers.worker_id"), nullable=False, unique=True)
    balance = Column(Numeric(12, 2), nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    worker = relationship("Worker", back_populates="wallet")
    ledger_entries = relationship("WalletLedgerEntry", back_populates="wallet")
    withdrawals = relationship("WithdrawalRequest", back_populates="wallet")
