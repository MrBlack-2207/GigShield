from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings

settings = get_settings()
_scheduler = BackgroundScheduler()


def _extract_severity_weight(source_id: str) -> float | None:
    try:
        marker = "|w="
        if marker not in source_id:
            return None
        return float(source_id.split(marker, 1)[1])
    except Exception:
        return None


def run_signal_ingestion():
    """
    Full pipeline - runs every SCHEDULER_INTERVAL_MINUTES:
    1. Fetch core signals + event flags for every zone
    2. Persist all signal readings
    3. Compute and persist ZDI snapshot/log
    4. Open / update / close disruption events
    5. Trigger claims on disruption close
    6. Run fraud checks
    7. Process approved payouts
    """
    from datetime import datetime, timezone

    from app.adapters import (
        get_aqi_adapter,
        get_event_flag_adapters,
        get_outage_adapter,
        get_payment_gateway,
        get_traffic_adapter,
        get_weather_adapter,
    )
    from app.database import SessionLocal
    from app.engine.claims_engine import trigger_claims_for_event
    from app.engine.disruption_manager import (
        close_disruption,
        get_active_disruption,
        open_disruption,
        update_disruption,
    )
    from app.engine.fraud_checker import run_fraud_checks
    from app.engine.payout_service import process_payout
    from app.engine.zdi_scorer import compute_zdi
    from app.models.signal_reading import SignalReading as SignalReadingModel
    from app.models.signal_reading import ZDISnapshot
    from app.models.zone import Zone
    from app.models.zone_zdi_log import ZoneZDILog
    from app.services.audit_service import write_audit

    db = SessionLocal()
    try:
        zones = db.query(Zone).filter(Zone.is_active == True).all()

        core_adapters = [
            get_weather_adapter(),
            get_traffic_adapter(),
            get_aqi_adapter(),
            get_outage_adapter(),
        ]
        event_flag_adapters = get_event_flag_adapters()
        adapters = core_adapters + event_flag_adapters
        event_flag_types = {adapter.get_signal_type() for adapter in event_flag_adapters}

        gateway = get_payment_gateway()

        for zone in zones:
            # 1. Fetch all configured readings for the zone.
            readings = [adapter.fetch(zone.zone_id) for adapter in adapters]
            active_event_payloads: list[dict] = []

            # 2. Persist raw signal readings.
            for r in readings:
                db.add(
                    SignalReadingModel(
                        zone_id=r.zone_id,
                        signal_type=r.signal_type,
                        raw_value=r.raw_value,
                        normalized_score=r.normalized_score,
                        source_id=r.source_id,
                        is_mocked=r.is_mocked,
                        recorded_at=r.recorded_at,
                    )
                )

                # Event flags are logging-only for transparency right now.
                if r.signal_type in event_flag_types and float(r.raw_value) >= 1.0:
                    active_event_payloads.append(
                        {
                            "signal_type": r.signal_type,
                            "raw_value": float(r.raw_value),
                            "severity_weight": _extract_severity_weight(r.source_id),
                            "source_id": r.source_id,
                            "recorded_at": r.recorded_at.isoformat(),
                            "is_mocked": r.is_mocked,
                        }
                    )

            # 3. Compute ZDI from all signals (core + event flags).
            result = compute_zdi(zone.zone_id, readings)

            db.add(
                ZoneZDILog(
                    zone_id=result.zone_id,
                    zdi_value=float(result.zdi_score),
                    timestamp=result.snapshot_at,
                )
            )

            db.add(
                ZDISnapshot(
                    zone_id=result.zone_id,
                    zdi_score=result.zdi_score,
                    disruption_level=result.disruption_level,
                    payout_pct=result.payout_pct,
                    rain_component=result.rain_component,
                    outage_component=result.outage_component,
                    traffic_component=result.traffic_component,
                    aqi_component=result.aqi_component,
                    snapshot_at=result.snapshot_at,
                )
            )
            db.commit()

            for payload in active_event_payloads:
                write_audit(
                    db,
                    "EVENT_SIGNAL_ACTIVE",
                    "Zone",
                    zone.zone_id,
                    zone_id=zone.zone_id,
                    payload={
                        "signal_type": payload["signal_type"],
                        "raw_value": payload["raw_value"],
                        "severity_weight": payload["severity_weight"],
                        "source_id": payload["source_id"],
                        "recorded_at": payload["recorded_at"],
                    },
                    is_mocked=payload["is_mocked"],
                )

            write_audit(
                db,
                "ZDI_COMPUTED",
                "Zone",
                zone.zone_id,
                zone_id=zone.zone_id,
                payload={
                    "zdi": result.zdi_score,
                    "level": result.disruption_level,
                    "base_zdi": result.base_zdi,
                    "event_boost_total": result.event_boost_total,
                    "final_zdi": result.final_zdi,
                    "active_event_signals": result.active_event_signals,
                },
                is_mocked=True,
            )

            # 4. Disruption lifecycle.
            active_event = get_active_disruption(db, zone.zone_id)

            if result.is_disruption and not active_event:
                active_event = open_disruption(db, result)
                write_audit(
                    db,
                    "DISRUPTION_OPENED",
                    "Zone",
                    zone.zone_id,
                    zone_id=zone.zone_id,
                    payload={"zdi": result.zdi_score, "event_id": active_event.event_id},
                )

            elif result.is_disruption and active_event:
                update_disruption(db, active_event, result)

            elif not result.is_disruption and active_event:
                closed_event = close_disruption(db, active_event, datetime.now(timezone.utc))
                write_audit(
                    db,
                    "DISRUPTION_CLOSED",
                    "Zone",
                    zone.zone_id,
                    zone_id=zone.zone_id,
                    payload={
                        "event_id": closed_event.event_id,
                        "affected_hours": float(closed_event.affected_hours or 0),
                        "peak_zdi": closed_event.peak_zdi,
                    },
                )

                # 5. Trigger claims.
                claims = trigger_claims_for_event(db, closed_event)
                write_audit(
                    db,
                    "CLAIMS_TRIGGERED",
                    "Zone",
                    zone.zone_id,
                    zone_id=zone.zone_id,
                    payload={"claim_count": len(claims)},
                )

                for claim in claims:
                    # 6. Fraud check.
                    fraud_score, fraud_flag = run_fraud_checks(db, claim)
                    claim.fraud_score = fraud_score
                    claim.fraud_flag = fraud_flag
                    claim.status = "FLAGGED" if fraud_flag else "APPROVED"
                    db.commit()

                    write_audit(
                        db,
                        "FRAUD_CHECK",
                        "Claim",
                        claim.claim_id,
                        zone_id=zone.zone_id,
                        payload={"fraud_score": fraud_score, "flagged": fraud_flag},
                    )

                    if not fraud_flag:
                        # 7. Process payout.
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
