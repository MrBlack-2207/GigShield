# ML Dataset Contracts (Use Cases 1-6)

This folder defines dataset contracts only.

Scope:
- Disruption frequency estimation
- Disruption severity estimation
- Disruption duration estimation
- Correlation load estimation
- ZDI trigger quality classification
- Fraud anomaly detection

Out of scope:
- Synthetic row generation
- Model training
- Backend ML integration

Global contract rules:
1. Identifier columns (`zone_id`, `event_id`, `worker_id`) are index keys only and must not be model input features.
2. Target leakage is disallowed.
3. In correlation-load data, `realized_weekly_loss` and `independent_weekly_loss_baseline` are target-construction columns only and must not be model inputs.
4. Timestamp fields are UTC.

Artifacts:
- `dataset_contracts.yaml`: canonical machine-readable contracts.
- `column_dictionary.md`: human-readable column dictionary.
- `schemas/*.schema.json`: row-level JSON schemas per dataset.
