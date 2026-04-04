from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
import redis as redis_lib
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.adapters import get_payment_gateway
from app.config import get_settings
from app.database import get_db
from app.engine.claims_engine import trigger_claims_for_event
from app.engine.disruption_manager import close_disruption, get_active_disruption
from app.engine.fraud_checker import run_fraud_checks
from app.engine.payout_service import process_payout
from app.engine.premium_calculator import calculate_premium, get_current_season
from app.models.audit_log import AuditLog
from app.models.claim import Claim
from app.models.dark_store import DarkStore
from app.models.disruption_event import DisruptionEvent
from app.models.policy import Policy
from app.models.wallet_ledger_entry import WalletLedgerEntry
from app.models.worker import Worker
from app.models.zone import Zone
from app.models.zone_zdi_log import ZoneZDILog
from app.scheduler.jobs import run_signal_ingestion
from app.schemas.contract import (
    ClaimTimelineItemOut,
    ClaimsTimelineOut,
    DemoActivatePolicyOut,
    DemoClaimsRunOut,
    DemoClaimsRunRequest,
    DemoTriggerFireOut,
    DemoTriggerFireRequest,
    PolicyPurchaseRequest,
    PolicyQuoteOut,
    PolicyQuoteRequest,
    StoreOut,
    WalletLedgerEntryMiniOut,
    WorkerCashoutOut,
    WorkerDashboardOut,
    WorkerPolicyEnvelope,
    WorkerPolicyOut,
    WorkerRegisterOut,
    WorkerWalletOut,
    ZDITransparencyOut,
)
from app.schemas.worker import WorkerRegisterRequest
from app.services import (
    create_policy,
    derive_effective_policy_status,
    get_worker_by_id,
    is_policy_payout_eligible,
    predict_disruption_frequency_days,
    register_worker,
    sync_policy_status_in_flow,
)
from app.services.audit_service import write_audit
from app.services.wallet_service import cash_out_wallet, get_wallet_for_worker
from app.constants.platforms import normalize_platform

router = APIRouter()
settings = get_settings()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value, default: float | None = 0.0) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _require_worker(db: Session, worker_id: str) -> Worker:
    worker = get_worker_by_id(db, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker


def _latest_policy(db: Session, worker_id: str) -> Policy | None:
    return (
        db.query(Policy)
        .filter(Policy.worker_id == worker_id)
        .order_by(Policy.created_at.desc())
        .first()
    )


def _policy_to_out(policy: Policy | None, now: datetime | None = None) -> WorkerPolicyOut | None:
    if not policy:
        return None
    now_utc = now or _now_utc()
    effective_status = derive_effective_policy_status(policy, now_utc)
    payout_eligible_now = is_policy_payout_eligible(policy, now_utc)
    return WorkerPolicyOut(
        policy_id=policy.policy_id,
        worker_id=policy.worker_id,
        zone_id=policy.zone_id,
        tenure_months=int(policy.tenure_months),
        status=str(policy.status),
        effective_status=effective_status,
        billing_cycle=str(policy.billing_cycle),
        weekly_premium_inr=_safe_float(policy.weekly_premium_inr),
        weekly_payout_cap_inr=_safe_float(policy.weekly_payout_cap),
        start_date=policy.start_date,
        end_date=policy.end_date,
        cooldown_ends_at=policy.cooldown_ends_at,
        next_premium_due_at=policy.next_premium_due_at,
        payout_eligible_now=payout_eligible_now,
    )


def _latest_zdi_transparency(
    db: Session,
    zone_id: str,
    at_or_before: datetime | None = None,
) -> ZDITransparencyOut | None:
    query = db.query(AuditLog).filter(
        AuditLog.event_type == "ZDI_COMPUTED",
        AuditLog.zone_id == zone_id,
    )
    if at_or_before is not None:
        query = query.filter(AuditLog.logged_at <= at_or_before)
    row = query.order_by(AuditLog.logged_at.desc()).first()
    if not row:
        return None
    payload = row.payload or {}
    return ZDITransparencyOut(
        base_zdi=_safe_float(payload.get("base_zdi"), default=None),
        event_boost_total=_safe_float(payload.get("event_boost_total"), default=None),
        final_zdi=_safe_float(payload.get("final_zdi"), default=None),
        timestamp=row.logged_at,
    )


def _build_claim_timeline_items(db: Session, claims: list[Claim]) -> list[ClaimTimelineItemOut]:
    if not claims:
        return []

    claim_ids = [c.claim_id for c in claims]
    event_ids = sorted({c.disruption_event_id for c in claims if c.disruption_event_id})

    credited_rows = (
        db.query(WalletLedgerEntry.reference_id)
        .filter(
            WalletLedgerEntry.type == "payout",
            WalletLedgerEntry.reference_id.in_(claim_ids),
        )
        .all()
    )
    credited_claim_ids = {r[0] for r in credited_rows if r and r[0]}

    event_audit_map: dict[tuple[str, str], dict] = {}
    if event_ids:
        event_audits = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "DisruptionEvent",
                AuditLog.entity_id.in_(event_ids),
                AuditLog.event_type.in_(["AFFECTED_HOURS_SELECTED", "PAYOUT_RATE_SELECTED"]),
            )
            .order_by(AuditLog.logged_at.desc())
            .all()
        )
        for row in event_audits:
            key = (row.entity_id, row.event_type)
            if key not in event_audit_map:
                event_audit_map[key] = row.payload or {}

    items: list[ClaimTimelineItemOut] = []
    for claim in claims:
        affected_payload = event_audit_map.get((claim.disruption_event_id, "AFFECTED_HOURS_SELECTED"), {})
        payout_payload = event_audit_map.get((claim.disruption_event_id, "PAYOUT_RATE_SELECTED"), {})
        zdi = _latest_zdi_transparency(db, claim.zone_id, claim.triggered_at)

        payout_rate_default = _safe_float(claim.payout_pct, 0.0) / 100.0
        affected_hours_used = _safe_float(affected_payload.get("affected_hours_used"), _safe_float(claim.affected_hours))
        payout_rate_used = _safe_float(payout_payload.get("payout_rate_used"), payout_rate_default)

        items.append(
            ClaimTimelineItemOut(
                claim_id=claim.claim_id,
                policy_id=claim.policy_id,
                disruption_event_id=claim.disruption_event_id,
                zone_id=claim.zone_id,
                status=claim.status,
                triggered_at=claim.triggered_at,
                paid_at=claim.paid_at,
                base_zdi=zdi.base_zdi if zdi else None,
                event_boost_total=zdi.event_boost_total if zdi else None,
                final_zdi=zdi.final_zdi if zdi else None,
                affected_hours_used=affected_hours_used,
                affected_hours_source=str(affected_payload.get("affected_hours_source") or "fallback_zdi_logs"),
                payout_rate_used=payout_rate_used,
                payout_rate_source=str(payout_payload.get("payout_rate_source") or "fallback_zdi_ladder"),
                payout_amount=_safe_float(claim.final_payout_inr),
                wallet_credited=claim.claim_id in credited_claim_ids,
            )
        )
    return items


def _ensure_demo_mode() -> None:
    env = (settings.APP_ENV or "").strip().lower()
    if env in {"production", "prod"}:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/stores", response_model=list[StoreOut])
def list_stores(
    platform: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    normalized_platform = None
    if platform:
        normalized_platform = normalize_platform(platform)
        if not normalized_platform:
            raise HTTPException(status_code=400, detail="platform must be zepto or blinkit")

    query = (
        db.query(DarkStore, Zone)
        .join(Zone, Zone.zone_id == DarkStore.zone_id)
    )
    if normalized_platform:
        query = query.filter(DarkStore.platform == normalized_platform)

    rows = query.order_by(DarkStore.zone_id.asc(), DarkStore.name.asc()).all()
    return [
        StoreOut(
            id=store.id,
            name=store.name,
            platform=store.platform,
            zone_id=store.zone_id,
            zone_name=zone.name,
            location=store.location,
        )
        for store, zone in rows
    ]


@router.post("/workers", response_model=WorkerRegisterOut, status_code=201)
def register_worker_contract(
    body: WorkerRegisterRequest,
    db: Session = Depends(get_db),
):
    try:
        worker = register_worker(
            db=db,
            full_name=body.full_name,
            phone=body.phone,
            income_tier=body.income_tier,
            zone_id=body.zone_id,
            platform=body.platform,
            home_store_id=body.home_store_id,
            external_worker_id=body.external_worker_id,
            aadhaar=body.aadhaar,
        )
        return WorkerRegisterOut(
            worker_id=worker.worker_id,
            full_name=worker.full_name,
            phone=worker.phone,
            income_tier=int(worker.income_tier),
            primary_zone_id=worker.primary_zone_id,
            platform=worker.platform,
            external_worker_id=worker.external_worker_id,
            home_store_id=worker.home_store_id,
            kyc_status=worker.kyc_status,
            is_active=bool(worker.is_active),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/policies/quote", response_model=PolicyQuoteOut)
def quote_policy(
    body: PolicyQuoteRequest,
    db: Session = Depends(get_db),
):
    worker = _require_worker(db, body.worker_id)
    zone_id = body.zone_id or worker.primary_zone_id
    season = body.season or get_current_season()
    now = _now_utc()

    freq_result = predict_disruption_frequency_days(db=db, zone_id=zone_id, at_time=now)
    breakdown = calculate_premium(
        worker.income_tier,
        season,
        seasonal_disruption_days_override=freq_result.seasonal_disruption_days,
        disruption_days_source=freq_result.source,
    )

    return PolicyQuoteOut(
        worker_id=worker.worker_id,
        zone_id=zone_id,
        tenure_months=body.tenure_months,
        billing_cycle="weekly",
        first_weekly_premium_at_purchase=True,
        cooldown_hours=48,
        season=breakdown.season,
        weekly_premium_inr=breakdown.weekly_premium_inr,
        weekly_payout_cap_inr=breakdown.weekly_payout_cap_inr,
        coverage_ratio=breakdown.coverage_ratio,
        expected_weekly_loss=breakdown.expected_weekly_loss,
        seasonal_disruption_days=breakdown.seasonal_disruption_days,
        disruption_days_source=breakdown.disruption_days_source,
    )


@router.post("/policies/purchase", response_model=WorkerPolicyOut, status_code=201)
def purchase_policy_contract(
    body: PolicyPurchaseRequest,
    db: Session = Depends(get_db),
):
    worker = _require_worker(db, body.worker_id)
    zone_id = body.zone_id or worker.primary_zone_id
    try:
        policy = create_policy(
            db=db,
            worker_id=worker.worker_id,
            zone_id=zone_id,
            tenure_months=body.tenure_months,
        )
        return _policy_to_out(policy, _now_utc())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/workers/{worker_id}/policy", response_model=WorkerPolicyEnvelope)
def get_worker_policy(
    worker_id: str,
    db: Session = Depends(get_db),
):
    _require_worker(db, worker_id)
    policy = _latest_policy(db, worker_id)
    return WorkerPolicyEnvelope(
        worker_id=worker_id,
        policy=_policy_to_out(policy, _now_utc()),
    )


@router.get("/workers/{worker_id}/claims", response_model=ClaimsTimelineOut)
def get_worker_claims_timeline(
    worker_id: str,
    limit: int = Query(default=50, ge=1, le=300),
    db: Session = Depends(get_db),
):
    _require_worker(db, worker_id)
    claims = (
        db.query(Claim)
        .filter(Claim.worker_id == worker_id)
        .order_by(Claim.triggered_at.desc())
        .limit(limit)
        .all()
    )
    return ClaimsTimelineOut(
        worker_id=worker_id,
        items=_build_claim_timeline_items(db, claims),
    )


@router.get("/workers/{worker_id}/wallet", response_model=WorkerWalletOut)
def get_worker_wallet(
    worker_id: str,
    recent_limit: int = Query(default=10, ge=0, le=50),
    db: Session = Depends(get_db),
):
    _require_worker(db, worker_id)
    wallet = get_wallet_for_worker(db, worker_id)
    if not wallet:
        return WorkerWalletOut(
            worker_id=worker_id,
            wallet_id=None,
            wallet_balance_inr=0.0,
            updated_at=None,
            recent_entries=[],
        )

    recent_entries = (
        db.query(WalletLedgerEntry)
        .filter(WalletLedgerEntry.wallet_id == wallet.id)
        .order_by(WalletLedgerEntry.created_at.desc())
        .limit(recent_limit)
        .all()
    )
    return WorkerWalletOut(
        worker_id=worker_id,
        wallet_id=wallet.id,
        wallet_balance_inr=_safe_float(wallet.balance),
        updated_at=wallet.updated_at,
        recent_entries=[
            WalletLedgerEntryMiniOut(
                id=row.id,
                amount_inr=_safe_float(row.amount),
                entry_type=row.type,
                reference_id=row.reference_id,
                created_at=row.created_at,
            )
            for row in recent_entries
        ],
    )


@router.post("/workers/{worker_id}/wallet/cashout", response_model=WorkerCashoutOut)
def cashout_worker_wallet(
    worker_id: str,
    db: Session = Depends(get_db),
):
    _require_worker(db, worker_id)
    try:
        withdrawal, withdrawn_amount, remaining_balance = cash_out_wallet(db=db, worker_id=worker_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return WorkerCashoutOut(
        withdrawal_id=withdrawal.id,
        withdrawn_amount=_safe_float(withdrawn_amount),
        remaining_wallet_balance=_safe_float(remaining_balance),
        status=withdrawal.status,
    )


@router.get("/workers/{worker_id}/dashboard", response_model=WorkerDashboardOut)
def get_worker_dashboard(
    worker_id: str,
    db: Session = Depends(get_db),
):
    worker = _require_worker(db, worker_id)
    now = _now_utc()
    policy = _latest_policy(db, worker_id)
    wallet = get_wallet_for_worker(db, worker_id)

    claims_count = int(
        db.query(func.count(Claim.claim_id))
        .filter(Claim.worker_id == worker_id)
        .scalar()
        or 0
    )
    paid_claims_count = int(
        db.query(func.count(Claim.claim_id))
        .filter(Claim.worker_id == worker_id, Claim.status == "PAID")
        .scalar()
        or 0
    )
    total_payout_paid = _safe_float(
        db.query(func.coalesce(func.sum(Claim.final_payout_inr), 0))
        .filter(Claim.worker_id == worker_id, Claim.status == "PAID")
        .scalar()
    )
    recent_claims = (
        db.query(Claim)
        .filter(Claim.worker_id == worker_id)
        .order_by(Claim.triggered_at.desc())
        .limit(5)
        .all()
    )

    return WorkerDashboardOut(
        worker_id=worker.worker_id,
        full_name=worker.full_name,
        platform=worker.platform,
        home_store_id=worker.home_store_id,
        primary_zone_id=worker.primary_zone_id,
        policy=_policy_to_out(policy, now),
        wallet_balance_inr=_safe_float(wallet.balance) if wallet else 0.0,
        claims_count=claims_count,
        paid_claims_count=paid_claims_count,
        total_payout_paid_inr=total_payout_paid,
        latest_zdi=_latest_zdi_transparency(db, worker.primary_zone_id),
        recent_claims=_build_claim_timeline_items(db, recent_claims),
    )


@router.post("/demo/workers/{worker_id}/activate-policy", response_model=DemoActivatePolicyOut)
def demo_activate_policy(
    worker_id: str,
    db: Session = Depends(get_db),
):
    _ensure_demo_mode()
    _require_worker(db, worker_id)

    policy = _latest_policy(db, worker_id)
    if not policy:
        raise HTTPException(status_code=404, detail="No policy found for worker")

    now = _now_utc()
    previous_status = str(policy.status)

    if not policy.start_date or policy.start_date > now:
        policy.start_date = now
    if not policy.end_date or policy.end_date <= now:
        policy.end_date = now + timedelta(days=30)

    policy.cooldown_ends_at = now - timedelta(minutes=1)
    if not policy.next_premium_due_at or policy.next_premium_due_at <= now:
        policy.last_premium_paid_at = now
        policy.next_premium_due_at = now + timedelta(days=7)

    policy.status = "active"
    new_status = sync_policy_status_in_flow(db, policy, now)
    db.add(policy)
    db.commit()
    db.refresh(policy)

    write_audit(
        db=db,
        event_type="DEMO_POLICY_ACTIVATED",
        entity_type="Policy",
        entity_id=policy.policy_id,
        zone_id=policy.zone_id,
        payload={
            "worker_id": worker_id,
            "previous_status": previous_status,
            "new_status": new_status,
        },
        is_mocked=True,
    )

    return DemoActivatePolicyOut(
        worker_id=worker_id,
        policy_id=policy.policy_id,
        previous_status=previous_status,
        new_status=new_status,
        cooldown_ends_at=policy.cooldown_ends_at,
        next_premium_due_at=policy.next_premium_due_at,
    )


@router.post("/demo/triggers/fire", response_model=DemoTriggerFireOut)
def demo_fire_triggers(
    body: DemoTriggerFireRequest = DemoTriggerFireRequest(),
    db: Session = Depends(get_db),
):
    _ensure_demo_mode()
    created_claims_total = 0

    target_zone_id = body.zone_id
    if not target_zone_id and body.worker_id:
        worker = _require_worker(db, body.worker_id)
        target_zone_id = worker.primary_zone_id
    if body.scenario != "none" and not target_zone_id:
        raise HTTPException(status_code=400, detail="worker_id or zone_id required for selected scenario")

    redis_client = redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    outage_key = f"outage:{target_zone_id}" if target_zone_id else None

    # Minimal deterministic demo control: force outage flag for chosen zone.
    if outage_key and body.scenario == "outage_on":
        redis_client.set(outage_key, "1")
    elif outage_key and body.scenario == "outage_off":
        redis_client.delete(outage_key)
    elif outage_key and body.scenario == "outage_pulse":
        redis_client.set(outage_key, "1")

    for _ in range(body.cycles):
        run_signal_ingestion()

    if outage_key and body.scenario == "outage_pulse":
        redis_client.delete(outage_key)
        # Second tick with outage OFF to close the disruption window deterministically.
        run_signal_ingestion()

    # Demo determinism: for OFF/PULSE, ensure active event is closed so claims are created now.
    if target_zone_id and body.scenario in {"outage_off", "outage_pulse"}:
        active_event = get_active_disruption(db, target_zone_id)
        if active_event:
            closed_event = close_disruption(db, active_event, _now_utc())
            created_claims = trigger_claims_for_event(db, closed_event)
            created_claims_total += len(created_claims)
            write_audit(
                db=db,
                event_type="DEMO_CLAIMS_FORCED",
                entity_type="DisruptionEvent",
                entity_id=closed_event.event_id,
                zone_id=target_zone_id,
                payload={
                    "scenario": body.scenario,
                    "claims_created": len(created_claims),
                },
                is_mocked=True,
            )
        if created_claims_total == 0:
            # Hard fallback for demo videos: synthesize one short disruption window
            # so claims are always generated for eligible policies in the zone.
            now = _now_utc()
            high_zdi_ts = now - timedelta(minutes=15)
            db.add(
                ZoneZDILog(
                    zone_id=target_zone_id,
                    zdi_value=85.0,
                    timestamp=high_zdi_ts,
                )
            )
            db.add(
                ZoneZDILog(
                    zone_id=target_zone_id,
                    zdi_value=10.0,
                    timestamp=now,
                )
            )
            synthetic_event = DisruptionEvent(
                zone_id=target_zone_id,
                started_at=high_zdi_ts,
                ended_at=now,
                peak_zdi=85.0,
                peak_level="SEVERE",
                affected_hours=0.25,
                is_active=False,
            )
            db.add(synthetic_event)
            db.commit()
            db.refresh(synthetic_event)
            created_claims = trigger_claims_for_event(db, synthetic_event)
            created_claims_total += len(created_claims)
            write_audit(
                db=db,
                event_type="DEMO_SYNTHETIC_CLAIMS_FORCED",
                entity_type="DisruptionEvent",
                entity_id=synthetic_event.event_id,
                zone_id=target_zone_id,
                payload={
                    "scenario": body.scenario,
                    "claims_created": len(created_claims),
                    "reason": "no_claims_from_live_trigger",
                },
                is_mocked=True,
            )

    zdi_query = db.query(AuditLog).filter(AuditLog.event_type == "ZDI_COMPUTED")
    if target_zone_id:
        zdi_query = zdi_query.filter(AuditLog.zone_id == target_zone_id)
    zdi_row = zdi_query.order_by(AuditLog.logged_at.desc()).first()
    zdi_out = None
    if zdi_row:
        payload = zdi_row.payload or {}
        zdi_out = ZDITransparencyOut(
            base_zdi=_safe_float(payload.get("base_zdi"), default=None),
            event_boost_total=_safe_float(payload.get("event_boost_total"), default=None),
            final_zdi=_safe_float(payload.get("final_zdi"), default=None),
            timestamp=zdi_row.logged_at,
        )

    return DemoTriggerFireOut(
        status="ok",
        cycles=body.cycles,
        scenario=body.scenario,
        target_zone_id=target_zone_id,
        last_zdi=zdi_out,
    )


@router.post("/demo/claims/run", response_model=DemoClaimsRunOut)
def demo_run_claims(
    body: DemoClaimsRunRequest = DemoClaimsRunRequest(),
    db: Session = Depends(get_db),
):
    _ensure_demo_mode()

    query = (
        db.query(Claim)
        .filter(Claim.status.in_(["PENDING", "APPROVED"]))
        .order_by(Claim.triggered_at.asc())
    )
    if body.worker_id:
        query = query.filter(Claim.worker_id == body.worker_id)
    claims = query.limit(body.limit).all()

    gateway = get_payment_gateway()

    processed = 0
    approved = 0
    flagged = 0
    paid = 0

    for claim in claims:
        processed += 1
        should_pay = False
        flagged_for_demo = False

        if claim.status == "PENDING":
            if body.skip_fraud_checks:
                # Demo-only behavior: keep claim visibly flagged while still allowing payout.
                claim.fraud_score = 1.0
                claim.fraud_flag = True
                claim.status = "FLAGGED"
                flagged += 1
                flagged_for_demo = True
                db.commit()
                should_pay = True
            else:
                fraud_score, fraud_flag = run_fraud_checks(db, claim)
                claim.fraud_score = fraud_score
                claim.fraud_flag = fraud_flag
                if fraud_flag:
                    claim.status = "FLAGGED"
                    flagged += 1
                    db.commit()
                    continue

                claim.status = "APPROVED"
                approved += 1
                db.commit()
                should_pay = True

        elif claim.status == "APPROVED":
            should_pay = True

        if should_pay:
            process_payout(db, claim, gateway)
            paid += 1
            if flagged_for_demo:
                # Keep "FLAGGED" visible in claims timeline for demo narration.
                claim.status = "FLAGGED"
                db.add(claim)
                db.commit()

    return DemoClaimsRunOut(
        status="ok",
        processed=processed,
        approved=approved,
        flagged=flagged,
        paid=paid,
    )
