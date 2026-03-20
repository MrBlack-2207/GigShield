# gigshield/backend/app/engine/premium_calculator.py

from dataclasses import dataclass
from app.config import get_settings

settings = get_settings()

# ── Seasonal disruption days per week (Bengaluru, locked from design doc) ──
SEASONAL_DISRUPTION_DAYS: dict[str, float] = {
    "dry":          1.0,
    "pre_monsoon":  1.6,
    "monsoon":      2.5,
    "post_monsoon": 1.3,
}

# ── Constants locked from design doc ────────────────────────────────────────
CONDITIONAL_PAYOUT_RATE = 0.50   # E[payout% | ZDI >= 25] — severity given disruption
AVG_HOURS_FRACTION      = 0.40   # E[disruption hours / working hours | disruption]
INCOME_TIERS            = [400, 600, 800]


@dataclass
class PremiumBreakdown:
    """
    Full transparency object. Every component is visible.
    Used for the worker-facing premium preview in the app.
    """
    income_tier:              int
    season:                   str
    coverage_ratio:           float
    seasonal_disruption_days: float
    conditional_payout_rate:  float
    avg_hours_fraction:       float
    correlation_load:         float
    loading_factor:           float
    admin_fee_inr:            float

    expected_weekly_loss:     float   # pre-loading actuarial expected loss
    weekly_premium_inr:       float   # final premium charged
    weekly_payout_cap_inr:    float   # max payout in any single week


def calculate_premium(income_tier: int, season: str) -> PremiumBreakdown:
    """
    Corrected premium formula — separates frequency from severity.

    WeeklyPremium =
        DailyIncome
        × CoverageRatio
        × (SeasonalDisruptionDays / 7)      ← frequency
        × ConditionalPayoutRate             ← severity given disruption
        × AvgHoursFraction                  ← duration
        × CorrelationLoad                   ← systemic event surcharge
        × LoadingFactor                     ← insurer margin
        + AdminFee

    Weekly payout cap = CoverageRatio × DailyIncome × 5
    (caps at 5 insured working days per week)
    """
    if income_tier not in INCOME_TIERS:
        raise ValueError(f"Income tier must be one of {INCOME_TIERS}. Got: {income_tier}")

    season_key = season.lower().replace(" ", "_")
    if season_key not in SEASONAL_DISRUPTION_DAYS:
        raise ValueError(
            f"Season must be one of {list(SEASONAL_DISRUPTION_DAYS.keys())}. Got: {season}"
        )

    disruption_days = SEASONAL_DISRUPTION_DAYS[season_key]

    coverage_ratio    = settings.COVERAGE_RATIO
    correlation_load  = settings.CORRELATION_LOAD
    loading_factor    = settings.LOADING_FACTOR
    admin_fee         = settings.ADMIN_FEE_INR

    expected_weekly_loss = (
        income_tier
        * coverage_ratio
        * (disruption_days / 7)
        * CONDITIONAL_PAYOUT_RATE
        * AVG_HOURS_FRACTION
    )

    weekly_premium = (
        expected_weekly_loss
        * correlation_load
        * loading_factor
    ) + admin_fee

    weekly_payout_cap = coverage_ratio * income_tier * 5

    return PremiumBreakdown(
        income_tier=income_tier,
        season=season_key,
        coverage_ratio=coverage_ratio,
        seasonal_disruption_days=disruption_days,
        conditional_payout_rate=CONDITIONAL_PAYOUT_RATE,
        avg_hours_fraction=AVG_HOURS_FRACTION,
        correlation_load=correlation_load,
        loading_factor=loading_factor,
        admin_fee_inr=admin_fee,
        expected_weekly_loss=round(expected_weekly_loss, 2),
        weekly_premium_inr=round(weekly_premium, 2),
        weekly_payout_cap_inr=round(weekly_payout_cap, 2),
    )


def get_current_season() -> str:
    """
    Returns the current Bengaluru season based on month.
    Used when no season is explicitly passed.
    """
    from datetime import datetime
    month = datetime.utcnow().month
    if month in [1, 2, 3, 4]:
        return "dry"
    elif month in [5, 6]:
        return "pre_monsoon"
    elif month in [7, 8, 9, 10]:
        return "monsoon"
    else:
        return "post_monsoon"