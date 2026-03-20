# gigshield/backend/app/scheduler/jobs.py

from apscheduler.schedulers.background import BackgroundScheduler
from app.config import get_settings

settings  = get_settings()
_scheduler = BackgroundScheduler()


def run_signal_ingestion():
    """
    Full pipeline — runs every SCHEDULER_INTERVAL_MINUTES:
    1. Fetch all 4 signals for every zone
    2. Compute ZDI
    3. Persist ZDI snapshot
    4. Open / update / close disruption events
    5. Trigger claims on disruption close
    6. Run fraud checks
    7. Process approved payouts
    """
    from app.database           import SessionLocal
    from app.models.zone        import Zone
    from app.models.signal_reading import SignalReading as SignalReadingModel, ZDISnapshot
    from app.adapters           import (
        get_weather_adapter, get_traffic_adapter,
        get_aqi_adapter,     get_outage_adapter,
        get_payment_gateway,
    )
    from app.engine import (
        compute_zdi,
        open_disruption, update_disruption,
        close_disruption, get_active_disruption,
        trigger_claims_for_event,
        run_fraud_checks,
        process_payout,
    )
    from app.services.audit_service import write_audit
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        zones = db.query(Zone).filter(Zone.is_active == True).all()

        adapters = [
            get_weather_adapter(),
            get_traffic_adapter(),
            get_aqi_adapter(),
            get_outage_adapter(),
        ]
        gateway = get_payment_gateway()

        for zone in zones:
            # ── 1. Fetch all signals ──────────────────────────────────────
            readings = [adapter.fetch(zone.zone_id) for adapter in adapters]

            # ── 2. Persist raw signal readings ────────────────────────────
            for r in readings:
                db.add(SignalReadingModel(
                    zone_id=r.zone_id,
                    signal_type=r.signal_type,
                    raw_value=r.raw_value,
                    normalized_score=r.normalized_score,
                    source_id=r.source_id,
                    is_mocked=r.is_mocked,
                    recorded_at=r.recorded_at,
                ))

            # ── 3. Compute ZDI ────────────────────────────────────────────
            result = compute_zdi(zone.zone_id, readings)

            db.add(ZDISnapshot(
                zone_id=result.zone_id,
                zdi_score=result.zdi_score,
                disruption_level=result.disruption_level,
                payout_pct=result.payout_pct,
                rain_component=result.rain_component,
                outage_component=result.outage_component,
                traffic_component=result.traffic_component,
                aqi_component=result.aqi_component,
                snapshot_at=result.snapshot_at,
            ))
            db.commit()

            write_audit(db, "ZDI_COMPUTED", "Zone", zone.zone_id,
                        zone_id=zone.zone_id,
                        payload={"zdi": result.zdi_score, "level": result.disruption_level},
                        is_mocked=True)

            # ── 4. Disruption lifecycle ───────────────────────────────────
            active_event = get_active_disruption(db, zone.zone_id)

            if result.is_disruption and not active_event:
                active_event = open_disruption(db, result)
                write_audit(db, "DISRUPTION_OPENED", "Zone", zone.zone_id,
                            zone_id=zone.zone_id,
                            payload={"zdi": result.zdi_score, "event_id": active_event.event_id})

            elif result.is_disruption and active_event:
                update_disruption(db, active_event, result)

            elif not result.is_disruption and active_event:
                closed_event = close_disruption(
                    db, active_event, datetime.now(timezone.utc)
                )
                write_audit(db, "DISRUPTION_CLOSED", "Zone", zone.zone_id,
                            zone_id=zone.zone_id,
                            payload={
                                "event_id":      closed_event.event_id,
                                "affected_hours": float(closed_event.affected_hours or 0),
                                "peak_zdi":      closed_event.peak_zdi,
                            })

                # ── 5. Trigger claims ─────────────────────────────────────
                claims = trigger_claims_for_event(db, closed_event)
                write_audit(db, "CLAIMS_TRIGGERED", "Zone", zone.zone_id,
                            zone_id=zone.zone_id,
                            payload={"claim_count": len(claims)})

                for claim in claims:
                    # ── 6. Fraud check ────────────────────────────────────
                    fraud_score, fraud_flag = run_fraud_checks(db, claim)
                    claim.fraud_score = fraud_score
                    claim.fraud_flag  = fraud_flag
                    claim.status      = "FLAGGED" if fraud_flag else "APPROVED"
                    db.commit()

                    write_audit(db, "FRAUD_CHECK", "Claim", claim.claim_id,
                                zone_id=zone.zone_id,
                                payload={"fraud_score": fraud_score, "flagged": fraud_flag})

                    if not fraud_flag:
                        # ── 7. Process payout ─────────────────────────────
                        process_payout(db, claim, gateway)

    except Exception as e:
        print(f"[Scheduler] ERROR during signal ingestion: {e}")
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    _scheduler.add_job(
        run_signal_ingestion,
        trigger="interval",
        minutes=settings.SCHEDULER_INTERVAL_MINUTES,
        id="signal_ingestion",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"[Scheduler] Started. Interval: {settings.SCHEDULER_INTERVAL_MINUTES} min.")


def stop_scheduler():
    _scheduler.shutdown(wait=False)
    print("[Scheduler] Stopped.")