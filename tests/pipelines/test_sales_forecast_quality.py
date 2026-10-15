from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.sales_forecast.train import (
    chronological_split,
    load_sales,
    recursive_forecast,
    training_examples,
)

ARTIFACTS = ROOT / "scripts/sales_forecast/artifacts"


def test_training_features_exclude_current_target():
    train, _ = chronological_split(load_sales())
    original_x, original_y = training_examples(train)

    modified = train.copy()
    last_index = modified.index[-1]

    modified.loc[last_index, "revenue_eur"] *= 1.5

    altered_x, altered_y = training_examples(modified)

    assert len(original_x) == len(original_y) == 72

    pd.testing.assert_frame_equal(
        original_x, altered_x
    )

    np.testing.assert_allclose(
        original_y[:-1], altered_y[:-1]
    )

    assert original_y[-1] != altered_y[-1]


def test_saved_model_reproduces_forecast():
    train, test = chronological_split(load_sales())

    model = joblib.load(
        ARTIFACTS / "random_forest_yoy.joblib"
    )

    recalculated = recursive_forecast(
        model, train, test["month"]
    )

    saved = pd.read_csv(
        ARTIFACTS / "forecast_2024_2025.csv"
    )

    np.testing.assert_allclose(
        recalculated["prediction_eur"].to_numpy(),
        saved["prediction_eur"].to_numpy(),
        atol=0.006,
        rtol=0,
    )


def test_missing_month_is_rejected(tmp_path):
    df = load_sales()
    invalid = tmp_path / "missing_month.csv"

    df.drop(index=10).to_csv(invalid, index=False)

    with pytest.raises(ValueError, match="120 meses"):
        load_sales(invalid)
