# Business Performance Pipeline Design

> **Part 1/3 — Pipeline Design Specification**
> **Branch:** `feature/business-performance-pipeline-design-v2`
> **Status:** Design only — no implementation
> **Date:** 2026-10-09

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Business Objective](#2-business-objective)
3. [Audience and Cadence](#3-audience-and-cadence)
4. [KPI Contract](#4-kpi-contract)
5. [Source Contract](#5-source-contract)
6. [Source Contract Gap / Implementation Prerequisites](#6-source-contract-gap--implementation-prerequisites)
7. [Grain and Dimensions](#7-grain-and-dimensions)
8. [Destination Schema](#8-destination-schema)
9. [Transformation Rules](#9-transformation-rules)
10. [Prefect Architecture](#10-prefect-architecture)
11. [Schedule / States / Retries / Blocks](#11-schedule--states--retries--blocks)
12. [Idempotency](#12-idempotency)
13. [Failure Handling and Recoverability](#13-failure-handling-and-recoverability)
14. [Observability](#14-observability)
15. [Pipeline Run Metadata](#15-pipeline-run-metadata)
16. [Future Reporting API](#16-future-reporting-api)
17. [Security / Privacy / Data Handling](#17-security--privacy--data-handling)
18. [Testing Strategy for Future Implementation](#18-testing-strategy-for-future-implementation)
19. [Rollout / Implementation Sequence](#19-rollout--implementation-sequence)
20. [Explicit Non-Goals](#20-explicit-non-goals)
21. [Acceptance Criteria / Definition of Done](#21-acceptance-criteria--definition-of-done)

---

## 1. Executive Summary

This document specifies the **Business Performance Pipeline** — a weekly batch ETL pipeline that produces the **Weekly Warehouse-Client Performance Report** for TrackFlow's executive and operations leadership.

The pipeline reads from the existing immutable `telemetry_events` table (read-only), aggregates four mandatory KPIs by warehouse and client for a given ISO week, and writes the result to a new reporting table `reporting.weekly_warehouse_client_performance`. It is designed for idempotent re-runs, manual backfill, and full observability.

This is **Part 1/3: Design only**. No Prefect flows, tasks, database migrations, endpoints, or service code are implemented in this milestone. The design is precise enough that a future Part 2 can implement it without reinterpreting key decisions.

---

## 2. Business Objective

Thomas (CEO) requires a **weekly report** that he can consult autonomously — without depending on Ana or Miguel to produce it manually.

The purpose of this pipeline is to exist **solely** to produce that report. Every design decision is subordinate to that single business outcome.

---

## 3. Audience and Cadence

| Attribute            | Value                                                            |
| -------------------- | ---------------------------------------------------------------- |
| **Primary audience** | Thomas (CEO), Ana Whitfield (Head of Warehouse Operations)       |
| **Frequency**        | Weekly                                                           |
| **Freshness**        | Available Monday morning (UTC)                                   |
| **Consumption**      | Reporting API (`/reporting/weekly-warehouse-client-performance`) |

The pipeline must complete and make data available **before Monday 08:00 UTC** so that the report is fresh at the start of the business week.

---

## 4. KPI Contract

The pipeline produces exactly **four business KPIs**, plus one supporting count
required to calculate KPI 4.

### 4.1 Business KPIs

| #   | KPI                  | Source Event                     | Calculation                                    | Business Meaning                                                     |
| --- | -------------------- | -------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------- |
| 1   | **Inbound Units Count** | `inbound_order_created`          | `SUM(quantity)` from `inbound_order_created` events for the week      | Units of client merchandise received by a warehouse during the week  |
| 2   | **Outbound Orders Count** | `outbound_order_created`         | `COUNT(outbound_order_created)` events for the week                   | Orders prepared and dispatched by warehouse/client during the week   |
| 3   | **Stockout Events Count** | `stock_threshold_triggered`      | `COUNT(stock_threshold_triggered)` events for the week                | Number of times a client SKU in a warehouse dropped below configured minimum |
| 4   | **Discrepancy Rate** | derived                          | `discrepancy_events_count / outbound_orders_count` (0 if denominator = 0) | Ratio of discrepancy events to outbound orders for the week          |

### 4.2 Supporting Count

| Field                    | Source Event                     | Calculation                                    |
| ------------------------ | -------------------------------- | --------------------------------------------------------------------- |
| `discrepancy_events_count` | `inventory_discrepancy_detected` | `COUNT(inventory_discrepancy_detected)` events for the week           |

`discrepancy_events_count` is a supporting count stored in the reporting row because it is required to independently recalculate `discrepancy_rate`. It is **not** a business KPI on its own.

### 4.3 Discrepancy Rate — Semantic Prerequisite

**Rule:** `discrepancy_rate = discrepancy_events_count / outbound_orders_count`. When `outbound_orders_count = 0`, the rate is defined as `0` (not null, not infinity).

**Business meaning prerequisite:** Interpreting this ratio as a *proportion of outbound orders that had a discrepancy* (bounded between 0 and 1) requires upstream-defined discrepancy-event semantics plus a guarantee or contract-defined correlation/deduplication rule establishing how events relate to outbound orders. No such guarantee or correlation contract is established in the current repository. This design names no specific key and assumes no guarantee.

Until this prerequisite is resolved upstream, the formula can only be read as discrepancy events per outbound order and may exceed 1.0; its business interpretation remains blocked. This is a source-contract prerequisite (see §6). **Part 1 does not resolve it. Part 2 must not invent a solution.**

## 5. Source Contract

### 5.1 Source Table

| Property             | Value                                                         |
| -------------------- | ------------------------------------------------------------- |
| **Table**            | `telemetry_events`                                            |
| **Access mode**      | **READ-ONLY** — never write, update, or delete                |
| **Primary key**      | `id` (UUID)                                                   |
| **Row immutability** | Events are immutable once stored                              |
| **Relevant columns** | `timestamp`, `event_type`, `tags` (JSONB)                     |
| **Tags content**     | Original envelope fields + event properties (preserved as-is) |

### 5.2 Required Event Types (v1 exactly)

The pipeline filters on exactly these four `event_type` values:

1. `inbound_order_created`
2. `outbound_order_created`
3. `stock_threshold_triggered`
4. `inventory_discrepancy_detected`

No other event types are consumed.

### 5.3 Required Properties (extracted from `tags`)

Each of the four contractual event types must provide the properties required by its event contract:

| Property     | Required for                         | Validation |
| ------------ | ------------------------------------ | ---------- |
| `warehouse`  | All four event types                 | Non-null and exactly one canonical value: `los_angeles` or `zaragoza` |
| `client_id`  | All four event types                 | Non-null, non-empty contractual client identifier |
| `quantity`   | `inbound_order_created`              | Required value must satisfy the inbound quantity contract |

**Current repository storage (verified):** `services/api/routers/telemetry.py` builds `TelemetryEventTable.tags` through `_build_tags()`. That function flattens event `properties` into top-level keys of `tags`; it does not store them under a nested `tags.properties` object. Thus, for properties that exist in current telemetry, the actual JSONB access form is `tags->>'<key>'` (for example, `tags->>'quantity'`). Envelope fields are top-level keys as well. `services/api/telemetry_models.py` defines `tags` as the JSONB storage column.

**Future source-contract prerequisite:** The four contractual event types are not currently defined. Their upstream contract must state one unambiguous location in `tags` for `warehouse`, `client_id`, and `quantity` where applicable. This document does not assume that future producers will preserve the current flattened representation; until the contract specifies it, the future extraction path is unresolved. Part 2 must not guess a path. No SQL elsewhere in this design may imply a different path.

### 5.4 UTC Time Window

The pipeline processes exactly one ISO week per run:

```
[week_start, week_start + 7 days)
```

Where `week_start` is a **Monday at 00:00:00 UTC**. The upper bound is exclusive. All `telemetry_events.timestamp` comparisons use UTC.

### 5.5 Warehouse Contract

| Canonical value | Warehouse |
| --------------- | --------- |
| `los_angeles`   | Los Angeles warehouse |
| `zaragoza`      | Zaragoza warehouse |

The four future contractual event types must emit these canonical values directly. **Normalization occurs upstream**, before the pipeline consumes the events. The pipeline accepts only `los_angeles` and `zaragoza`; it does not silently transform `LA` to `los_angeles` or `ZGZ` to `zaragoza`. Current-repository codes `LA` / `ZGZ` describe current telemetry only and are not valid future pipeline contract values. Any noncanonical or missing warehouse is a blocking contract/data violation: record the violation safely and fail the run without loading partial results (see §9 and §13).

## 6. Source Contract Gap / Implementation Prerequisites

### ⚠️ Critical Finding

The pipeline **design** uses the contractual event types and fields defined above. However, the current repository state does **not** satisfy this contract. The pipeline **must not be deployed to production** until the source contract gap is closed.

### 6.1 Confirmed Gaps

| # | Gap | Status |
| - | --- | ------ |
| 1 | The current repository does not define `inbound_order_created`, `outbound_order_created`, `stock_threshold_triggered`, or `inventory_discrepancy_detected` as contractual event types. | **BLOCKING** |
| 2 | `client_id` is not present in the current telemetry contract for these events. | **BLOCKING** |
| 3 | Current telemetry uses warehouse codes `LA` / `ZGZ`, while this design contract requires `los_angeles` / `zaragoza`. Upstream must emit canonical values; pipeline-side mapping is prohibited. | **BLOCKING** |
| 4 | No contractual equivalence is established between `inbound_registered` and `inbound_order_created`, `outbound_registered` and `outbound_order_created`, `outbound_insufficient_stock` and `stock_threshold_triggered`, or `incident_created` and `inventory_discrepancy_detected`. No mapping is safe to assume. | **BLOCKING** |
| 5 | The future `tags` JSON path for `warehouse`, `client_id`, and `quantity` (where applicable) is not defined. | **BLOCKING** |
| 6 | The discrepancy-rate semantic prerequisite is not defined: there is no current correlation key or guarantee of at most one countable discrepancy event per outbound order. Consequently the formula may yield a value greater than 1 and cannot yet be interpreted as a proportion of orders. | **BLOCKING** |

### 6.2 Explicit Disclaimers

- `inbound_registered` is **NOT** assumed equivalent to `inbound_order_created`.
- `outbound_registered` is **NOT** assumed equivalent to `outbound_order_created`.
- `outbound_insufficient_stock` is **NOT** assumed equivalent to `stock_threshold_triggered`.
- `incident_created` (with `category=inventory_discrepancy`) is **NOT** assumed equivalent to `inventory_discrepancy_detected`.

### 6.3 What Must Happen Before Implementation

1. Upstream must define and emit the four contractual event types with required `warehouse`, `client_id`, and (for inbound) `quantity` properties.
2. Upstream must emit canonical warehouse values `los_angeles` / `zaragoza`; the pipeline must not map `LA` / `ZGZ`.
3. The upstream contract must define an unambiguous `tags` JSON location for each required property. The current repository’s flattened representation is factual context, not an assumed future contract.
4. `docs/telemetry/event-schemas.json` must document those event and property contracts.
5. Upstream must define discrepancy-to-order semantics sufficient to interpret the unchanged discrepancy-rate formula as a proportion: at most one countable discrepancy event per outbound order, or a contract-defined correlation key and association rule. No such guarantee or key currently exists.
6. The contract must explicitly establish any event relationships if desired; this design does not equate current events with the future contractual types.

**All items are blocking readiness prerequisites.** Part 1 documents them without resolving telemetry. Part 2 must not start production implementation until the readiness gate is satisfied and must not invent a resolution.

### 6.4 Design Contract vs Current Repository State

| Dimension | Design Contract | Current Repository State | Required action |
| --------- | --------------- | ------------------------- | --------------- |
| Event types | Four contractual types in §5.2 | Not currently defined as contractual events | Upstream contract and emission required |
| Client identifier | Required `client_id` | Not present in current contract | Add to upstream contract and events |
| Warehouse codes | `los_angeles`, `zaragoza` | `LA`, `ZGZ` | Upstream emits canonical values; no pipeline mapping |
| Property paths | One explicit `tags` path per property | Current `_build_tags()` flattens properties to top-level `tags` keys | Future upstream contract must specify exact paths |
| Discrepancy semantics | Exact formula in §4 plus prerequisite in §4.3 | No order correlation or one-event-per-order guarantee | Upstream defines semantics; prerequisite blocks production KPI |
| Event equivalence | No implicit equivalence | No contractual mapping among similarly named current events | Do not infer mappings; upstream contract must define any intended relation |
| Event schemas | Contract documented in this design | `docs/telemetry/event-schemas.json` lacks the future contract | Update schema catalog upstream before implementation |

## 7. Grain and Dimensions

### 7.1 Grain

One row per **warehouse + client_id + week_start**.

| Dimension    | Type | Description                                                  |
| ------------ | ---- | ------------------------------------------------------------ |
| `warehouse`  | text | Warehouse identifier: `los_angeles` or `zaragoza`            |
| `client_id`  | text | Client identifier (opaque string, e.g. UUID or brand code)   |
| `week_start` | date | Monday of the ISO week (UTC). Stored as a date, no time part |

### 7.2 Warehouse Contract

- `warehouse` must be present, non-null, and exactly `los_angeles` or `zaragoza`.
- Those canonical values are emitted upstream. The pipeline does not map `LA` / `ZGZ`.
- A missing or noncanonical warehouse is a critical contract/data violation: record safe violation metadata, fail the run, do not retry automatically, and do not aggregate or load any results. No partial output is permitted.

### 7.3 Client Rule

Each row belongs to **exactly one** client. Multiple clients are never aggregated into the same row.

---

## 8. Destination Schema

### 8.1 Table

```sql
CREATE TABLE reporting.weekly_warehouse_client_performance (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  warehouse             text        NOT NULL,
  client_id             text        NOT NULL,
  week_start            date        NOT NULL,
  inbound_units_count   integer     NOT NULL DEFAULT 0,
  outbound_orders_count integer     NOT NULL DEFAULT 0,
  stockout_events_count integer     NOT NULL DEFAULT 0,
  discrepancy_events_count integer  NOT NULL DEFAULT 0,
  discrepancy_rate      numeric     NOT NULL DEFAULT 0,
  computed_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (warehouse, client_id, week_start)
);
```

### 8.2 Schema Notes

- `id` is a surrogate UUID, generated automatically. It has no business meaning.
- `discrepancy_rate` is `numeric` (arbitrary precision). The application computes it as a decimal ratio (e.g. `0.15` for 15%).
- `computed_at` is the timestamp of the last pipeline run that touched this row (updated on every upsert).
- The `UNIQUE` constraint on `(warehouse, client_id, week_start)` is the **natural business key** and the target of the UPSERT.

### 8.3 Schema (reporting schema)

The `reporting` schema must exist before the pipeline runs. It isolates reporting aggregates from the operational `public` schema (where `telemetry_events` lives). This schema must be created during database setup/migration, not by the pipeline itself.

---

## 9. Transformation Rules

### 9.1 Step-by-Step Logic

#### Step 1 — Event Filtering

Read only from `telemetry_events` for the requested UTC week:

- `timestamp >= week_start` AND `timestamp < week_start + INTERVAL '7 days'`
- `event_type IN ('inbound_order_created', 'outbound_order_created', 'stock_threshold_triggered', 'inventory_discrepancy_detected')`

Events outside this contractual event-type filter are ignored at extraction and do not count as contract violations for this run.

#### Step 2 — Strict Contract Validation

Validate every extracted contractual event before aggregation. Required fields and values are defined in §5.3 and §7.2. This includes required `warehouse`, `client_id`, inbound `quantity`, and contractual schema/event fields. Validate the entire extracted input before producing any KPI output.

**Contract/data violation policy:** Detect invalid events, increment `events_rejected` and a reason-specific counter for each violation, and record only safe violation metadata in run observability (for example, event type, reason code, and count; do not copy sensitive payloads). Then fail the run deterministically: no retry, no KPI aggregation, no reporting load, and no partial output. This applies to missing/null/invalid `warehouse`, `client_id`, required `quantity`, missing required contractual fields, and schema-contract violations. Correcting the upstream contract/data allows a safe rerun for the same `week_start`.

#### Step 3 — Aggregation

Only after the entire extracted input passes validation, group by `(warehouse, client_id)` for the selected week. The future property paths must follow the unambiguous upstream contract prerequisite in §5.3; this design does not guess a `tags` path.

| Output field | Exact calculation |
| ------------ | ----------------- |
| `inbound_units_count` | `SUM(quantity)` for `inbound_order_created` |
| `outbound_orders_count` | `COUNT(*)` for `outbound_order_created` |
| `stockout_events_count` | `COUNT(*)` for `stock_threshold_triggered` |
| `discrepancy_events_count` | `COUNT(*)` for `inventory_discrepancy_detected` |

#### Step 4 — Rate Calculation

For each group, preserve the required formula exactly:

```text
discrepancy_rate = discrepancy_events_count / outbound_orders_count
```

When `outbound_orders_count = 0`, `discrepancy_rate = 0`. The semantic prerequisite in §4.3 and §6.1 remains a production readiness blocker; do not substitute another formula or infer an order correlation.

### 9.2 Empty Week

An empty valid week is not a contract violation. If the contractual event-type filter returns zero events, the flow completes successfully with `Completed`, `events_read = 0`, zero groups, and zero reporting rows. It is not a failure, and this design does not create zero-valued rows for every possible warehouse/client combination. If any events are present but a critical contract/data violation is detected, the run fails under §9.1; it must not be treated as an empty week.

---

## 10. Prefect Architecture

### 10.1 Flow

**Flow name:** `weekly_warehouse_client_performance_flow`

This is a single Prefect flow that orchestrates the weekly aggregation end-to-end.

### 10.2 Tasks

The flow is decomposed into three strictly separated tasks:

#### Task 1 — `extract_weekly_telemetry`

Read-only extraction from `telemetry_events`, restricted to the requested UTC `[week_start, week_start + 7 days)` interval and the four contractual event types only. Events outside the filter are ignored. No reporting writes occur in this task.

#### Task 2 — `validate_and_aggregate_performance`

Perform strict source/schema validation on all extracted events. Require `client_id`, canonical `warehouse` (`los_angeles` or `zaragoza`), required inbound `quantity`, and all required contractual fields. Count violations in `events_rejected`/reason counters and record safe violation metadata. Any critical violation deterministically fails this task with **no retry**, no aggregation result, and no partial output. The flow stops; Task 3 MUST NOT RUN. For fully valid input, compute all four business KPIs and the supporting `discrepancy_events_count` using §4 and §9 formulas (including zero denominator = 0).

#### Task 3 — `upsert_weekly_performance`

Runs only after Task 2 completes successfully. Write exclusively to `reporting.weekly_warehouse_client_performance`, using the `(warehouse, client_id, week_start)` business key and one atomic transaction. Perform deterministic UPSERTs. A load error rolls back the transaction; transient infrastructure errors may retry under §11.3. A failed Task 2 can never reach this task.

| Property | Contract |
| -------- | -------- |
| Failure behavior | Contract/data violation in Task 2 → flow Failed; Task 3 is not scheduled; no partial load. Transient infrastructure failure → retry only as §11.3 allows. |
| Input | Validated aggregate result from Task 2 only |
| Output | Number of reporting rows upserted |
| Idempotency | Same `week_start` recomputes deterministically and UPSERTs on the business key |

### 10.3 Task Dependencies

```
validate_week_start (optional precondition)
    │
    ▼
health_check (optional precondition)
    │
    ▼
extract_weekly_telemetry
    │
    ▼
validate_and_aggregate_performance
    │
    ▼
upsert_weekly_performance
    │
    ▼
log_run_metadata (optional postcondition)
```

### 10.4 Inputs / Outputs / Dependencies Summary

| Element                 | Description                                                              |
| ----------------------- | ------------------------------------------------------------------------ |
| **Flow input**          | `week_start: date` — Monday of the ISO week to process                   |
| **Flow output**         | None (side-effect: reporting table is upserted; metadata is persisted)   |
| **External dependency** | Database connection to the operational PostgreSQL instance               |
| **Source**              | `telemetry_events` table (read-only)                                     |
| **Destination**         | `reporting.weekly_warehouse_client_performance` table (write via UPSERT) |
| **Secret/Block**        | Database `DATABASE_URL` connection string (see [§11.4](#114-blocks))     |

---

## 11. Schedule / States / Retries / Blocks

### 11.1 Schedule

| Property          | Value                                                              |
| ----------------- | ------------------------------------------------------------------ |
| **Cadence**       | Weekly                                                             |
| **Day**           | Monday                                                             |
| **Target window** | 05:00 – 07:00 UTC (completed by 08:00 UTC at latest)               |
| **Timezone**      | UTC for scheduling and data boundaries                             |
| **Data window**   | Previous ISO week (Monday 00:00:00 UTC → next Monday 00:00:00 UTC) |

**Why UTC for data boundaries:** All timestamps in `telemetry_events` are UTC (per the event envelope contract). Using UTC for the week boundaries eliminates DST ambiguity and ensures consistent week alignment regardless of the operator's local timezone.

**Why early Monday morning:** The report must be fresh for Thomas and Ana at the start of the business week. Running the pipeline before 08:00 UTC on Monday ensures data is ready when they arrive.

**Prefect Schedule definition (conceptual):**

```python
# Conceptual — not implemented in this milestone
Schedule(
    cron="0 5 * * 1",        # 05:00 UTC every Monday
    timezone="UTC",
)
```

### 11.2 States

| State         | Meaning                                                          |
| ------------- | ---------------------------------------------------------------- |
| **Scheduled** | The flow run has been scheduled but has not started execution    |
| **Running**   | At least one task is currently executing                         |
| **Completed** | All tasks completed successfully; data is available for querying |
| **Failed**    | A non-retriable task failed; the flow stopped without completing |

### 11.3 Retries

Retry only transient infrastructure failures that may resolve without changing source data or code. Critical source-contract/data violations are deterministic and are **never automatically retried**.

| Failure scenario | Retry? | Max retries | Result |
| ----------------- | ------ | ----------- | ------ |
| Transient DB connectivity/network error | Yes | 3 | Exponential backoff; exhausted retries → `Failed` |
| Transient DB lock/deadlock during load | Yes | 2 | Retry transaction; exhausted retries → `Failed` |
| Missing/invalid `client_id`, warehouse, quantity, required field, or schema violation | **No** | — | Count/report violation, fail; no aggregation or load |
| Empty valid week | No | — | `Completed`, zero groups and zero rows |
| Deterministic DB/schema/constraint error | No | — | `Failed`; no automatic retry |

No infinite automatic retries. Once a deterministic source-contract issue is corrected upstream, the operator may rerun the same `week_start`. Load retries rerun the atomic transaction; a later manual rerun is safe through deterministic recomputation and UPSERT.

### 11.4 Blocks

Prefect Blocks define reusable infrastructure configuration. For this pipeline, the following blocks are relevant:

| Block                          | Purpose                                                                             | Credentials in Block?                                                                 |
| ------------------------------ | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| **Database Block**             | Connection string (`DATABASE_URL`) for the operational DB                           | Reference only — actual credentials stored in Prefect Secrets / environment variables |
| **Environment Block**          | Environment label (production, staging) to select the correct DB target             | No secrets                                                                            |
| **Slack / Notification Block** | Optional alerting channel for failures (design consideration, not mandatory for v1) | Webhook URL stored as Secret                                                          |

**Security rule:** No secrets (passwords, connection strings, API tokens) are ever written into `PIPELINE_DESIGN.md` or any code. Blocks reference **Secrets** by name.

---

## 12. Idempotency

### 12.1 Natural Business Key

The natural business key of the destination table is:

```
(warehouse, client_id, week_start)
```

This triple uniquely identifies a report row. It is enforced by a `UNIQUE` constraint.

### 12.2 UPSERT Mechanism

The pipeline uses PostgreSQL `INSERT ... ON CONFLICT ... DO UPDATE` (colloquially "UPSERT"). On INSERT, omit `computed_at` from both the column list and values so its DDL `DEFAULT now()` applies; on conflict, set `computed_at = now()` as shown below.

```sql
INSERT INTO reporting.weekly_warehouse_client_performance
  (warehouse, client_id, week_start, inbound_units_count,
   outbound_orders_count, stockout_events_count,
   discrepancy_events_count, discrepancy_rate)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (warehouse, client_id, week_start)
DO UPDATE SET
  inbound_units_count       = EXCLUDED.inbound_units_count,
  outbound_orders_count     = EXCLUDED.outbound_orders_count,
  stockout_events_count     = EXCLUDED.stockout_events_count,
  discrepancy_events_count  = EXCLUDED.discrepancy_events_count,
  discrepancy_rate          = EXCLUDED.discrepancy_rate,
  computed_at               = now();
```

### 12.3 What Happens on Rerun

- **No duplicate rows** are created (the `UNIQUE` constraint prevents it).
- **Aggregates are recalculated** from the current state of `telemetry_events`.
- **The same week's row is updated** with the new deterministic result and a fresh `computed_at`.

This makes reruns safe for:

- **Manual reruns** — Thomas or Ana can trigger a fresh computation at any time.
- **Recovery** — After a failed run, the next successful run overwrites partial or missing data.
- **Backfills** — Historical weeks can be computed by running the flow with past `week_start` values. Each historical row is upserted independently.
- **Audit** — `computed_at` tracks when each row was last computed. Multiple runs for the same week produce an updated timestamp but no data loss.

### 12.4 Determinism Guarantee

The pipeline is **deterministic with respect to the source data**: given the same set of `telemetry_events` for a week, a rerun produces identical metric values. This holds because:

- Source is read-only (events are immutable).
- Aggregation logic is deterministic (SUM, COUNT).
- Rate formula is deterministic (division, with zero-guard).
- UPSERT replaces data atomically.

---

## 13. Failure Handling and Recoverability

### 13.1 Failure Scenarios

| Scenario | Detection and behavior | Retry / load outcome |
| -------- | ---------------------- | -------------------- |
| Critical source-contract/data violation (missing/null/invalid `client_id`, noncanonical warehouse, invalid/missing quantity or required field, schema violation) | Task 2 counts `events_rejected` by reason and records safe violation metadata; run fails deterministically | No retry; Task 3 does not run; no aggregation or reporting load |
| Empty valid week (zero extracted contractual events) | Task 2 completes with zero groups; observability records the empty week | `Completed`; zero reporting rows |
| Transient DB/network failure during extraction or load | Task fails with transient infrastructure error | Retry according to §11.3; exhaustion → `Failed` |
| Load failure after write begins | Atomic transaction rolls back all writes | Retry only if transient; no partial committed load |
| Deterministic database/schema/constraint failure | Fail immediately and record safe error summary | No retry |

A corrected upstream contract/data violation may be rerun for the same `week_start`; deterministic recomputation and the business-key UPSERT make that rerun safe.

### 13.2 Recoverability Design

| Failure/state | Recovery contract |
| ------------- | ----------------- |
| Transient infrastructure failure | Retry under §11.3; if exhausted, run is `Failed` |
| Critical source-contract/data violation | No retry; `Failed`; no aggregation and no reporting load. Correct upstream, then manually rerun the same `week_start` |
| Empty valid week | `Completed`; zero groups and zero rows |
| Load failure | Roll back the single transaction; retry only if transient; deterministic recomputation plus UPSERT makes rerun safe |
| Manual rerun/backfill | Supported by specifying `week_start`; recompute and UPSERT that week |

| Guarantee | Description |
| --------- | ----------- |
| **No silent continuation after critical violation** | A critical source-contract/data violation fails the flow; it is never skipped to produce partial KPIs. |
| **Atomicity of load** | All upserts are one database transaction; any load failure rolls back all writes. |
| **Safe rerun** | Fix source issue, then rerun the same `week_start`; deterministic recomputation and the business-key UPSERT are safe. |
| **Empty-week distinction** | Zero events is valid and completes with no rows; invalid events are not an empty week. |

### 13.3 Retry vs Fail Decision Tree

```text
Did extraction find zero contractual events for this week?
  YES → valid empty week → Completed; zero groups and zero rows
  NO  → Did any event violate the required source/schema contract?
          YES → record safe violation metadata and rejection counters
                → Failed immediately; no retry, no aggregation, no load
          NO  → Did a transient infrastructure failure occur?
                  YES → retry under §11.3; exhausted → Failed
                  NO  → deterministic/unexpected failure → Failed; no retry
```

Task 3 is unreachable unless Task 2 completes successfully.

## 14. Observability

### 14.1 Per-Run Metadata Logging

| Field | Description |
| ----- | ----------- |
| `events_read` | Number of events returned by the contractual extraction filter |
| `events_rejected` | Count of extracted events with critical contract/data violations; the run still fails and no valid subset is aggregated |
| `events_rejected_reasons` | Safe reason-code/count breakdown (for example, `missing_client_id`, `unknown_warehouse`, `invalid_quantity`); do not store sensitive event payloads |
| `groups_aggregated` | Number of groups, zero for an empty week or failed validation |
| `rows_upserted` | Number of rows committed; zero for failed validation or rolled-back transaction |
| `retry_count` | Transient infrastructure retries only; deterministic contract/data violations have zero retries |
| `pipeline_status` | `Completed` for successful valid weeks including empty weeks; `Failed` for violations or exhausted failures |
| `failure_reason` | Safe summary/reason code for failed runs; never the full sensitive payload |

### 14.2 Observability Principle

**Business metrics ≠ operational metrics.** The KPIs (`inbound_units_count`, `outbound_orders_count`, etc.) are business data that flows into the report. The observability fields (`events_read`, `events_rejected`, `retry_count`, etc.) are operational metadata about the pipeline itself. They must be logged to a separate metadata store (see [§15](#15-pipeline-run-metadata)), not mixed into the reporting table.

---

## 15. Pipeline Run Metadata

### 15.1 Conceptual Table Design

To support `GET /reporting/pipeline-runs/latest` and enable operational visibility, a metadata table for pipeline runs should be designed as part of the `reporting` schema. This table is **not implemented in this milestone** but its design is specified here.

```sql
CREATE TABLE reporting.pipeline_runs (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_name     text        NOT NULL,
  week_start        date        NOT NULL,
  state             text        NOT NULL,     -- 'scheduled', 'running', 'completed', 'failed'
  started_at        timestamptz NOT NULL,
  completed_at      timestamptz,
  events_read       integer     NOT NULL DEFAULT 0,
  events_rejected   integer     NOT NULL DEFAULT 0,
  events_rejected_reasons jsonb   DEFAULT '{}',
  groups_aggregated integer     NOT NULL DEFAULT 0,
  rows_upserted     integer     NOT NULL DEFAULT 0,
  error_summary     text,
  retry_count       integer     NOT NULL DEFAULT 0,
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- Index for efficient "latest run" query
CREATE INDEX idx_pipeline_runs_pipeline_week
  ON reporting.pipeline_runs (pipeline_name, week_start DESC);
```

**Design notes:**

- `pipeline_name` allows future pipelines to share the same metadata table.
- `week_start` identifies which week the run processed.
- `state` uses plain text (not an enum) to allow future states without migration.
- `events_rejected_reasons` is a JSONB breakdown for structured rejection logging.
- The index on `(pipeline_name, week_start DESC)` supports "get latest run" queries efficiently.

### 15.2 Write Timing

| Timing Point | Action                                                           |
| ------------ | ---------------------------------------------------------------- |
| Before flow  | Insert row with `state = 'running'`, `started_at = now()`        |
| After flow   | Update row with `state`, `completed_at`, counters, error summary |

This two-phase write ensures that even a failed run leaves a trace.

---

## 16. Future Reporting API

### 16.1 New Module

A new FastAPI module should be created:

```
services/reporting/
├── __init__.py
├── routers/
│   ├── __init__.py
│   ├── weekly_performance.py   # GET /reporting/weekly-warehouse-client-performance
│   └── pipeline_runs.py        # GET /reporting/pipeline-runs/latest, POST /reporting/pipeline-runs
├── models.py                   # Pydantic models for request/response
└── dependencies.py             # Shared dependencies (DB session, etc.)
```

This module is **not implemented in this milestone**.

### 16.2 Endpoint: `GET /reporting/weekly-warehouse-client-performance`

| Property            | Value                                                                            |
| ------------------- | -------------------------------------------------------------------------------- |
| **Path**            | `GET /reporting/weekly-warehouse-client-performance`                             |
| **Query params**    | `week_start: date` (optional — defaults to the most recent computed week)        |
| **Response**        | Array of rows from `reporting.weekly_warehouse_client_performance` for that week |
| **Default**         | If `week_start` omitted, return the most recent week available in the table      |
| **Scope**           | Returns **all** `(warehouse, client)` combinations for that week                 |
| **No modification** | Does **not** replace or modify `GET /telemetry/report`                           |

### 16.3 Endpoint: `GET /reporting/pipeline-runs/latest`

| Property     | Value                                                                                                                                                                        |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Path**     | `GET /reporting/pipeline-runs/latest`                                                                                                                                        |
| **Response** | Latest run from `reporting.pipeline_runs` ordered by `started_at DESC`                                                                                                       |
| **Fields**   | `pipeline_name`, `week_start`, `state`, `started_at`, `completed_at`, `events_read`, `events_rejected`, `groups_aggregated`, `rows_upserted`, `error_summary`, `retry_count` |

### 16.4 Endpoint: `POST /reporting/pipeline-runs`

| Property         | Value                                                                      |
| ---------------- | -------------------------------------------------------------------------- |
| **Path**         | `POST /reporting/pipeline-runs`                                            |
| **Request body** | `{"week_start": "2026-10-05"}` (optional — defaults to previous ISO week)  |
| **Response**     | `{"run_id": "...", "state": "running", "started_at": "..."}`               |
| **Behavior**     | Triggers the Prefect flow for the specified `week_start`                   |
| **Note**         | Implementation depends on Prefect deployment model (REST API, CLI, or SDK) |

### 16.5 Non-Interference Declaration

These endpoints:

- **Do NOT** replace or modify `GET /telemetry/report`.
- **Do NOT** modify `services/telemetry/analysis.py`.
- **Do NOT** modify existing telemetry ingestion or storage.

---

## 17. Security / Privacy / Data Handling

### 17.1 Principles

| Principle                           | Application                                                                                                                              |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **No secrets in design**            | This document contains no passwords, API keys, or tokens                                                                                 |
| **Read-only source**                | The pipeline only reads `telemetry_events`. No writes ever                                                                               |
| **Minimal PII exposure**            | `client_id` is an opaque identifier (UUID or brand code). It is not a person's name, email, or address                                   |
| **Tags used minimally**             | Only `warehouse`, `client_id`, and `quantity` are extracted from `tags`. No raw free-text fields are accessed or stored                  |
| **No raw event storage**            | The reporting table stores only aggregated metrics, not raw events                                                                       |
| **Auditability**                    | All pipeline runs are logged with metadata. Any manual rerun is traceable                                                                |
| **No unprotected warehouse values** | Only the contractual warehouses `los_angeles` and `zaragoza` are accepted. Unknown warehouse values are rejected, not silently processed |

### 17.2 Data Flow

```
telemetry_events (READ-ONLY)
        │
        │  (read by pipeline, filtered by event_type + time window)
        ▼
    [in-memory validation + aggregation]
        │
        │  (only validated, aggregated metrics written)
        ▼
reporting.weekly_warehouse_client_performance (UPSERT)
```

### 17.3 What is NOT Stored in the Reporting Table

- Raw event payloads
- `eventId`, `timestamp`, `userId`, `sessionId` from source events
- Free-text fields (`message`, incident descriptions, etc.)
- Any PII

---

## 18. Testing Strategy for Future Implementation

The future implementation must cover the following design-contract categories. This section specifies expected tests; it does not claim that implementation or tests exist today.

1. **Valid aggregation:** one fixture per contractual event type; verify the four business KPI values and supporting `discrepancy_events_count` independently.
2. **UTC week boundary:** include timestamps at `week_start` and immediately before the exclusive end; exclude the end and events outside the selected week.
3. **Strict validation / no partial output:** for each critical violation (missing/null/invalid `client_id`, missing/null/invalid/noncanonical warehouse, missing/invalid required quantity, required field/schema violation), assert safe rejection counters and metadata, deterministic `Failed`, zero automatic retries, zero KPI aggregation, zero Task 3 calls, and zero reporting writes—even when otherwise-valid events are present.
4. **Valid empty week:** assert `Completed`, `events_read = 0`, zero groups, and zero reporting rows; distinguish this from any week containing an invalid contractual event.
5. **Discrepancy semantics:** verify the exact formula and zero-denominator behavior; test unique-per-transaction event semantics only once the upstream contract defines the required correlation/deduplication behavior. Until then, production readiness remains blocked; do not fabricate a key.
6. **Atomic load failure:** force failure within the transaction and assert full rollback, no partial committed rows, transient retry only when the failure is retryable.
7. **UPSERT idempotency:** repeat the same valid `week_start` and assert deterministic business-key results and refreshed `computed_at`.
8. **Retry classification:** transient infrastructure failures retry within configured limits; deterministic source/schema violations and deterministic database errors do not retry.
9. **Backfill/manual rerun:** rerun a corrected week by `week_start` and verify safe deterministic replacement.
10. **Warehouse contract:** accept only `los_angeles` and `zaragoza`; assert that `LA` and `ZGZ` are rejected, never mapped.
11. **Source JSON contract readiness:** validate against the eventual upstream-defined property paths and required event shapes; do not assert guessed JSON paths before that contract exists.

## 19. Rollout / Implementation Sequence

### 19.1 Prerequisite (Must Complete Before Part 2)

Deployment is blocked until each upstream source-contract prerequisite is verified and documented:

- [ ] All four contractual event types exist with versioned schemas and required fields.
- [ ] Upstream emits canonical `warehouse` values `los_angeles` / `zaragoza`; no pipeline-side mapping from `LA` / `ZGZ` is permitted.
- [ ] `client_id`, inbound `quantity`, and all required fields have documented types, nullability, and validation rules.
- [ ] Exact JSON storage/property paths for every required field are explicitly defined for this source representation and verified against emitted events; no path is inferred by this design.
- [ ] `inventory_discrepancy_detected` has upstream-defined semantics and a documented guarantee or contract-defined correlation/deduplication rule sufficient to interpret discrepancy events against outbound orders. No key or guarantee is assumed here.
- [ ] Invalid contract/data behavior is implemented as deterministic fail/no retry/no aggregation/no load; valid empty weeks complete with zero rows.
- [ ] Reporting schema/table migration, transactional UPSERT, rollback, and backfill behavior are ready for implementation and validation.

The first five checkboxes are **blocking upstream contract prerequisites**. An incomplete checkbox means the pipeline must not be enabled for production scheduling.

### 19.2 Implementation Sequence (Part 2)

| Step | Task                                                                      | Dependencies |
| ---- | ------------------------------------------------------------------------- | ------------ |
| 1    | Create `reporting` schema in database migration                           | None         |
| 2    | Create `reporting.weekly_warehouse_client_performance` table              | Step 1       |
| 3    | Implement `extract_weekly_telemetry` task                                 | Step 1, 2    |
| 4    | Implement `validate_and_aggregate_performance` task                       | None         |
| 5    | Implement `upsert_weekly_performance` task                                | Step 1, 2    |
| 6    | Implement `weekly_warehouse_client_performance_flow` flow (orchestration) | Steps 3–5    |
| 7    | Implement `reporting.pipeline_runs` metadata table                        | None         |
| 8    | Implement run metadata logging in the flow                                | Step 7       |
| 9    | Create `services/reporting/` module                                       | None         |
| 10   | Implement `GET /reporting/weekly-warehouse-client-performance`            | Step 2       |
| 11   | Implement `GET /reporting/pipeline-runs/latest`                           | Step 7       |
| 12   | Implement `POST /reporting/pipeline-runs`                                 | Step 6, 7    |
| 13   | Write tests (see [§18](#18-testing-strategy-for-future-implementation))   | Steps 3–12   |
| 14   | Configure Prefect schedule (cron for Monday 05:00 UTC)                    | Step 6       |

### 19.3 Rollout Order

1. **Source contract gap resolved** (upstream telemetry changes) — **BLOCKING**.
2. Database migration (schemas + tables).
3. Pipeline tasks + flow (internal — no user-facing change).
4. Reporting API endpoints.
5. Tests.
6. Prefect schedule activation.
7. Monitoring + alerting setup.

---

## 20. Explicit Non-Goals

The following are explicitly **out of scope** for this pipeline design:

| #   | Non-Goal                                                | Rationale                                                                                                  |
| --- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| 1   | **No modification of telemetry ingestion**              | The `telemetry_events` ingestion layer is already implemented and is not part of this milestone            |
| 2   | **No modification of `services/telemetry/analysis.py`** | Existing analysis pipeline is independent and must not be touched                                          |
| 3   | **No modification of `GET /telemetry/report`**          | Existing report endpoint remains unchanged                                                                 |
| 4   | **No dashboards**                                       | This milestone produces only the pipeline design and data. Visualization is a future concern               |
| 5   | **No new KPIs**                                         | Exactly four business KPIs in v1; `discrepancy_events_count` is a supporting count, not a fifth KPI                                                                      |
| 6   | **No currency dimension**                               | Monetary values are not included in this pipeline                                                          |
| 7   | **No multi-client aggregation**                         | Each row belongs to exactly one client. No cross-client aggregation                                        |
| 8   | **No Prefect deployment**                               | Prefect infrastructure (workers, storage, deployment) is not part of this design milestone                 |
| 9   | **No real-time or streaming**                           | The pipeline is batch-only, weekly cadence. No streaming or real-time processing                           |
| 10  | **No alerting rules**                                   | The pipeline logs failures; it does not define business alerting thresholds                                |
| 11  | **No data retention/deletion policy**                   | The reporting table stores aggregated weekly data indefinitely in v1. Retention policy is a future concern |

---

## 21. Acceptance Criteria / Definition of Done

### 21.1 Design Milestone (This Milestone)

| # | Criterion | Status |
| - | --------- | ------ |
| 1 | `data/pipelines/PIPELINE_DESIGN.md` exists and remains design-only | Done |
| 2 | Document contains all 21 design sections | Done |
| 3 | `telemetry_events` is the read-only source and current storage facts are separated from future source-contract assumptions | Done |
| 4 | All four event types and all blocking upstream contract gaps are explicit | Done |
| 5 | Destination is `reporting.weekly_warehouse_client_performance` with grain `(warehouse, client_id, week_start)` | Done |
| 6 | Exactly four business KPIs are defined; `discrepancy_events_count` is identified only as supporting; formula/zero-denominator behavior are exact | Done |
| 7 | Contract violation fails deterministically without retry, aggregation, partial output, or load; Task 3 is gated on Task 2 success | Done |
| 8 | Valid empty week completes with zero groups/rows; it is not conflated with invalid input | Done |
| 9 | Transient-only retry, transaction rollback, deterministic UPSERT, and manual backfill by `week_start` are specified | Done |
| 10 | UPSERT omits `computed_at` from INSERT columns/values and relies on its DDL default; conflict UPDATE refreshes it | Done |
| 11 | Deployment readiness explicitly blocks on all upstream event/schema/field/path/warehouse/discrepancy prerequisites | Done |
| 12 | No implementation files, tests, services, migrations, endpoints, telemetry, or reporting systems are changed | Verify |
| 13 | No git add/commit/push/PR or other git mutation is performed | Verify |
| 14 | Only `data/pipelines/PIPELINE_DESIGN.md` is edited by this task | Verify |

### 21.2 Implementation Milestone (Future — Part 2)

The following are future implementation acceptance criteria, not claims of existing implementation:

1. Implement the reporting schema/table and transactional UPSERT only after upstream readiness prerequisites are closed.
2. Implement the Prefect flow with extraction, strict validation/aggregation, and success-gated load tasks.
3. Verify all test categories in §18, including no retry/no partial output for contract violations, valid empty week, atomic rollback, idempotency, and zero-denominator behavior.
4. Implement reporting endpoints only after the source contract and data semantics are approved.
5. Configure the schedule only after all blocking source-contract prerequisites and deployment checks pass.
6. Preserve `services/telemetry/analysis.py` and `GET /telemetry/report` unchanged.

---

_End of Pipeline Design Document — Part 1/3_

_End of Pipeline Design Document — Part 1/3_
