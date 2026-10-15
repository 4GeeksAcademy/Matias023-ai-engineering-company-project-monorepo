"""Diagnostico reproducible de regularizacion de TrackFlow."""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.sales_forecast.evaluate import (
    MODEL,
    evaluate_fold,
    temporal_folds,
)
from scripts.sales_forecast.train import (
    chronological_split,
    load_sales,
)

OUTPUT = ROOT / "data/eval"


def main():
    data = load_sales()
    train, test = chronological_split(data)
    assert len(train) == 96 and len(test) == 24

    reference = joblib.load(MODEL)
    folds = temporal_folds(train)
    rows = []

    print("=== EXPERIMENTO DE REGULARIZACION ===")

    for leaf in (2, 4, 6):
        for fold_number, (tr, va) in enumerate(folds, 1):
            model = clone(reference)
            model.set_params(min_samples_leaf=leaf)

            train_error, val_error, _, _ = evaluate_fold(
                train.iloc[tr].copy(),
                train.iloc[va].copy(),
                model,
            )

            rows.append({
                "min_samples_leaf": leaf,
                "fold": fold_number,
                "train_rmse_eur": train_error["rmse"],
                "validation_rmse_eur": val_error["rmse"],
                "validation_mae_eur": val_error["mae"],
            })

    results = pd.DataFrame(rows)

    summary = results.groupby("min_samples_leaf").agg(
        cv_rmse_mean=("validation_rmse_eur", "mean"),
        cv_rmse_std=("validation_rmse_eur", "std"),
        cv_mae_mean=("validation_mae_eur", "mean"),
        train_rmse_mean=("train_rmse_eur", "mean"),
    ).reset_index()

    original = summary.loc[
        summary["min_samples_leaf"] == 2
    ].iloc[0]

    best = summary.loc[
        summary["cv_rmse_mean"].idxmin()
    ]

    improvement = 100 * (
        1 - best["cv_rmse_mean"] / original["cv_rmse_mean"]
    )

    previous = json.loads(
        (OUTPUT / "regression_cv_summary.json").read_text()
    )

    assert np.isclose(
        original["cv_rmse_mean"],
        previous["validation_rmse_eur"]["mean"],
        rtol=0.00001,
    ), "El experimento no reproduce el modelo original"

    assert len(results) == 15
    assert results.groupby("min_samples_leaf")["fold"].nunique().eq(5).all()

    summary.to_csv(
        OUTPUT / "regularization_comparison.csv",
        index=False,
        float_format="%.6f",
    )

    if int(best["min_samples_leaf"]) != 2 and improvement >= 1:
        recommendation = (
            f"Probar min_samples_leaf={int(best['min_samples_leaf'])} "
            f"en lugar de 2. La validacion temporal muestra "
            f"una reduccion del RMSE medio de {improvement:.2f}%. "
            "Confirmar estabilidad antes de sustituir el modelo."
        )
    else:
        recommendation = (
            "Conservar min_samples_leaf=2 por ahora: aumentar "
            "la regularizacion no demuestra una mejora suficiente "
            "en estos folds. Como siguiente experimento, entrenar "
            "un pronosticador directo a 12 meses y compararlo "
            "contra la estrategia recursiva con los mismos "
            "cortes temporales y RMSE."
        )

    table = "\n".join(
        "| {leaf} | {rmse:,.2f} | {std:,.2f} | {mae:,.2f} |".format(
            leaf=int(row["min_samples_leaf"]),
            rmse=row["cv_rmse_mean"],
            std=row["cv_rmse_std"],
            mae=row["cv_mae_mean"],
        )
        for _, row in summary.iterrows()
    )

    report = f"""# Evaluacion formal del modelo de regresion - TrackFlow

## Objetivo

Evaluar la estabilidad y capacidad de generalizacion del
modelo Random Forest de prediccion de ingresos mensuales,
sin utilizar el periodo externo de prueba para seleccionar
hiperparametros.

## Contexto y datos

- Dataset: `data/raw/trackflow_sales.csv`.
- Objetivo: `revenue_eur`, mercado consolidado.
- Periodo de entrenamiento: 2016-2023 (96 meses).
- Prueba externa reservada: 2024-2025 (24 meses).
- Modelo: RandomForestRegressor de crecimiento interanual.
- Validacion: TimeSeriesSplit con 5 folds de 12 meses.
- Semilla del modelo: 42.

Los folds conservan el orden cronologico. Las variables
de entrenamiento se construyen solo con su historia.
Las predicciones de validacion son recursivas y nunca
incorporan los ingresos reales del fold como nuevos lags.

## Validacion cruzada del modelo original

| Metrica | Media EUR | Desviacion estandar EUR |
|---|---:|---:|
| MAE entrenamiento | {previous['train_mae_eur']['mean']:,.2f} | {previous['train_mae_eur']['std']:,.2f} |
| MAE validacion | {previous['validation_mae_eur']['mean']:,.2f} | {previous['validation_mae_eur']['std']:,.2f} |
| RMSE entrenamiento | {previous['train_rmse_eur']['mean']:,.2f} | {previous['train_rmse_eur']['std']:,.2f} |
| RMSE validacion | {previous['validation_rmse_eur']['mean']:,.2f} | {previous['validation_rmse_eur']['std']:,.2f} |
| RMSE baseline estacional | {previous['baseline_rmse_eur']['mean']:,.2f} | {previous['baseline_rmse_eur']['std']:,.2f} |

El baseline repite las ventas del ultimo año conocido
para los doce meses de validacion.

## Curva de aprendizaje

![Curva de aprendizaje](regression_learning_curve.png)

La validacion cambia al aumentar el historial de
entrenamiento, pero no mejora de forma monotona.
Existe una brecha importante entre los errores.

**Advertencia metodologica:** el RMSE de entrenamiento
es in-sample de un paso y el de validacion es un
pronostico recursivo de doce meses. Por ello, la
diferencia entre curvas no permite atribuir por si sola
toda la brecha al sobreajuste.

## Diagnostico

**Clasificacion: indicios de overfitting (sobreajuste)
o dificultad de generalizacion a horizontes largos.**

La brecha entrenamiento-validacion justifica investigar
sobreajuste, pero el componente de acumulacion de
errores impide confirmarlo exclusivamente con esta curva.

No se observa un subajuste generalizado: el modelo
supera al baseline en el RMSE medio de validacion.

El aumento de datos disponibles tampoco garantiza una
mejora continua; debe evaluarse la estabilidad temporal.

## Experimento de regularizacion

Se mantuvieron los mismos folds, features y criterio
de evaluacion; solo cambio `min_samples_leaf`.

| min_samples_leaf | RMSE medio EUR | Desv. EUR | MAE medio EUR |
|---:|---:|---:|---:|
{table}

## Accion correctiva especifica

{recommendation}

No se modifica automaticamente el modelo anterior.
La eleccion de hiperparametros se basa solo en los
folds de entrenamiento, no en el periodo 2024-2025.

## Justificacion de negocio

Para TrackFlow, una subestimacion de ingresos/volumen
podria reducir la capacidad planificada ante picos
de comercio electronico. Una sobreestimacion podria
provocar sobreasignacion de recursos.

El contexto no proporciona costos monetarios de estos
dos tipos de error; por eso no se afirma que uno sea
siempre mas caro. MAE es facil de interpretar en euros,
mientras que RMSE penaliza especialmente los errores
grandes durante periodos de alta actividad.

**Metrica principal: RMSE**, por el impacto de errores
grandes en la planificacion. MAE se reporta como
complemento interpretable.

## Evidencias y pruebas

- `regression_cv_folds.csv`: errores por fold.
- `regression_cv_summary.json`: media y desviacion.
- `regression_learning_curve.png`: curva temporal.
- `regularization_comparison.csv`: experimento.
- `tests/pipelines/test_regression_model_eval.py`:
  orden temporal y ausencia de fuga entre folds.

## Conclusion

El modelo supera al baseline, pero presenta variabilidad
entre periodos y una brecha de generalizacion que merece
investigacion. No se recomienda promocion automatica a
staging sin evaluar la accion correctiva y confirmar
las condiciones operacionales.
"""

    (OUTPUT / "evaluation_report.md").write_text(
        report, encoding="utf-8"
    )

    print("\n=== COMPARACION ===")
    print(summary.to_string(index=False))

    print("\n=== ACCION CORRECTIVA ===")
    print(recommendation)

    print("\nPASS: informe tecnico y experimento guardados")


if __name__ == "__main__":
    main()
