# Column Dictionary (Use Cases 1-6)

Legend for `role`:
- `index`: key column for joins/versioning only, never model input
- `feature`: model input feature
- `target`: prediction target
- `target_component`: used only to compute target, never model input
- `metadata`: optional diagnostics/context column

## 1) ds_disruption_frequency_zone_month
Granularity: one row per zone per month

| column | type | role | source |
|---|---|---|---|
| zone_id | string | index | zones/zone_zdi_logs |
| year | int | index | timestamps |
| month_of_year | int | index + feature | timestamps |
| season_index | int | feature | month mapping |
| risk_tier_index | int | feature | zones.risk_tier |
| radius_km | float | feature | zones |
| recent_4week_disruption_days | float | feature | zone_zdi_logs |
| prev_4week_zdi_mean | float | feature | zone_zdi_logs |
| prev_4week_zdi_p95 | float | feature | zone_zdi_logs |
| prev_4week_rain_norm_mean | float | feature | signal_readings |
| prev_4week_rain_norm_p95 | float | feature | signal_readings |
| prev_4week_outage_active_ratio | float | feature | signal_readings |
| prev_4week_traffic_norm_mean | float | feature | signal_readings |
| prev_4week_aqi_norm_mean | float | feature | signal_readings |
| prev_4week_event_flag_active_ratio | float | feature | signal_readings |
| seasonal_disruption_days | float | target | zone_zdi_logs |

Notes:
- `zone_id` is index-only and must never be used as a model feature.
- Removed from features by design: `active_workers_count`, `active_policies_count`, season string.

## 2) ds_disruption_severity_event
Granularity: one row per disruption event

| column | type | role | source |
|---|---|---|---|
| event_id | string | index | disruption_events |
| zone_id | string | index | disruption_events |
| season_index | int | feature | event timestamp |
| start_hour | int | feature | disruption_events.started_at |
| day_of_week | int | feature | disruption_events.started_at |
| max_rain_norm | float | feature | signal_readings |
| max_outage_norm | float | feature | signal_readings |
| max_traffic_norm | float | feature | signal_readings |
| max_aqi_norm | float | feature | signal_readings |
| mean_rain_norm | float | feature | signal_readings |
| mean_traffic_norm | float | feature | signal_readings |
| event_flags_active_count | int | feature | signal_readings |
| max_zdi | float | feature | zone_zdi_logs |
| mean_zdi | float | feature | zone_zdi_logs |
| zdi_above_50_ratio | float | feature | zone_zdi_logs |
| zdi_above_75_ratio | float | feature | zone_zdi_logs |
| conditional_payout_rate | float | target | claims + policies |
| payout_tier_class | int | metadata | derived from target |

Removed per feedback: `policies_exposed_count`, `avg_income_tier_exposed`.

## 3) ds_disruption_duration_event
Granularity: one row per disruption event

| column | type | role | source |
|---|---|---|---|
| event_id | string | index | disruption_events |
| zone_id | string | index | disruption_events |
| season_index | int | feature | event timestamp |
| start_hour | int | feature | disruption_events.started_at |
| day_of_week | int | feature | disruption_events.started_at |
| early_rain_mean | float | feature | signal_readings |
| early_outage_ratio | float | feature | signal_readings |
| early_traffic_mean | float | feature | signal_readings |
| early_aqi_mean | float | feature | signal_readings |
| peak_zdi_first_hour | float | feature | zone_zdi_logs |
| zdi_rise_rate_first_hour | float | feature | zone_zdi_logs |
| event_flags_active_count_first_hour | int | feature | signal_readings |
| affected_hours | float | target | disruption_events |
| avg_hours_fraction | float | metadata | affected_hours / 10.0 |

## 4) ds_correlation_load_city_week
Granularity: one row per city-week

| column | type | role | source |
|---|---|---|---|
| city | string | index | zones |
| iso_year | int | index | timestamps |
| iso_week | int | index | timestamps |
| season_index | int | feature | week timestamp |
| active_policies_count | int | feature | policies |
| insured_base_sum | float | feature | policies |
| simultaneous_disruption_ratio | float | feature | zone_zdi_logs |
| rain_zone_correlation | float | feature | signal_readings |
| outage_breadth_ratio | float | feature | signal_readings |
| event_flag_multi_zone_ratio | float | feature | signal_readings |
| zdi_cross_zone_std | float | feature | zone_zdi_logs |
| claims_per_hour_peak | float | feature | claims |
| zones_with_claims_count | int | feature | claims |
| realized_weekly_loss | float | target_component | payouts/claims |
| independent_weekly_loss_baseline | float | target_component | synthetic baseline |
| correlation_load | float | target | derived from target components |

Important: `realized_weekly_loss` and `independent_weekly_loss_baseline` must not be used as model features.

## 5) ds_zdi_trigger_quality_interval
Granularity: one row per zone per 15-minute interval

| column | type | role | source |
|---|---|---|---|
| zone_id | string | index | zone_zdi_logs/signal_readings |
| ts_15m | datetime | index | zone_zdi_logs/signal_readings |
| season_index | int | feature | timestamp |
| hour | int | feature | timestamp |
| day_of_week | int | feature | timestamp |
| rain_norm | float | feature | signal_readings |
| outage_norm | float | feature | signal_readings |
| traffic_norm | float | feature | signal_readings |
| aqi_norm | float | feature | signal_readings |
| strike | int | feature | signal_readings |
| bandh | int | feature | signal_readings |
| petrol_crisis | int | feature | signal_readings |
| lockdown | int | feature | signal_readings |
| curfew | int | feature | signal_readings |
| zdi_lag_1 | float | feature | zone_zdi_logs |
| zdi_lag_2 | float | feature | zone_zdi_logs |
| rain_lag_1 | float | feature | signal_readings |
| outage_lag_1 | float | feature | signal_readings |
| risk_tier_index | int | feature | zones |
| radius_km | float | feature | zones |
| true_disruption | int | target | synthetic/validated label |
| operational_impact_proxy | int | metadata | disruption_events + claims |

## 6) ds_fraud_worker_week
Granularity: one row per worker per week

| column | type | role | source |
|---|---|---|---|
| worker_id | string | index | workers |
| week_start | date | index | timestamps |
| platform_index | int | feature | workers.platform |
| income_tier | int | feature | workers |
| kyc_status_index | int | feature | workers.kyc_status |
| external_worker_id_present | int | feature | workers.external_worker_id |
| policy_status_index | int | feature | policies.status |
| policy_age_days | float | feature | policies |
| cooldown_remaining_hours | float | feature | policies |
| claims_count_7d | int | feature | claims |
| paid_claim_ratio_30d | float | feature | claims |
| mean_claim_amount_30d | float | feature | claims |
| max_claim_amount_30d | float | feature | claims |
| zone_entropy_30d | float | feature | claims |
| hours_between_claims_p50 | float | feature | claims |
| wallet_credits_7d | float | feature | wallet_ledger_entries |
| wallet_debits_7d | float | feature | wallet_ledger_entries |
| cashout_count_7d | int | feature | withdrawal_requests |
| cashout_to_payout_time_p50_minutes | float | feature | payouts + withdrawal_requests |
| withdrawal_reject_ratio | float | feature | withdrawal_requests |
| manual_review_count_30d | int | feature | audit_log |
| anomaly_score | float | target | model output |
| weak_fraud_label | int | metadata | claims.fraud_flag / review outcomes |
