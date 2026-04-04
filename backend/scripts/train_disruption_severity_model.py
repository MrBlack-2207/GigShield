#!/usr/bin/env python
"""
Train ML Use Case 2 model (Disruption Severity Estimation).

Target:
  payout_rate

Identifiers/context dropped:
  event_id, zone_id

Feature policy:
  all remaining numeric columns.

Split modes:
  - default: random split
  - --time-split: sort by natural temporal columns when present;
    otherwise fallback to dataset row order.

Saves:
  models/disruption_severity_model.pkl
"""

from __future__ import annotations

import argparse
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight


TARGET_COL = "payout_rate"
ID_COLS = {"event_id", "zone_id"}
DEFAULT_MODEL_PATH = Path("models/disruption_severity_model.pkl")
DEFAULT_DATASET_NAME = "ds_disruption_severity_event.csv"

# Fixed severity mapping per requirements.
PAYOUT_RATE_TO_CLASS = {0.40: 0, 0.70: 1, 1.00: 2}
CLASS_TO_PAYOUT_RATE = {0: 0.40, 1: 0.70, 2: 1.00}

TIME_ORDER_CANDIDATES = [
    "event_start_ts",
    "start_timestamp",
    "start_time",
    "started_at",
    "created_at",
    "timestamp",
    "date",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train disruption severity LightGBM model.")
    parser.add_argument(
        "--data-path",
        type=Path,
        default=None,
        help=f"Path to dataset CSV. Defaults to <repo>/data/ml_datasets/{DEFAULT_DATASET_NAME}.",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=DEFAULT_MODEL_PATH,
        help=f"Path to save trained model (default: {DEFAULT_MODEL_PATH}).",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Test split ratio (default: 0.2).",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed for splitting/model (default: 42).",
    )
    parser.add_argument(
        "--time-split",
        action="store_true",
        help="Use time-aware split: train on earlier rows, test on later rows.",
    )
    return parser.parse_args()


def _candidate_roots(start: Path) -> list[Path]:
    roots: list[Path] = []

    env_root = os.environ.get("GIGSHIELD_REPO_ROOT")
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())

    roots.extend([start] + list(start.parents))

    cwd = Path.cwd().resolve()
    roots.extend([cwd] + list(cwd.parents))

    seen: set[Path] = set()
    ordered: list[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            ordered.append(r)
    return ordered


def resolve_repo_root(start: Path) -> Path | None:
    for candidate in _candidate_roots(start):
        if (candidate / "backend").is_dir() and (candidate / "data").is_dir():
            return candidate
    return None


def resolve_default_data_path(start: Path) -> Path:
    repo_root = resolve_repo_root(start)
    if repo_root:
        return repo_root / "data" / "ml_datasets" / DEFAULT_DATASET_NAME

    docker_data = Path("/data")
    if docker_data.is_dir():
        return docker_data / "ml_datasets" / DEFAULT_DATASET_NAME

    raise SystemExit(
        "Could not resolve repository root for default data path. "
        "Set GIGSHIELD_REPO_ROOT or pass --data-path explicitly."
    )


def validate_columns(df: pd.DataFrame) -> None:
    if TARGET_COL not in df.columns:
        raise ValueError(f"Dataset missing target column: {TARGET_COL}")


def encode_target(df: pd.DataFrame) -> pd.Series:
    payout_rates = pd.to_numeric(df[TARGET_COL], errors="coerce").round(2)
    if payout_rates.isna().any():
        raise ValueError("Found non-numeric or null payout_rate values.")

    invalid = sorted(set(payout_rates.unique()) - set(PAYOUT_RATE_TO_CLASS.keys()))
    if invalid:
        raise ValueError(
            "Invalid payout_rate values found. "
            f"Expected only {sorted(PAYOUT_RATE_TO_CLASS.keys())}, got {invalid}"
        )

    encoded = payout_rates.map(PAYOUT_RATE_TO_CLASS).astype(int)
    return encoded


def build_feature_matrix(df: pd.DataFrame, y: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    excluded = set(ID_COLS) | {TARGET_COL}
    candidate_cols = [c for c in df.columns if c not in excluded]
    X = df[candidate_cols]

    X = X.select_dtypes(include=[np.number]).copy()
    if X.shape[1] == 0:
        raise ValueError("No numeric feature columns available after exclusions.")

    return X, y


def _select_time_sort_columns(df: pd.DataFrame) -> list[str]:
    if "year" in df.columns and "week_of_year" in df.columns:
        return ["year", "week_of_year"]

    cols: list[str] = []
    for name in TIME_ORDER_CANDIDATES:
        if name in df.columns:
            cols.append(name)
    return cols[:1] if cols else []


def split_random(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, str]:
    stratify = y if y.nunique() > 1 and y.value_counts().min() >= 2 else None
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=test_size,
            random_state=random_state,
            stratify=stratify,
        )
        mode = "stratified" if stratify is not None else "unstratified"
    except ValueError:
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=test_size,
            random_state=random_state,
            stratify=None,
        )
        mode = "unstratified_fallback"

    return X_train, X_test, y_train, y_test, mode


def split_time_aware(
    df: pd.DataFrame,
    y: pd.Series,
    test_size: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, str]:
    ordered = df.copy()
    ordered["_encoded_target"] = y.values

    sort_cols = _select_time_sort_columns(ordered)
    if sort_cols:
        ordered = ordered.sort_values(sort_cols, ascending=True).reset_index(drop=True)
        ordering_mode = f"time_columns:{','.join(sort_cols)}"
    else:
        ordered = ordered.reset_index(drop=True)
        ordering_mode = "dataset_row_order"

    split_idx = int(len(ordered) * (1.0 - test_size))
    split_idx = max(1, min(split_idx, len(ordered) - 1))

    train_df = ordered.iloc[:split_idx].copy()
    test_df = ordered.iloc[split_idx:].copy()

    y_train = train_df.pop("_encoded_target").astype(int)
    y_test = test_df.pop("_encoded_target").astype(int)
    X_train, _ = build_feature_matrix(train_df, y_train)
    X_test, _ = build_feature_matrix(test_df, y_test)
    return X_train, X_test, y_train, y_test, ordering_mode


def _compute_class_weight_map(y_train: pd.Series) -> dict[int, float]:
    classes = np.array(sorted(y_train.unique()), dtype=int)
    weights = compute_class_weight(class_weight="balanced", classes=classes, y=y_train.to_numpy())
    return {int(cls): float(w) for cls, w in zip(classes, weights)}


def main() -> int:
    args = parse_args()
    if not (0.0 < args.test_size < 1.0):
        raise SystemExit("--test-size must be between 0 and 1.")

    script_path = Path(__file__).resolve()
    data_path = args.data_path.resolve() if args.data_path else resolve_default_data_path(script_path.parent)
    if not data_path.exists():
        raise SystemExit(f"Dataset not found: {data_path}")

    df = pd.read_csv(data_path)
    if df.empty:
        raise SystemExit("Dataset is empty.")

    validate_columns(df)
    y_encoded = encode_target(df)

    if args.time_split:
        X_train, X_test, y_train, y_test, ordering_mode = split_time_aware(df, y_encoded, args.test_size)
        split_mode = "time-aware"
    else:
        X, y = build_feature_matrix(df, y_encoded)
        X_train, X_test, y_train, y_test, ordering_mode = split_random(
            X, y, args.test_size, args.random_state
        )
        split_mode = "random"

    class_weight = _compute_class_weight_map(y_train)

    model = LGBMClassifier(
        objective="multiclass",
        num_class=3,
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=args.random_state,
        class_weight=class_weight,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    macro_f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)
    labels = [0, 1, 2]
    class_names = [f"{CLASS_TO_PAYOUT_RATE[l]:.2f}" for l in labels]

    cm = confusion_matrix(y_test, y_pred, labels=labels)
    report_text = classification_report(
        y_test,
        y_pred,
        labels=labels,
        target_names=class_names,
        zero_division=0,
    )
    report_dict = classification_report(
        y_test,
        y_pred,
        labels=labels,
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )

    artifact = {
        "model": model,
        "class_to_payout_rate": CLASS_TO_PAYOUT_RATE,  # 0->0.40, 1->0.70, 2->1.00
        "payout_rate_to_class": PAYOUT_RATE_TO_CLASS,  # 0.40->0, 0.70->1, 1.00->2
        "feature_columns": list(X_train.columns),
        "target_column": TARGET_COL,
        "identifier_columns": sorted(ID_COLS),
        "split_mode": split_mode,
        "time_ordering": ordering_mode,
        "class_weight": class_weight,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    args.model_path.parent.mkdir(parents=True, exist_ok=True)
    with args.model_path.open("wb") as f:
        pickle.dump(artifact, f)

    full_class_counts = y_encoded.value_counts().sort_index()
    decoded_distribution = {
        f"{CLASS_TO_PAYOUT_RATE[int(cls)]:.2f}": int(cnt)
        for cls, cnt in full_class_counts.items()
    }

    print("Training complete.")
    print(f"data_path={data_path}")
    print(f"dataset_shape={df.shape}")
    print(f"class_distribution={decoded_distribution}")
    print(f"split_mode={split_mode}")
    print(f"time_ordering={ordering_mode}")
    print(f"feature_list={list(X_train.columns)}")
    print(f"train_rows={len(X_train)} test_rows={len(X_test)}")
    print(f"accuracy={accuracy:.6f}")
    print(f"macro_f1={macro_f1:.6f}")

    support_summary = {
        cls_name: int(report_dict.get(cls_name, {}).get("support", 0))
        for cls_name in class_names
    }
    print(f"per_class_support={support_summary}")
    print("confusion_matrix:")
    print(cm)
    print("classification_report:")
    print(report_text)
    print(f"model_saved_to={args.model_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
