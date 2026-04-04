#!/usr/bin/env python
"""
Train ML Use Case 3 model (Disruption Duration Estimation).

Target:
  affected_hours

Identifiers dropped:
  event_id, zone_id

Feature policy:
  all remaining numeric columns after preprocessing.
  If `season` string exists, convert to numeric `season_index`,
  keep `season_index`, and exclude original `season` string.

Split modes:
  - default: random split
  - --time-split: sort by natural temporal order column when available,
    else fallback to dataset row order.

Saves:
  models/disruption_duration_model.pkl
"""

from __future__ import annotations

import argparse
import os
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split


TARGET_COL = "affected_hours"
ID_COLS = {"event_id", "zone_id"}
DEFAULT_MODEL_PATH = Path("models/disruption_duration_model.pkl")
SEASON_TO_INDEX = {"dry": 1, "pre_monsoon": 2, "monsoon": 3, "post_monsoon": 4}

# Preferred temporal columns for --time-split if present.
TIME_ORDER_CANDIDATES = [
    "event_start_ts",
    "start_timestamp",
    "start_time",
    "started_at",
    "timestamp",
    "year",
    "week_of_year",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train disruption duration LightGBM model.")
    parser.add_argument(
        "--data-path",
        type=Path,
        default=None,
        help="Path to dataset CSV. Defaults to <repo>/data/ml_datasets/ds_disruption_duration_event.csv.",
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
        return repo_root / "data" / "ml_datasets" / "ds_disruption_duration_event.csv"

    docker_data = Path("/data")
    if docker_data.is_dir():
        return docker_data / "ml_datasets" / "ds_disruption_duration_event.csv"

    raise SystemExit(
        "Could not resolve repository root for default data path. "
        "Set GIGSHIELD_REPO_ROOT or pass --data-path explicitly."
    )


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()

    if "season" in work.columns:
        # Keep behavior deterministic for unknown season values.
        work["season_index"] = (
            work["season"]
            .astype(str)
            .str.strip()
            .str.lower()
            .map(SEASON_TO_INDEX)
            .fillna(0)
            .astype(int)
        )

    return work


def validate_columns(df: pd.DataFrame) -> None:
    if TARGET_COL not in df.columns:
        raise ValueError(f"Dataset missing target column: {TARGET_COL}")


def build_feature_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    y = df[TARGET_COL]

    excluded = set(ID_COLS) | {TARGET_COL, "season"}
    candidate_cols = [c for c in df.columns if c not in excluded]
    X = df[candidate_cols]

    # Keep only numeric columns as requested.
    X = X.select_dtypes(include=[np.number]).copy()
    if X.shape[1] == 0:
        raise ValueError("No numeric feature columns available after preprocessing.")

    return X, y


def _select_time_sort_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for name in TIME_ORDER_CANDIDATES:
        if name in df.columns:
            cols.append(name)

    # Prefer year+week pair when both exist.
    if "year" in df.columns and "week_of_year" in df.columns:
        return ["year", "week_of_year"]

    return cols[:1] if cols else []


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
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, str]:
    sort_cols = _select_time_sort_columns(df)

    if sort_cols:
        ordered = df.sort_values(sort_cols, ascending=True).reset_index(drop=True)
        ordering_mode = f"time_columns:{','.join(sort_cols)}"
    else:
        ordered = df.reset_index(drop=True)
        ordering_mode = "dataset_row_order"

    split_idx = int(len(ordered) * (1.0 - test_size))
    split_idx = max(1, min(split_idx, len(ordered) - 1))

    train_df = ordered.iloc[:split_idx]
    test_df = ordered.iloc[split_idx:]

    X_train, y_train = build_feature_matrix(train_df)
    X_test, y_test = build_feature_matrix(test_df)
    return X_train, X_test, y_train, y_test, ordering_mode


def main() -> int:
    args = parse_args()
    if not (0.0 < args.test_size < 1.0):
        raise SystemExit("--test-size must be between 0 and 1.")

    script_path = Path(__file__).resolve()
    data_path = args.data_path.resolve() if args.data_path else resolve_default_data_path(script_path.parent)
    if not data_path.exists():
        raise SystemExit(f"Dataset not found: {data_path}")

    raw_df = pd.read_csv(data_path)
    if raw_df.empty:
        raise SystemExit("Dataset is empty.")

    df = preprocess(raw_df)
    validate_columns(df)

    if args.time_split:
        X_train, X_test, y_train, y_test, ordering_mode = split_time_aware(df, args.test_size)
        split_mode = "time-aware"
    else:
        X, y = build_feature_matrix(df)
        X_train, X_test, y_train, y_test = split_random(X, y, args.test_size, args.random_state)
        split_mode = "random"
        ordering_mode = "n/a"

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
    print(f"data_path={data_path}")
    print(f"dataset_shape={df.shape}")
    print(f"split_mode={split_mode}")
    print(f"time_ordering={ordering_mode}")
    print(f"feature_list={list(X_train.columns)}")
    print(f"train_rows={len(X_train)} test_rows={len(X_test)}")
    print(f"MAE={mae:.6f}")
    print(f"RMSE={rmse:.6f}")
    print(f"model_saved_to={args.model_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
