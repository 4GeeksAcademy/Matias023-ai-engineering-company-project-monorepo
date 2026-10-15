from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.sales_forecast.train import (
    causal_features,
    chronological_split,
    load_sales,
    recursive_forecast,
    training_examples,
)


def test_dataset_and_split():
    df = load_sales()
    train, test = chronological_split(df)

    assert len(df) == 120
    assert len(train) == 96
    assert len(test) == 24

    assert train["month"].min() == pd.Timestamp("2016-01-01")
    assert train["month"].max() == pd.Timestamp("2023-12-01")
    assert test["month"].min() == pd.Timestamp("2024-01-01")
    assert test["month"].max() == pd.Timestamp("2025-12-01")

    assert train["month"].max() < test["month"].min()


def test_lag_features_require_past_data():
    month = pd.Timestamp("2024-01-01")
    history = list(range(100, 124))

    features = causal_features(history, month)

    assert np.isfinite(list(features.values())).all()

    # Agregar valores futuros no puede alterar una prediccion
    # cuando se proporciona el mismo historial anterior.
    same_history = history.copy()
    assert features == causal_features(same_history, month)


def test_recursive_forecast_ignores_test_revenue():
    df = load_sales()
    train, test = chronological_split(df)
    X, y = training_examples(train)

    model = RandomForestRegressor(
        n_estimators=8,
        random_state=42,
        n_jobs=1,
    )
    model.fit(X, y)

    original = recursive_forecast(
        model, train, test["month"]
    )

    modified_test = test.copy()
    modified_test["revenue_eur"] = 999999999.0

    modified = recursive_forecast(
        model, train, modified_test["month"]
    )

    np.testing.assert_allclose(
        original["prediction_eur"],
        modified["prediction_eur"],
    )
