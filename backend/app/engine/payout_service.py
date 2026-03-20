# gigshield/backend/app/engine/payout_service.py

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.claim  import Claim
from app.models.payout import Payout
from app.interfaces.payment_gateway import PaymentGateway
from app.services.audit_service import write_audit


def process_payout(
    db:      Session,
    claim:   Claim,
    gateway: PaymentGateway,
) -> Payout:
    """
    Initiates a payout for an APPROVED claim via the payment gateway.
    Updates claim status to PAID or REJECTED based on gateway result.
    Writes to audit log regardless of outcome.
    """
    result = gateway.disburse(
        worker_id=claim.worker_id,
        claim_id=claim.claim_id,
        amount_inr=float(claim.final_payout_inr),
        reference=f"GIGSHIELD_{claim.claim_id[:8].upper()}",
    )

    payout = Payout(
        claim_id=claim.claim_id,
        worker_id=claim.worker_id,
        amount_inr=claim.final_payout_inr,
        method=result.method,
        gateway_ref=result.gateway_ref,
        is_mocked=result.is_mocked,
        status="SETTLED" if result.success else "FAILED",
        initiated_at=result.initiated_at,
        settled_at=datetime.now(timezone.utc) if result.success else None,
    )
    db.add(payout)

    claim.status   = "PAID" if result.success else "REJECTED"
    claim.paid_at  = datetime.now(timezone.utc) if result.success else None
    claim.processed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(payout)

    write_audit(
        db=db,
        event_type="PAYOUT_INITIATED",
        entity_type="Payout",
        entity_id=payout.payout_id,
        zone_id=claim.zone_id,
        payload={
            "claim_id":    claim.claim_id,
            "worker_id":   claim.worker_id,
            "amount_inr":  float(claim.final_payout_inr),
            "gateway_ref": result.gateway_ref,
            "success":     result.success,
            "is_mocked":   result.is_mocked,
        },
    )

    return payout