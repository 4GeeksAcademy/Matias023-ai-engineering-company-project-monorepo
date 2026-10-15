"""Evaluacion temporal del modelo de ingresos TrackFlow."""

import json
import sys
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.sales_forecast.train import (
    chronological_split,
    load_sales,
    recursive_forecast,
    training_examples,
)

OUTPUT = ROOT / "data/eval"
MODEL = ROOT / "scripts/sales_forecast/artifacts/random_forest_yoy.joblib"


def temporal_folds(train):
    if len(train) != 96:
        raise ValueError("Se esperan 96 meses de entrenamiento")

    splitter = TimeSeriesSplit(n_splits=5, test_size=12)
    splits = list(splitter.split(train))

    for train_idx, val_idx in splits:
        assert len(val_idx) == 12
        assert len(train_idx) >= 36
        assert train_idx[-1] < val_idx[0]
        assert val_idx[0] == train_idx[-1] + 1
        assert np.all(np.diff(train_idx) == 1)
        assert np.all(np.diff(val_idx) == 1)

    return splits


def errors(actual, predicted):
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(
            mean_squared_error(actual, predicted)
        )),
    }


def evaluate_fold(train, validation, reference_model):
    X, y = training_examples(train)

    model = clone(reference_model)
    model.fit(X, y)

    train_values = train["revenue_eur"].to_numpy(dtype=float)

    # Entrenamiento: prediccion in-sample de un paso.
    train_actual = train_values[24:]
    train_previous_year = train_values[12:-12]

    train_pred = train_previous_year * np.exp(
        model.predict(X)
    )

    # Validacion: pronostico recursivo de 12 meses.
    # No se utilizan ingresos reales del fold de validacion.
    forecast = recursive_forecast(
        model, train, validation["month"]
    )

    validation_actual = validation[
        "revenue_eur"
    ].to_numpy(dtype=float)

    validation_pred = forecast[
        "prediction_eur"
    ].to_numpy(dtype=float)

    # Baseline estacional: repetir el ultimo año conocido.
    baseline = train_values[-12:]

    return (
        errors(train_actual, train_pred),
        errors(validation_actual, validation_pred),
        errors(validation_actual, baseline),
        len(X),
    )


def main():
    data = load_sales()
    train, external_test = chronological_split(data)

    assert len(train) == 96
    assert len(external_test) == 24

    reference_model = joblib.load(MODEL)

    rows = []

    for fold, (train_idx, val_idx) in enumerate(
        temporal_folds(train), start=1
    ):
        fold_train = train.iloc[train_idx].copy()
        fold_val = train.iloc[val_idx].copy()

        train_error, val_error, base_error, examples = (
            evaluate_fold(
                fold_train, fold_val, reference_model
            )
        )

        row = {
            "fold": fold,
            "train_months": len(fold_train),
            "train_examples": examples,
            "train_end": str(
                fold_train["month"].max().date()
            ),
            "validation_start": str(
                fold_val["month"].min().date()
            ),
            "validation_end": str(
                fold_val["month"].max().date()
            ),
            "train_mae_eur": train_error["mae"],
            "train_rmse_eur": train_error["rmse"],
            "validation_mae_eur": val_error["mae"],
            "validation_rmse_eur": val_error["rmse"],
            "baseline_rmse_eur": base_error["rmse"],
        }

        rows.append(row)

        print(
            f"FOLD {fold}: "
            f"train={len(fold_train)} meses | "
            f"validacion={row['validation_start'][:7]} "
            f"a {row['validation_end'][:7]} | "
            f"RMSE train={train_error['rmse']:,.2f} | "
            f"RMSE val={val_error['rmse']:,.2f} EUR"
        )

    results = pd.DataFrame(rows)

    def aggregate(column):
        values = results[column].to_numpy(dtype=float)
        return {
            "mean": float(values.mean()),
            "std": float(values.std(ddof=1)),
        }

    summary = {
        "strategy": "TimeSeriesSplit",
        "folds": 5,
        "validation_horizon_months": 12,
        "external_test_excluded": "2024-2025",
        "train_rmse_eur": aggregate("train_rmse_eur"),
        "validation_rmse_eur": aggregate(
            "validation_rmse_eur"
        ),
        "train_mae_eur": aggregate("train_mae_eur"),
        "validation_mae_eur": aggregate(
            "validation_mae_eur"
        ),
        "baseline_rmse_eur": aggregate(
            "baseline_rmse_eur"
        ),
        "comparison_limitation": (
            "Train is in-sample one-step fitting; "
            "validation is recursive 12-month forecasting. "
            "The errors are not fully equivalent."
        ),
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)

    results.to_csv(
        OUTPUT / "regression_cv_folds.csv",
        index=False,
        float_format="%.6f",
    )

    (OUTPUT / "regression_cv_summary.json").write_text(
        json.dumps(
            summary, indent=2, ensure_ascii=False
        ) + "\n",
        encoding="utf-8",
    )

    fig, ax = plt.subplots(figsize=(10, 6))

    x = results["train_months"]

    ax.plot(
        x,
        results["train_rmse_eur"],
        marker="o",
        label="Entrenamiento (in-sample)",
    )
    ax.plot(
        x,
        results["validation_rmse_eur"],
        marker="o",
        label="Validacion (12 meses recursivos)",
    )
    ax.plot(
        x,
        results["baseline_rmse_eur"],
        marker="o",
        linestyle="--",
        label="Baseline estacional",
    )

    ax.set(
        title="TrackFlow - Curva de aprendizaje temporal",
        xlabel="Meses disponibles para entrenamiento",
        ylabel="RMSE (EUR)",
    )

    ax.grid(alpha=0.2)
    ax.legend()
    fig.tight_layout()

    fig.savefig(
        OUTPUT / "regression_learning_curve.png",
        dpi=160,
    )
    plt.close(fig)

    print("\n=== RESUMEN CV (MEDIA +/- DESV. ESTANDAR) ===")

    for key in [
        "train_mae_eur",
        "validation_mae_eur",
        "train_rmse_eur",
        "validation_rmse_eur",
        "baseline_rmse_eur",
    ]:
        stats = summary[key]
        print(
            f"{key}: "
            f"{stats['mean']:,.2f} +/- "
            f"{stats['std']:,.2f} EUR"
        )

    print("\nPASS: 5 folds cronologicos")
    print("PASS: test externo 2024-2025 excluido")
    print("PASS: curva y metricas guardadas")


if __name__ == "__main__":
    main()
