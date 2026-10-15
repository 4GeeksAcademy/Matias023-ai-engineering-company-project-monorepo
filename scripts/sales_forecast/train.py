"""Pronostico mensual TrackFlow, sin acceso a ingresos futuros."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import normaltest
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/raw/trackflow_sales.csv"
OUTPUT = Path(__file__).resolve().parent / "artifacts"
SEED = 42


def load_sales(path: Path = DATA) -> pd.DataFrame:
    df = pd.read_csv(path)

    expected_columns = [
        "month",
        "revenue_eur",
        "shipments_processed",
        "avg_revenue_per_shipment_eur",
        "market",
    ]
    if list(df.columns) != expected_columns:
        raise ValueError("Columnas inesperadas")

    df["month"] = pd.to_datetime(
        df["month"], format="%Y-%m-%d", errors="raise"
    )

    if df.isna().any().any():
        raise ValueError("Hay valores nulos")

    if not df["market"].eq("consolidated").all():
        raise ValueError("El modelo requiere consolidated")

    for column in [
        "revenue_eur",
        "shipments_processed",
        "avg_revenue_per_shipment_eur",
    ]:
        if not np.isfinite(df[column]).all():
            raise ValueError(f"Valores no finitos: {column}")
        if not df[column].gt(0).all():
            raise ValueError(f"Valores no positivos: {column}")

    expected_dates = pd.date_range(
        "2016-01-01", "2025-12-01", freq="MS"
    )

    if len(df) != 120 or not np.array_equal(
        df["month"].to_numpy(), expected_dates.to_numpy()
    ):
        raise ValueError("Se requieren 120 meses consecutivos")

    return df


def chronological_split(df: pd.DataFrame):
    train = df.loc[df["month"] < "2024-01-01"].copy()
    test = df.loc[df["month"] >= "2024-01-01"].copy()

    if len(train) != 96 or len(test) != 24:
        raise ValueError("Split temporal incorrecto")

    if train["month"].max() >= test["month"].min():
        raise ValueError("Fuga temporal entre train y test")

    return train, test


def causal_features(history, month):
    """Usa exclusivamente valores anteriores al mes objetivo."""
    if len(history) < 24:
        raise ValueError("Se necesitan 24 meses previos")

    y = np.asarray(history, dtype=float)
    recent = y[-3:]
    previous_year = y[-15:-12]

    return {
        "month_sin": float(
            np.sin(2 * np.pi * month.month / 12)
        ),
        "month_cos": float(
            np.cos(2 * np.pi * month.month / 12)
        ),
        "nov_dec": float(month.month in (11, 12)),
        "february": float(month.month == 2),
        "yoy_last_month": float(
            np.log(y[-1] / y[-13])
        ),
        "yoy_previous_year": float(
            np.log(y[-12] / y[-24])
        ),
        "yoy_recent_3": float(
            np.log(recent.mean() / previous_year.mean())
        ),
        "momentum": float(
            np.log(y[-1] / recent.mean())
        ),
        "seasonal_index": float(
            y[-12] / y[-24:-12].mean()
        ),
        "volatility_3": float(
            recent.std() / recent.mean()
        ),
    }


def training_examples(train):
    values = train["revenue_eur"].to_numpy(dtype=float)
    months = train["month"].tolist()

    features = []
    targets = []

    for t in range(24, len(train)):
        features.append(
            causal_features(values[:t].tolist(), months[t])
        )

        # Regresion sobre crecimiento interanual.
        targets.append(
            float(np.log(values[t] / values[t - 12]))
        )

    return pd.DataFrame(features), np.asarray(targets)


def recursive_forecast(model, train, test_months):
    """No utiliza ingresos reales de 2024 ni 2025."""
    history = train["revenue_eur"].astype(float).tolist()
    records = []

    for month in test_months:
        features = pd.DataFrame([
            causal_features(history, month)
        ])

        growth = float(model.predict(features)[0])

        tree_values = np.asarray([
            tree.predict(features.to_numpy())[0]
            for tree in model.estimators_
        ])

        last_year = history[-12]

        prediction = float(
            last_year * np.exp(growth)
        )

        lower = float(
            last_year * np.exp(
                np.quantile(tree_values, 0.10)
            )
        )

        upper = float(
            last_year * np.exp(
                np.quantile(tree_values, 0.90)
            )
        )

        records.append({
            "month": month,
            "prediction_eur": prediction,
            "tree_p10_eur": lower,
            "tree_p90_eur": upper,
        })

        # Solo se agrega la prediccion, nunca el valor real.
        history.append(prediction)

    return pd.DataFrame(records)


def calculate_psi(train_values, test_values):
    """PSI de ingresos consolidados, no mezcla geográfica."""
    boundaries = np.unique(
        np.quantile(train_values, np.linspace(0, 1, 6))
    )[1:-1]

    bins = np.r_[-np.inf, boundaries, np.inf]

    a = np.histogram(train_values, bins=bins)[0].astype(float)
    b = np.histogram(test_values, bins=bins)[0].astype(float)

    a = (a + 0.5) / (a.sum() + 0.5 * len(a))
    b = (b + 0.5) / (b.sum() + 0.5 * len(b))

    return float(np.sum((b - a) * np.log(b / a)))


def normalized_gini(actual, predicted):
    """Gini normalizado de ordenamiento para regresion."""

    def raw_gini(values, scores):
        ordered = values[
            np.argsort(-scores, kind="stable")
        ]
        n = len(ordered)
        return float(
            (
                np.cumsum(ordered).sum()
                / ordered.sum()
                - (n + 1) / 2
            ) / n
        )

    ideal = raw_gini(actual, actual)

    if ideal <= 0:
        return 0.0

    return float(
        raw_gini(actual, predicted) / ideal
    )


def evaluate(train, test, forecast):
    actual = test["revenue_eur"].to_numpy(dtype=float)
    predicted = forecast["prediction_eur"].to_numpy(dtype=float)

    errors = actual - predicted
    mse = float(mean_squared_error(actual, predicted))
    k2, k2_p = normaltest(errors)

    metrics = {
        "train_period": "2016-01 to 2023-12",
        "test_period": "2024-01 to 2025-12",
        "train_rows": 96,
        "test_rows": 24,
        "effective_training_examples": 72,
        "algorithm": "RandomForestRegressor",
        "target_transformation": "log(year_over_year_growth)",
        "forecast_strategy": "recursive_24_months",
        "mse_eur2": mse,
        "rmse_eur": float(np.sqrt(mse)),
        "rmse_pct_mean_test_revenue": float(
            100 * np.sqrt(mse) / actual.mean()
        ),
        "mae_eur": float(
            mean_absolute_error(actual, predicted)
        ),
        "r2_score": float(
            r2_score(actual, predicted)
        ),
        "psi_revenue_train_vs_test": calculate_psi(
            train["revenue_eur"].to_numpy(dtype=float),
            actual,
        ),
        "gini_normalized_regression": normalized_gini(
            actual, predicted
        ),
        "k2_residual_normality": float(k2),
        "k2_p_value": float(k2_p),
        "k2_definition_status": (
            "Provisional: D'Agostino-Pearson K2 sobre residuos. "
            "Confirmar interpretacion con profesor."
        ),
        "psi_limitation": (
            "Solo compara ingresos consolidados. "
            "No permite evaluar mezcla US/Espana."
        ),
        "prediction_range_limitation": (
            "P10-P90 de dispersion entre arboles. "
            "No es un intervalo calibrado."
        ),
    }

    numeric = [
        value for value in metrics.values()
        if isinstance(value, (float, int))
    ]
    if not np.isfinite(numeric).all():
        raise ValueError("Se encontraron metricas no finitas")

    return metrics


def main():
    df = load_sales()
    train, test = chronological_split(df)

    X_train, y_train = training_examples(train)

    model = RandomForestRegressor(
        n_estimators=250,
        min_samples_leaf=2,
        random_state=SEED,
        n_jobs=2,
    )

    model.fit(X_train, y_train)

    forecast = recursive_forecast(
        model, train, test["month"]
    )

    assert len(forecast) == 24
    assert forecast["prediction_eur"].gt(0).all()

    forecast["actual_eur"] = (
        test["revenue_eur"].to_numpy()
    )

    metrics = evaluate(train, test, forecast)

    OUTPUT.mkdir(parents=True, exist_ok=True)

    joblib.dump(
        model,
        OUTPUT / "random_forest_yoy.joblib",
    )

    forecast.to_csv(
        OUTPUT / "forecast_2024_2025.csv",
        index=False,
        float_format="%.2f",
    )

    (OUTPUT / "metrics.json").write_text(
        json.dumps(
            metrics, indent=2, ensure_ascii=False
        ) + "\n",
        encoding="utf-8",
    )

    fig, ax = plt.subplots(figsize=(13, 5.5))

    ax.plot(
        train["month"],
        train["revenue_eur"],
        label="Entrenamiento 2016-2023",
        color="gray",
        alpha=0.65,
    )

    ax.plot(
        test["month"],
        test["revenue_eur"],
        label="Ventas reales 2024-2025",
        color="black",
        linewidth=2,
    )

    ax.plot(
        forecast["month"],
        forecast["prediction_eur"],
        label="Prediccion Random Forest",
        color="tab:blue",
    )

    ax.fill_between(
        forecast["month"],
        forecast["tree_p10_eur"],
        forecast["tree_p90_eur"],
        alpha=0.2,
        color="tab:blue",
        label="Dispersion entre arboles P10-P90",
    )

    ax.axvline(
        pd.Timestamp("2024-01-01"),
        linestyle="--",
        color="tab:red",
        alpha=0.6,
    )

    ax.set(
        title="TrackFlow: pronostico de ingresos",
        xlabel="Mes",
        ylabel="Ingresos (EUR)",
    )

    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(
        OUTPUT / "forecast_vs_actual.png",
        dpi=160,
    )
    plt.close(fig)

    print("=== MODELO ENTRENADO ===")
    print("Train: 2016-2023 (96 meses)")
    print("Test: 2024-2025 (24 meses)")
    print("Ejemplos supervisados:", len(X_train))

    for key in [
        "mse_eur2",
        "rmse_eur",
        "rmse_pct_mean_test_revenue",
        "r2_score",
        "psi_revenue_train_vs_test",
        "gini_normalized_regression",
        "k2_residual_normality",
        "k2_p_value",
    ]:
        print(f"{key}: {metrics[key]:.6f}")

    print("Artefactos:", OUTPUT)


if __name__ == "__main__":
    main()
