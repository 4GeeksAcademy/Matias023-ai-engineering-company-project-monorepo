# Pipeline semanal de rendimiento por almacén/cliente

## Propósito y audiencia

Este pipeline de Prefect calcula un informe operativo semanal para operaciones, responsables de almacén y equipos de cuentas de clientes. Produce una fila por **warehouse + client_id + week_start** en `reporting.weekly_warehouse_client_performance`.

La fuente es `telemetry_events`, que el pipeline solo lee. El destino es la tabla de reporting, mantenida mediante UPSERT idempotente con warehouse, cliente y semana como clave. Reejecutar una semana actualiza sus valores calculados sin duplicar filas del mismo grano.

## Contrato y métricas

Solo son contractuales estos tipos de evento exactos:

- `inbound_order_created`
- `outbound_order_created`
- `stock_threshold_triggered`
- `inventory_discrepancy_detected`

Los valores canónicos de almacén son `los_angeles` y `zaragoza`. Los cuatro KPIs son `inbound_units_count`, `outbound_orders_count`, `stockout_events_count` y `discrepancy_rate`. El campo de soporte `discrepancy_events_count` **no es un quinto KPI**. La tasa divide los eventos de discrepancia por los pedidos de salida; si el denominador es cero, el resultado es 0. Los campos contractuales inválidos o ausentes provocan un fallo de validación: no hay conversiones silenciosas ni IDs de cliente/pedido inferidos.

Las semanas comienzan el lunes a las 00:00 UTC y abarcan el intervalo semiabierto hasta (sin incluir) el lunes siguiente. Por defecto se procesa la semana completada más reciente. `--week-start` permite backfill y reejecución y debe indicar un lunes.

## Ejecución y frecuencia

Ejecutar desde la raíz del repositorio:

```sh
uv run --project services/api --no-sync python data/pipelines/pipeline.py
```

Backfill/reejecución de una semana:

```sh
uv run --project services/api --no-sync python data/pipelines/pipeline.py --week-start 2025-01-06
```

Se recomienda programarlo semanalmente después del cierre de la semana UTC, temprano el lunes UTC (el objetivo de diseño es 05:00 UTC y completar antes de las 08:00 UTC). El repositorio no incluye actualmente un deployment/scheduler; debe configurarse en el entorno Prefect de destino. También hay un disparador manual autenticado mediante `POST /reporting/pipeline-runs`, con `{"week_start":"YYYY-MM-DD"}` opcional. El endpoint invoca el flow canónico y no duplica transformaciones. El informe autenticado está disponible en `GET /reporting/weekly-warehouse-client-performance`; sin `week_start` devuelve la semana calculada más reciente. `GET /reporting/pipeline-runs/latest` devuelve los metadatos de la última ejecución.

## Reintentos y fallos

Prefect reintenta fallos transitorios elegibles de conexión/operación de base de datos (la tarea UPSERT permite dos reintentos; extracción permite tres). `PipelineRun.retry_count` cuenta los intentos adicionales reales según `run_count` del ciclo de vida de TaskRun de Prefect. Los errores deterministas de contrato, como datos de evento inválidos, no se reintentan. Otros errores no transitorios fallan la ejecución. Las ejecuciones fallidas conservan metadatos resumidos seguros, incluidos conteos/motivos de rechazo cuando corresponda; no se guardan payloads de eventos ni credenciales en esos metadatos.

`log_operational_summary` es opcional y no crítico: su fallo se registra, pero no cambia el estado exitoso del flow principal. Extracción, validación y carga atómica son críticas. Un error de carga revierte el lote completo.

## Configuración y ejecución local

Configuración requerida:

- `DATABASE_URL`, usando la configuración de base de datos de la aplicación. Para uso local, apuntar a SQLite; no usar la base de producción.
- `PIPELINE_TAG_PATH_WAREHOUSE` y `PIPELINE_TAG_PATH_CLIENT_ID`, rutas explícitas separadas por puntos dentro de `tags`.
- `PIPELINE_TAG_PATH_QUANTITY` para las cantidades de entrada.

Por ejemplo, los fixtures actuales usan `warehouse`, `client_id` y `quantity`; los valores de producción deben acordarse con los productores. Las ejecuciones locales/de prueba en SQLite reutilizan `get_engine()`, `get_db()` e `init_db()` de la API y crean las tablas de reporting sin un schema `reporting`. PostgreSQL conserva el schema real `reporting`. No usar una base de producción o Supabase para validación local.

## Prerrequisitos upstream conocidos (no resueltos por este pipeline)

- Los nombres de eventos de productores todavía no están alineados con los tipos exactos anteriores.
- `client_id` debe llegar desde upstream; el pipeline no lo inventa.
- Los valores canónicos de almacén deben llegar desde upstream; el pipeline no convierte alias.
- La semántica de discrepancia debe confirmarse upstream antes de interpretar `discrepancy_rate` como señal de negocio.

Consultar [PIPELINE_DESIGN.md](PIPELINE_DESIGN.md) para el diseño y contrato detallados. Estas instrucciones describen la implementación actual y no afirman que los prerrequisitos upstream estén completados.
