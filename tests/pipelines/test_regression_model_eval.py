import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.sales_forecast.evaluate import temporal_folds
from scripts.sales_forecast.train import (
    chronological_split,
    load_sales,
    training_examples,
)


def test_five_folds_preserve_chronology():
    train, external = chronological_split(load_sales())
    splits = temporal_folds(train)

    assert len(splits) == 5
    assert len(external) == 24

    expected_years = list(range(2019, 2024))
    observed_years = []

    for tr, va in splits:
        assert tr.max() < va.min()
        assert len(va) == 12
        assert not set(tr).intersection(set(va))

        observed_years.append(
            train.iloc[va]["month"].iloc[0].year
        )

        assert train.iloc[va]["month"].max() < (
            pd.Timestamp("2024-01-01")
        )

    assert observed_years == expected_years


def test_future_fold_values_cannot_change_features():
    train, _ = chronological_split(load_sales())

    for tr, va in temporal_folds(train):
        before = train.iloc[tr].copy()
        X_before, y_before = training_examples(before)

        changed = train.copy()
        changed.iloc[
            va,
            changed.columns.get_loc("revenue_eur")
        ] *= 10

        X_after, y_after = training_examples(
            changed.iloc[tr].copy()
        )

        pd.testing.assert_frame_equal(X_before, X_after)
        np.testing.assert_allclose(y_before, y_after)


def test_cv_does_not_include_external_test():
    full = load_sales()
    train, external = chronological_split(full)

    for tr, va in temporal_folds(train):
        assert tr.max() < 96
        assert va.max() < 96
        assert train.iloc[va]["month"].max() < (
            external["month"].min()
        )
