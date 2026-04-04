# gigshield/backend/app/engine/payout_service.py

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.payout import Payout
from app.interfaces.payment_gateway import PaymentGateway
from app.services.audit_service import write_audit
from app.services.wallet_service import apply_wallet_entry


def process_payout(
    db: Session,
    claim: Claim,
    gateway: PaymentGateway,
) -> Payout:
    """
    Credits payout into worker wallet (internal settlement).
    Keeps existing payout + claim state transitions for backward compatibility.
    """
    _ = gateway  # kept for backward-compatible function signature

    now = datetime.now(timezone.utc)
    amount = Decimal(str(claim.final_payout_inr)).quantize(Decimal("0.01"))

    wallet, ledger_entry, created = apply_wallet_entry(
        db=db,
        worker_id=claim.worker_id,
        amount=amount,
        entry_type="payout",
        reference_id=claim.claim_id,
    )

    payout = (
        db.query(Payout)
        .filter(Payout.claim_id == claim.claim_id, Payout.method == "WALLET_INTERNAL")
        .first()
    )
    if not payout:
        payout = Payout(
            claim_id=claim.claim_id,
            worker_id=claim.worker_id,
            amount_inr=amount,
            method="WALLET_INTERNAL",
            gateway_ref=f"WALLET_LEDGER_{ledger_entry.id[:8].upper()}",
            is_mocked=True,
            status="SETTLED",
            initiated_at=now,
            settled_at=now,
        )
        db.add(payout)

    claim.status = "PAID"
    claim.paid_at = claim.paid_at or now
    claim.processed_at = now

    db.commit()
    db.refresh(payout)

    write_audit(
        db=db,
        event_type="PAYOUT_INITIATED",
        entity_type="Payout",
        entity_id=payout.payout_id,
        zone_id=claim.zone_id,
        payload={
            "claim_id": claim.claim_id,
            "worker_id": claim.worker_id,
            "amount_inr": float(amount),
            "wallet_id": wallet.id,
            "ledger_entry_id": ledger_entry.id,
            "wallet_balance_after": float(wallet.balance),
            "idempotent_replay": not created,
            "method": "WALLET_INTERNAL",
        },
    )

    return payout
