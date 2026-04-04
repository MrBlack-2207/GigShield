#!/usr/bin/env python
"""
Expand simulation entities for ML/testing without touching core business logic.

Creates/expands:
- zones (optional generation)
- dark stores
- workers
- policies

Safety defaults:
- Reuses existing zones only (no new zones unless --allow-generate-zones)
- Does not add workers to already-populated stores unless --append-existing
- Creates policies only for workers without any policy

Examples:
  python scripts/expand_simulation_world.py --dry-run
  python scripts/expand_simulation_world.py --num-zones 8 --allow-generate-zones --dry-run
  python scripts/expand_simulation_world.py --dark-stores-per-zone-per-platform 2 --workers-per-store 40
  python scripts/expand_simulation_world.py --append-existing --workers-per-store 60
"""

from __future__ import annotations

import argparse
import calendar
import random
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable


RISK_TIERS = ("LOW", "MEDIUM", "HIGH")
PLATFORMS = ("zepto", "blinkit")
INCOME_TIERS = (400, 600, 800)

FIRST_NAMES = [
    "Ravi", "Suresh", "Anitha", "Mohammed", "Kavya", "Deepak", "Arjun", "Lakshmi",
    "Nikhil", "Pooja", "Rahul", "Sneha", "Kiran", "Meena", "Vikram", "Asha",
    "Rohan", "Divya", "Sanjay", "Priya",
]
LAST_NAMES = [
    "Kumar", "Babu", "Raj", "Arif", "Nair", "Singh", "Reddy", "Sharma",
    "Patil", "Menon", "Iyer", "Das", "Shetty", "Yadav", "Jain", "Gupta",
    "Mishra", "Pillai", "Verma", "Chopra",
]


@dataclass
class ZoneCtx:
    zone_id: str
    centroid_lat: float
    centroid_lng: float
    existing: bool
    zone_obj: object | None = None


@dataclass
class StoreCtx:
    id: str
    zone_id: str
    platform: str
    existing: bool
    worker_count: int
    store_obj: object | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expand simulation seed world.")
    parser.add_argument("--num-zones", type=int, default=None)
    parser.add_argument("--dark-stores-per-zone-per-platform", type=int, default=1)
    parser.add_argument("--workers-per-store", type=int, default=25)
    parser.add_argument("--policy-activation-ratio", type=float, default=0.70)
    parser.add_argument("--allow-generate-zones", action="store_true")
    parser.add_argument("--append-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--city", type=str, default="Bengaluru")
    return parser.parse_args()


def add_months_utc(dt: datetime, months: int) -> datetime:
    year = dt.year + ((dt.month - 1 + months) // 12)
    month = ((dt.month - 1 + months) % 12) + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def season_from_month(month: int) -> str:
    if month in (1, 2, 3, 4):
        return "dry"
    if month in (5, 6):
        return "pre_monsoon"
    if month in (7, 8, 9, 10):
        return "monsoon"
    return "post_monsoon"


def seasonal_profile_for_risk(risk_tier: str, rng: random.Random) -> dict[str, float]:
    if risk_tier == "HIGH":
        base = {"dry": 1.0, "pre_monsoon": 1.8, "monsoon": 2.8, "post_monsoon": 1.5}
    elif risk_tier == "MEDIUM":
        base = {"dry": 0.8, "pre_monsoon": 1.5, "monsoon": 2.3, "post_monsoon": 1.2}
    else:
        base = {"dry": 0.6, "pre_monsoon": 1.2, "monsoon": 1.8, "post_monsoon": 1.0}

    # Keep profiles realistic but not identical.
    return {
        k: round(max(0.3, v + rng.uniform(-0.15, 0.15)), 1)
        for k, v in base.items()
    }


def next_zone_id(existing_zone_ids: Iterable[str]) -> str:
    max_idx = 0
    for zid in existing_zone_ids:
        if zid.startswith("BLR-"):
            try:
                max_idx = max(max_idx, int(zid.split("-", 1)[1]))
            except Exception:
                continue
    return f"BLR-{max_idx + 1:02d}"


def select_policy_status(activation_ratio: float, rng: random.Random) -> str:
    if rng.random() < activation_ratio:
        return "active"
    r = rng.random()
    if r < 0.30:
        return "pending_activation"
    if r < 0.75:
        return "inactive"
    return "expired"


def generate_policy_timeline(
    status: str,
    tenure_months: int,
    now: datetime,
    rng: random.Random,
) -> dict[str, datetime]:
    if status == "active":
        start_date = now - timedelta(days=rng.randint(5, 50))
        cooldown_ends = start_date + timedelta(hours=48)
        if cooldown_ends > now:
            start_date = now - timedelta(days=3)
            cooldown_ends = start_date + timedelta(hours=48)
        end_date = add_months_utc(start_date, tenure_months)
        if end_date <= now:
            end_date = now + timedelta(days=rng.randint(30, 180))
        last_premium_paid_at = now - timedelta(days=rng.randint(0, 6))
        next_premium_due_at = last_premium_paid_at + timedelta(days=7)
        if next_premium_due_at <= now:
            next_premium_due_at = now + timedelta(days=rng.randint(1, 6))

    elif status == "pending_activation":
        start_date = now - timedelta(hours=rng.randint(1, 24))
        cooldown_ends = now + timedelta(hours=rng.randint(1, 48))
        end_date = add_months_utc(start_date, tenure_months)
        if end_date <= now:
            end_date = now + timedelta(days=30)
        last_premium_paid_at = start_date
        next_premium_due_at = last_premium_paid_at + timedelta(days=7)
        if next_premium_due_at <= now:
            next_premium_due_at = now + timedelta(days=2)

    elif status == "inactive":
        start_date = now - timedelta(days=rng.randint(20, 120))
        cooldown_ends = min(now - timedelta(hours=1), start_date + timedelta(hours=48))
        end_date = add_months_utc(start_date, tenure_months)
        if end_date <= now:
            end_date = now + timedelta(days=rng.randint(10, 120))
        last_premium_paid_at = now - timedelta(days=rng.randint(8, 45))
        next_premium_due_at = last_premium_paid_at + timedelta(days=7)
        if next_premium_due_at >= now:
            next_premium_due_at = now - timedelta(hours=rng.randint(1, 72))

    else:  # expired
        start_date = now - timedelta(days=rng.randint(90, 420))
        cooldown_ends = start_date + timedelta(hours=48)
        end_date = add_months_utc(start_date, tenure_months)
        if end_date >= now:
            end_date = now - timedelta(days=rng.randint(1, 45))
        last_premium_paid_at = min(end_date - timedelta(days=1), now - timedelta(days=10))
        next_premium_due_at = min(last_premium_paid_at + timedelta(days=7), end_date)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "cooldown_ends_at": cooldown_ends,
        "last_premium_paid_at": last_premium_paid_at,
        "next_premium_due_at": next_premium_due_at,
    }


def init_backend_imports(repo_root: Path):
    backend_path = repo_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from sqlalchemy import func  # noqa
    from app.database import SessionLocal  # noqa
    from app.engine.premium_calculator import calculate_premium  # noqa
    from app.models.dark_store import DarkStore  # noqa
    from app.models.policy import Policy  # noqa
    from app.models.worker import Worker  # noqa
    from app.models.zone import Zone  # noqa

    return {
        "func": func,
        "SessionLocal": SessionLocal,
        "calculate_premium": calculate_premium,
        "DarkStore": DarkStore,
        "Policy": Policy,
        "Worker": Worker,
        "Zone": Zone,
    }


def main() -> int:
    args = parse_args()

    if not (0.0 <= args.policy_activation_ratio <= 1.0):
        raise SystemExit("--policy-activation-ratio must be between 0 and 1.")
    if args.num_zones is not None and args.num_zones <= 0:
        raise SystemExit("--num-zones must be > 0.")
    if args.dark_stores_per_zone_per_platform <= 0:
        raise SystemExit("--dark-stores-per-zone-per-platform must be > 0.")
    if args.workers_per_store < 0:
        raise SystemExit("--workers-per-store must be >= 0.")

    rng = random.Random(args.seed)
    repo_root = Path(__file__).resolve().parents[1]
    imports = init_backend_imports(repo_root)

    func = imports["func"]
    SessionLocal = imports["SessionLocal"]
    calculate_premium = imports["calculate_premium"]
    DarkStore = imports["DarkStore"]
    Policy = imports["Policy"]
    Worker = imports["Worker"]
    Zone = imports["Zone"]

    stats = {
        "zones_reused": 0,
        "zones_created": 0,
        "dark_stores_reused": 0,
        "dark_stores_created": 0,
        "workers_existing_selected_stores": 0,
        "workers_created": 0,
        "workers_skipped_populated_store": 0,
        "policies_existing": 0,
        "policies_created": 0,
    }

    db = SessionLocal()
    now = datetime.now(timezone.utc)
    temp_id_counter = 1
    try:
        existing_zones = db.query(Zone).filter(Zone.is_active == True).order_by(Zone.zone_id.asc()).all()
        target_zone_count = args.num_zones if args.num_zones is not None else len(existing_zones)
        selected_zone_count = min(target_zone_count, len(existing_zones))

        selected_zones: list[ZoneCtx] = []
        for zone in existing_zones[:selected_zone_count]:
            selected_zones.append(
                ZoneCtx(
                    zone_id=zone.zone_id,
                    centroid_lat=float(zone.centroid_lat),
                    centroid_lng=float(zone.centroid_lng),
                    existing=True,
                    zone_obj=zone,
                )
            )
            stats["zones_reused"] += 1

        missing = max(0, target_zone_count - len(selected_zones))
        if missing > 0:
            if args.allow_generate_zones:
                existing_zone_ids = [z.zone_id for z in existing_zones] + [z.zone_id for z in selected_zones]
                for _ in range(missing):
                    zone_id = next_zone_id(existing_zone_ids)
                    existing_zone_ids.append(zone_id)
                    risk_tier = rng.choices(RISK_TIERS, weights=[0.30, 0.45, 0.25], k=1)[0]
                    centroid_lat = 12.9716 + rng.uniform(-0.16, 0.16)
                    centroid_lng = 77.5946 + rng.uniform(-0.22, 0.22)
                    radius_km = round(rng.uniform(1.8, 3.4), 2)
                    seasonal_profile = seasonal_profile_for_risk(risk_tier, rng)

                    if args.dry_run:
                        zone_ctx = ZoneCtx(
                            zone_id=zone_id,
                            centroid_lat=centroid_lat,
                            centroid_lng=centroid_lng,
                            existing=False,
                            zone_obj=None,
                        )
                    else:
                        zone_obj = Zone(
                            zone_id=zone_id,
                            name=f"Sim Zone {zone_id}",
                            city=args.city,
                            centroid_lat=centroid_lat,
                            centroid_lng=centroid_lng,
                            radius_km=radius_km,
                            risk_tier=risk_tier,
                            seasonal_disruption_days=seasonal_profile,
                            is_active=True,
                        )
                        db.add(zone_obj)
                        db.flush()
                        zone_ctx = ZoneCtx(
                            zone_id=zone_id,
                            centroid_lat=centroid_lat,
                            centroid_lng=centroid_lng,
                            existing=False,
                            zone_obj=zone_obj,
                        )
                    selected_zones.append(zone_ctx)
                    stats["zones_created"] += 1
            else:
                print(
                    f"[INFO] Requested {target_zone_count} zones but only {len(existing_zones)} exist. "
                    "Reusing existing zones only. Pass --allow-generate-zones to create more."
                )

        # Track unique worker identifiers.
        existing_phones = {p for (p,) in db.query(Worker.phone).all()}
        numeric_phones = [int(p) for p in existing_phones if p and p.isdigit() and len(p) == 10]
        next_phone_int = max(numeric_phones, default=9000000000) + 1

        ext_ids_by_platform = {platform: set() for platform in PLATFORMS}
        for platform, ext_id in db.query(Worker.platform, Worker.external_worker_id).filter(
            Worker.external_worker_id.isnot(None)
        ):
            if platform in ext_ids_by_platform:
                ext_ids_by_platform[platform].add(ext_id)

        ext_seq = {platform: len(ext_ids_by_platform[platform]) + 1 for platform in PLATFORMS}

        all_selected_stores: list[StoreCtx] = []

        for zone in selected_zones:
            for platform in PLATFORMS:
                stores = (
                    db.query(DarkStore)
                    .filter(
                        DarkStore.zone_id == zone.zone_id,
                        DarkStore.platform == platform,
                    )
                    .order_by(DarkStore.created_at.asc(), DarkStore.id.asc())
                    .all()
                )

                target_store_count = args.dark_stores_per_zone_per_platform
                selected_existing = stores[:target_store_count]

                for store in selected_existing:
                    worker_count = (
                        db.query(func.count(Worker.worker_id))
                        .filter(Worker.home_store_id == store.id)
                        .scalar()
                    )
                    stats["dark_stores_reused"] += 1
                    stats["workers_existing_selected_stores"] += int(worker_count or 0)
                    all_selected_stores.append(
                        StoreCtx(
                            id=store.id,
                            zone_id=zone.zone_id,
                            platform=platform,
                            existing=True,
                            worker_count=int(worker_count or 0),
                            store_obj=store,
                        )
                    )

                needed = max(0, target_store_count - len(selected_existing))
                for idx in range(needed):
                    lat = zone.centroid_lat + rng.uniform(-0.015, 0.015)
                    lng = zone.centroid_lng + rng.uniform(-0.015, 0.015)

                    if args.dry_run:
                        store_id = f"DRY-STORE-{temp_id_counter:06d}"
                        temp_id_counter += 1
                        store_ctx = StoreCtx(
                            id=store_id,
                            zone_id=zone.zone_id,
                            platform=platform,
                            existing=False,
                            worker_count=0,
                            store_obj=None,
                        )
                    else:
                        store_obj = DarkStore(
                            name=f"{platform.title()} {zone.zone_id} Store {len(selected_existing) + idx + 1}",
                            platform=platform,
                            zone_id=zone.zone_id,
                            location={"lat": round(lat, 6), "lng": round(lng, 6)},
                        )
                        db.add(store_obj)
                        db.flush()
                        store_ctx = StoreCtx(
                            id=store_obj.id,
                            zone_id=zone.zone_id,
                            platform=platform,
                            existing=False,
                            worker_count=0,
                            store_obj=store_obj,
                        )
                    stats["dark_stores_created"] += 1
                    all_selected_stores.append(store_ctx)

        # Worker expansion.
        created_worker_ids: list[str] = []
        created_workers_without_ids: dict[str, int] = {}

        for store in all_selected_stores:
            if args.append_existing:
                to_create = max(0, args.workers_per_store - store.worker_count)
            else:
                if store.worker_count > 0:
                    stats["workers_skipped_populated_store"] += 1
                to_create = args.workers_per_store if store.worker_count == 0 else 0

            if to_create <= 0:
                continue

            if args.dry_run:
                stats["workers_created"] += to_create
                created_workers_without_ids[store.id] = created_workers_without_ids.get(store.id, 0) + to_create
                continue

            for _ in range(to_create):
                # phone
                while str(next_phone_int) in existing_phones:
                    next_phone_int += 1
                phone = str(next_phone_int)
                existing_phones.add(phone)
                next_phone_int += 1

                # platform-specific external ID
                while True:
                    ext_id = f"SIM-{store.platform[:1].upper()}-{ext_seq[store.platform]:08d}"
                    ext_seq[store.platform] += 1
                    if ext_id not in ext_ids_by_platform[store.platform]:
                        ext_ids_by_platform[store.platform].add(ext_id)
                        break

                full_name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
                worker = Worker(
                    full_name=full_name,
                    phone=phone,
                    aadhaar_hash=None,
                    primary_zone_id=store.zone_id,
                    home_store_id=store.id,
                    income_tier=rng.choices(INCOME_TIERS, weights=[0.35, 0.45, 0.20], k=1)[0],
                    platform=store.platform,
                    external_worker_id=ext_id,
                    kyc_status=rng.choices(["VERIFIED", "PENDING"], weights=[0.88, 0.12], k=1)[0],
                    is_active=True,
                )
                db.add(worker)
                db.flush()
                created_worker_ids.append(worker.worker_id)
                stats["workers_created"] += 1

        # Policy expansion: create policy only for workers without any policy.
        season_now = season_from_month(now.month)

        for store in all_selected_stores:
            if args.dry_run:
                existing_without_policy = (
                    db.query(func.count(Worker.worker_id))
                    .outerjoin(Policy, Policy.worker_id == Worker.worker_id)
                    .filter(
                        Worker.home_store_id == store.id,
                        Policy.policy_id.is_(None),
                    )
                    .scalar()
                )
                new_workers = created_workers_without_ids.get(store.id, 0)
                stats["policies_created"] += int(existing_without_policy or 0) + new_workers
                continue

            workers_without_policy = (
                db.query(Worker)
                .outerjoin(Policy, Policy.worker_id == Worker.worker_id)
                .filter(
                    Worker.home_store_id == store.id,
                    Policy.policy_id.is_(None),
                )
                .all()
            )

            for worker in workers_without_policy:
                status = select_policy_status(args.policy_activation_ratio, rng)
                tenure_months = rng.choices([1, 3, 6, 12], weights=[0.50, 0.25, 0.15, 0.10], k=1)[0]
                timeline = generate_policy_timeline(status, tenure_months, now, rng)
                purchase_season = season_from_month(timeline["start_date"].month) or season_now
                premium = calculate_premium(worker.income_tier, purchase_season)

                week_start = timeline["last_premium_paid_at"].date()
                week_end = week_start + timedelta(days=7)

                policy = Policy(
                    worker_id=worker.worker_id,
                    zone_id=worker.primary_zone_id,
                    income_tier=worker.income_tier,
                    weekly_premium_inr=Decimal(str(premium.weekly_premium_inr)),
                    coverage_ratio=Decimal(str(premium.coverage_ratio)),
                    weekly_payout_cap=Decimal(str(premium.weekly_payout_cap_inr)),
                    season_at_purchase=purchase_season,
                    tenure_months=tenure_months,
                    start_date=timeline["start_date"],
                    end_date=timeline["end_date"],
                    billing_cycle="weekly",
                    last_premium_paid_at=timeline["last_premium_paid_at"],
                    next_premium_due_at=timeline["next_premium_due_at"],
                    cooldown_ends_at=timeline["cooldown_ends_at"],
                    week_start=week_start,
                    week_end=week_end,
                    status=status,
                    lookback_exclusion_until=timeline["cooldown_ends_at"],
                )
                db.add(policy)
                stats["policies_created"] += 1

        if args.dry_run:
            db.rollback()
            print("[DRY-RUN] No rows were inserted.")
        else:
            db.commit()
            print("[OK] Simulation expansion committed.")

        # Additional metrics for visibility.
        total_policies_existing = db.query(func.count(Policy.policy_id)).scalar()
        total_workers_existing = db.query(func.count(Worker.worker_id)).scalar()
        stats["policies_existing"] = int(total_policies_existing or 0)
        stats["workers_existing_selected_stores"] = int(stats["workers_existing_selected_stores"])

        selected_zone_total = stats["zones_reused"] + stats["zones_created"]
        selected_store_total = stats["dark_stores_reused"] + stats["dark_stores_created"]

        print("\nSimulation Summary")
        print("------------------")
        print(f"zones_selected: {selected_zone_total} (reused={stats['zones_reused']}, created={stats['zones_created']})")
        print(
            "dark_stores_selected: "
            f"{selected_store_total} (reused={stats['dark_stores_reused']}, created={stats['dark_stores_created']})"
        )
        print(f"workers_existing_in_selected_stores: {stats['workers_existing_selected_stores']}")
        print(f"workers_created: {stats['workers_created']}")
        print(f"stores_skipped_in_safe_mode: {stats['workers_skipped_populated_store']}")
        print(f"policies_created: {stats['policies_created']}")
        print(f"total_workers_in_db_after_run: {int(total_workers_existing or 0)}")
        print(f"total_policies_in_db_after_run: {int(total_policies_existing or 0)}")
        print("\nRun Mode")
        print("--------")
        print(f"dry_run={args.dry_run}")
        print(f"append_existing={args.append_existing}")
        print(f"allow_generate_zones={args.allow_generate_zones}")

        return 0

    except Exception as exc:
        db.rollback()
        print(f"[ERROR] {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
