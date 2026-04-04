import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class WalletLedgerEntry(Base):
    __tablename__ = "wallet_ledger_entries"
    __table_args__ = (
        CheckConstraint(
            "type IN ('payout', 'withdrawal', 'premium', 'adjustment')",
            name="ck_wallet_ledger_entries_type",
        ),
        CheckConstraint(
            "(type = 'adjustment') OR (reference_id IS NOT NULL)",
            name="ck_wallet_ledger_entries_reference_required",
        ),
        UniqueConstraint(
            "wallet_id",
            "type",
            "reference_id",
            name="uq_wallet_ledger_wallet_type_reference",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    wallet_id = Column(String(36), ForeignKey("wallets.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    type = Column(String(20), nullable=False)
    reference_id = Column(String(36))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    wallet = relationship("Wallet", back_populates="ledger_entries")
