# Weekly warehouse/client performance pipeline

## Purpose and audience

This Prefect pipeline computes a weekly operational performance report for business operations, warehouse managers, and client-account teams. It produces one row per **warehouse + client_id + week_start** in `reporting.weekly_warehouse_client_performance`.

The source is `telemetry_events`, which is read-only for this pipeline. The reporting table is the destination and is maintained with an idempotent UPSERT keyed by warehouse, client, and week. Rerunning a week replaces its computed values rather than creating duplicate grain rows.

## Contract and measures

Only these exact event types are contractual:

- `inbound_order_created`
- `outbound_order_created`
- `stock_threshold_triggered`
- `inventory_discrepancy_detected`

Canonical warehouse values are `los_angeles` and `zaragoza`. The four KPIs are `inbound_units_count`, `outbound_orders_count`, `stockout_events_count`, and `discrepancy_rate`. The supporting field `discrepancy_events_count` is **not a fifth KPI**. The rate is discrepancy event count divided by outbound order count; a zero denominator produces 0. Invalid/missing contract fields fail validation; there are no silent mappings or inferred client/order IDs.

Weeks start Monday at 00:00 UTC and cover the half-open interval through (but not including) the next Monday. The default is the most recently completed week. An explicit `--week-start` is available for backfills and reruns and must be a Monday.

## Run and schedule

Run from the repository root:

```sh
uv run --project services/api --no-sync python data/pipelines/pipeline.py
```

Backfill/rerun a week:

```sh
uv run --project services/api --no-sync python data/pipelines/pipeline.py --week-start 2025-01-06
```

Schedule it weekly after the UTC week closes, early Monday UTC (the design target is 05:00 UTC and completion before 08:00 UTC). The pipeline currently has no in-repository scheduler deployment; configure the Prefect deployment/scheduler in the target environment. A manual authenticated trigger is also available through `POST /reporting/pipeline-runs` with optional `{"week_start":"YYYY-MM-DD"}`. The endpoint calls the canonical flow and does not duplicate transformations. The authenticated report is `GET /reporting/weekly-warehouse-client-performance`; omitting `week_start` returns the most recently computed week. `GET /reporting/pipeline-runs/latest` returns run metadata.

## Retry and failure behavior

Prefect retries eligible transient database connection/operational failures (the UPSERT task allows two retries; extraction allows three). A retry is counted from the real Prefect TaskRun lifecycle `run_count` and persisted as the number of additional attempts in `PipelineRun.retry_count`. Contract validation errors such as invalid event data are deterministic and are not retried. Other non-transient errors fail the run. Failed runs retain safe summary metadata, including rejected counts/reasons where applicable; raw event payloads and credentials are not put in run metadata.

`log_operational_summary` is optional and non-critical: its failure is logged, but does not change a successful main flow state. Extraction, validation, and atomic load are critical. A load error rolls back the full batch.

## Configuration and local execution

Required runtime configuration:

- `DATABASE_URL`, using the application database configuration. For local use, point it at SQLite; do not point local runs at production.
- `PIPELINE_TAG_PATH_WAREHOUSE` and `PIPELINE_TAG_PATH_CLIENT_ID`, explicit dot-delimited paths within event `tags`.
- `PIPELINE_TAG_PATH_QUANTITY` for inbound quantity values.

For example, the current unit-test fixture uses `warehouse`, `client_id`, and `quantity`; production values must be agreed with event producers. SQLite local/test runs reuse the API's `get_engine()`, `get_db()`, and `init_db()` infrastructure and create reporting-owned tables without a `reporting` schema. PostgreSQL preserves the real `reporting` schema. Do not use a production or Supabase database for local validation.

## Known upstream prerequisites (not solved by this pipeline)

- Producer event names have not yet been aligned with the exact event types above.
- `client_id` must be supplied upstream; this pipeline will not invent it.
- Canonical warehouse values must be supplied upstream; this pipeline does not map aliases.
- Discrepancy semantics must be confirmed upstream before interpreting `discrepancy_rate` as a business signal.

See [PIPELINE_DESIGN.md](PIPELINE_DESIGN.md) for the detailed design and contract. These operational instructions describe the current implementation; they do not claim the upstream prerequisites are complete.
