#!/usr/bin/env python
"""
Train ML Use Case 1 model (Disruption Frequency Estimation).

Target:
  seasonal_disruption_days

Features:
  all columns except:
    - zone_id
    - year
    - week_of_year
    - seasonal_disruption_days (target)

Split modes:
  - default: random train/test split
  - --time-split: sort by (year, week_of_year), train on earlier rows, test on later rows

Saves:
  models/disruption_frequency_model.pkl
"""

from __future__ import annotations

import argparse
import pickle
import os
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split


DEFAULT_MODEL_PATH = Path("models/disruption_frequency_model.pkl")
TARGET_COL = "seasonal_disruption_days"
DROP_FEATURE_COLS = {"zone_id", "year", "week_of_year"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train disruption frequency LightGBM model.")
    parser.add_argument(
        "--data-path",
        type=Path,
        default=None,
        help="Path to dataset CSV. Defaults to <repo>/data/ml_datasets/ds_disruption_frequency_zone_week.csv.",
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
        help="Use time-aware split: train on earlier weeks, test on later weeks.",
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
        return repo_root / "data" / "ml_datasets" / "ds_disruption_frequency_zone_week.csv"

    docker_data = Path("/data")
    if docker_data.is_dir():
        return docker_data / "ml_datasets" / "ds_disruption_frequency_zone_week.csv"

    raise SystemExit(
        "Could not resolve repository root for default data path. "
        "Set GIGSHIELD_REPO_ROOT or pass --data-path explicitly."
    )


def validate_columns(df: pd.DataFrame) -> None:
    required = {TARGET_COL, "year", "week_of_year"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dataset missing required columns: {sorted(missing)}")


def build_feature_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    y = df[TARGET_COL]
    feature_cols = [
        c for c in df.columns
        if c not in DROP_FEATURE_COLS and c != TARGET_COL
    ]
    if not feature_cols:
        raise ValueError("No feature columns remain after exclusions.")
    X = df[feature_cols]
    return X, y


def split_random(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    return train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
    )


def split_time_aware(
    df: pd.DataFrame,
    test_size: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    sorted_df = df.sort_values(["year", "week_of_year"], ascending=[True, True]).reset_index(drop=True)
    split_idx = int(len(sorted_df) * (1.0 - test_size))
    split_idx = max(1, min(split_idx, len(sorted_df) - 1))

    train_df = sorted_df.iloc[:split_idx]
    test_df = sorted_df.iloc[split_idx:]

    X_train, y_train = build_feature_matrix(train_df)
    X_test, y_test = build_feature_matrix(test_df)
    return X_train, X_test, y_train, y_test


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

    if args.time_split:
        X_train, X_test, y_train, y_test = split_time_aware(df, args.test_size)
        split_mode = "time-aware"
    else:
        X, y = build_feature_matrix(df)
        X_train, X_test, y_train, y_test = split_random(
            X, y, args.test_size, args.random_state
        )
        split_mode = "random"

    model = LGBMRegressor(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=args.random_state,
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    rmse = float(np.sqrt(mean_squared_error(y_test, preds)))

    args.model_path.parent.mkdir(parents=True, exist_ok=True)
    with args.model_path.open("wb") as f:
        pickle.dump(model, f)

    print("Training complete.")
    print(f"split_mode={split_mode}")
    print(f"rows_total={len(df)} train_rows={len(X_train)} test_rows={len(X_test)}")
    print(f"feature_count={X_train.shape[1]}")
    print(f"features={list(X_train.columns)}")
    print(f"MAE={mae:.6f}")
    print(f"RMSE={rmse:.6f}")
    print(f"data_path={data_path}")
    print(f"model_saved_to={args.model_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
