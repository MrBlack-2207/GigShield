# gigshield/data/demo_runner.py
#
# DEMO CONTROL SCRIPT
# Simulates a complete parametric insurance event end-to-end.
#
# Usage from PowerShell:
#   docker exec gigshield_backend python /app/../data/demo_runner.py rainfall BLR-01
#   docker exec gigshield_backend python /app/../data/demo_runner.py outage   BLR-02
#   docker exec gigshield_backend python /app/../data/demo_runner.py extreme  BLR-03
#   docker exec gigshield_backend python /app/../data/demo_runner.py reset

import sys
sys.path.insert(0, "/app")

from datetime import datetime, timezone, timedelta
from app.database import SessionLocal
from app.models.zone            import Zone
from app.models.signal_reading  import SignalReading, ZDISnapshot
from app.models.disruption_event import DisruptionEvent
from app.interfaces.signal_provider import SignalReading as SRDataclass
from app.engine import (
    compute_zdi,
    open_disruption, close_disruption, get_active_disruption,
    trigger_claims_for_event, run_fraud_checks, process_payout,
)
from app.services.audit_service import write_audit
from app.adapters import get_payment_gateway

# ── Scenario definitions ───────────────────────────────────────────────────
SCENARIOS = {
    "rainfall": {
        "label":   "Heavy Rainfall — Moderate Disruption",
        "signals": {
            "RAINFALL":        65.0,   # normalized → ~75 (severe rain)
            "PLATFORM_OUTAGE": 0.0,
            "TRAFFIC":         45.0,   # normalized → ~37
            "AQI":             0.0,
        },
        "duration_hours": 3.5,
    },
    "outage": {
        "label":   "Platform Outage — Zepto/Blinkit Down",
        "signals": {
            "RAINFALL":        5.0,    # normalized → ~18 (light rain)
            "PLATFORM_OUTAGE": 1.0,    # normalized → 100 (full outage)
            "TRAFFIC":         30.0,   # normalized → ~15
            "AQI":             0.0,
        },
        "duration_hours": 2.0,
    },
    "extreme": {
        "label":   "Extreme Event — Rain + Outage + Traffic",
        "signals": {
            "RAINFALL":        1.0,    # normalized → 100
            "PLATFORM_OUTAGE": 1.0,    # normalized → 100
            "TRAFFIC":         1.0,    # normalized → 100
            "AQI":             0.0,
        },
        "duration_hours": 5.0,
    },
}

# Raw → normalized helpers (mirrors the adapter normalize() methods)
def _normalize_rainfall(raw):
    if raw < 2.5:   return 0
    if raw < 7.0:   return int(1  + (raw - 2.5)  / 4.5  * 23)
    if raw < 15.0:  return int(25 + (raw - 7.0)  / 8.0  * 24)
    if raw < 25.0:  return int(50 + (raw - 15.0) / 10.0 * 24)
    return min(100, int(75 + (raw - 25.0) / 10.0 * 25))

def _normalize_outage(raw):   return 100 if raw == 1.0 else 0
def _normalize_traffic(raw):
    if raw < 20.0:  return 0
    if raw < 40.0:  return int(1  + (raw - 20.0) / 20.0 * 23)
    if raw < 60.0:  return int(25 + (raw - 40.0) / 20.0 * 49)
    return min(100, int(75 + (raw - 60.0) / 40.0 * 25))
def _normalize_aqi(raw):
    if raw < 150.0: return 0
    if raw < 200.0: return int(1  + (raw - 150.0) / 50.0  * 23)
    if raw < 300.0: return int(25 + (raw - 200.0) / 100.0 * 49)
    return min(100, int(75 + (raw - 300.0) / 200.0 * 25))

NORMALIZERS = {
    "RAINFALL":        _normalize_rainfall,
    "PLATFORM_OUTAGE": _normalize_outage,
    "TRAFFIC":         _normalize_traffic,
    "AQI":             _normalize_aqi,
}


def run_scenario(scenario_key: str, zone_id: str):
    scenario = SCENARIOS[scenario_key]
    print(f"\n{'='*60}")
    print(f"  SCENARIO : {scenario['label']}")
    print(f"  ZONE     : {zone_id}")
    print(f"  DURATION : {scenario['duration_hours']} hours")
    print(f"{'='*60}\n")

    db = SessionLocal()
    try:
        zone = db.query(Zone).filter(Zone.zone_id == zone_id).first()
        if not zone:
            print(f"ERROR: Zone {zone_id} not found. Run workers_seed.py first.")
            return

        # ── Step 1: Build signal readings from scenario ──────────────────
        print("  [1/5] Generating signal readings...")
        now = datetime.now(timezone.utc)
        readings = []

        for signal_type, raw_value in scenario["signals"].items():
            normalized = NORMALIZERS[signal_type](raw_value)
            r = SRDataclass(
                zone_id=zone_id,
                signal_type=signal_type,
                raw_value=raw_value,
                normalized_score=normalized,
                source_id="demo_runner_v1",
                is_mocked=True,
                recorded_at=now,
            )
            readings.append(r)
            db.add(SignalReading(
                zone_id=zone_id,
                signal_type=signal_type,
                raw_value=raw_value,
                normalized_score=normalized,
                source_id="demo_runner_v1",
                is_mocked=True,
                recorded_at=now,
            ))

        db.commit()
        print(f"      Readings persisted for {len(readings)} signals.")

        # ── Step 2: Compute ZDI ───────────────────────────────────────────
        print("  [2/5] Computing ZDI...")
        result = compute_zdi(zone_id, readings)

        db.add(ZDISnapshot(
            zone_id=result.zone_id,
            zdi_score=result.zdi_score,
            disruption_level=result.disruption_level,
            payout_pct=result.payout_pct,
            rain_component=result.rain_component,
            outage_component=result.outage_component,
            traffic_component=result.traffic_component,
            aqi_component=result.aqi_component,
            snapshot_at=now,
        ))
        db.commit()

        print(f"      ZDI Score     : {result.zdi_score}/100")
        print(f"      Level         : {result.disruption_level}")
        print(f"      Payout %      : {result.payout_pct}%")
        print(f"      Components    : Rain={result.rain_component} "
              f"Outage={result.outage_component} "
              f"Traffic={result.traffic_component} "
              f"AQI={result.aqi_component}")

        if not result.is_disruption:
            print("\n  ZDI < 25 — no disruption threshold crossed. No claims triggered.")
            print("  Tip: use 'extreme' scenario to guarantee a payout.")
            return

        # ── Step 3: Open + immediately close disruption event ────────────
        print("  [3/5] Opening and closing disruption event...")

        active = get_active_disruption(db, zone_id)
        if active:
            close_disruption(db, active, now)

        event = open_disruption(db, result)
        write_audit(db, "DISRUPTION_OPENED", "Zone", zone_id,
                    zone_id=zone_id,
                    payload={"zdi": result.zdi_score, "scenario": scenario_key})

        # Simulate duration by backdating started_at
        started = now - timedelta(hours=scenario["duration_hours"])
        event.started_at = started
        db.commit()

        closed_event = close_disruption(db, event, now)
        write_audit(db, "DISRUPTION_CLOSED", "Zone", zone_id,
                    zone_id=zone_id,
                    payload={
                        "event_id":       closed_event.event_id,
                        "affected_hours": float(closed_event.affected_hours),
                        "peak_zdi":       closed_event.peak_zdi,
                    })

        print(f"      Event ID      : {closed_event.event_id[:8]}...")
        print(f"      Affected hrs  : {closed_event.affected_hours}")
        print(f"      Peak ZDI      : {closed_event.peak_zdi}")

        # ── Step 4: Trigger claims ────────────────────────────────────────
        print("  [4/5] Triggering claims for active policies...")
        claims = trigger_claims_for_event(db, closed_event)

        if not claims:
            print("      No active policies found in this zone.")
            print("      Tip: run workers_seed.py to add demo workers.")
            return

        print(f"      Claims created: {len(claims)}")

        # ── Step 5: Fraud check + payout ─────────────────────────────────
        print("  [5/5] Running fraud checks and processing payouts...\n")
        gateway = get_payment_gateway()

        for claim in claims:
            fraud_score, fraud_flag = run_fraud_checks(db, claim)
            claim.fraud_score = fraud_score
            claim.fraud_flag  = fraud_flag
            claim.status      = "FLAGGED" if fraud_flag else "APPROVED"
            db.commit()

            status_label = "FLAGGED" if fraud_flag else "APPROVED"
            print(f"      Worker        : {claim.worker_id[:8]}...")
            print(f"      Gross payout  : ₹{claim.gross_payout_inr}")
            print(f"      Final payout  : ₹{claim.final_payout_inr}")
            print(f"      Fraud score   : {claim.fraud_score} → {status_label}")

            if not fraud_flag:
                payout = process_payout(db, claim, gateway)
                print(f"      Payout ref    : {payout.gateway_ref}")
                print(f"      Status        : {payout.status}")
            print()

        print(f"{'='*60}")
        print(f"  DEMO COMPLETE — {len(claims)} claims processed for {zone_id}")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


def reset_demo():
    """Clears all demo-generated data so you can run a fresh demo."""
    print("\nResetting demo data...")
    db = SessionLocal()
    try:
        from app.models.payout          import Payout
        from app.models.claim           import Claim
        from app.models.disruption_event import DisruptionEvent
        from app.models.signal_reading  import SignalReading, ZDISnapshot
        from app.models.audit_log       import AuditLog

        db.query(Payout).delete()
        db.query(Claim).delete()
        db.query(DisruptionEvent).delete()
        db.query(ZDISnapshot).delete()
        db.query(SignalReading).delete()
        db.query(AuditLog).delete()
        db.commit()
        print("  All demo events, claims, payouts cleared.")
        print("  Workers and policies untouched.")
    except Exception as e:
        print(f"  ERROR: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] == "reset":
        reset_demo()
        sys.exit(0)

    if len(args) < 2:
        print("Usage:")
        print("  python demo_runner.py rainfall BLR-01")
        print("  python demo_runner.py outage   BLR-02")
        print("  python demo_runner.py extreme  BLR-03")
        print("  python demo_runner.py reset")
        sys.exit(1)

    scenario_key = args[0]
    zone_id      = args[1]

    if scenario_key not in SCENARIOS:
        print(f"Unknown scenario '{scenario_key}'. Choose: {list(SCENARIOS.keys())}")
        sys.exit(1)

    run_scenario(scenario_key, zone_id)