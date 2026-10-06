# TrackFlow Telemetry Design Plan — Event Catalog

> **Phase 2** — Event Catalog Design
> **Project:** Plan de Telemetría — 4Geeks Academy
> **Company:** TrackFlow (warehouse & last-mile delivery — Los Ángeles + Zaragoza)
> **Branch:** `feature/telemetry-design-plan`
> **Status:** Design specification only — no implementation

---

## Terminology Note

The source document `CONTEXT-trackflow.es.md` does **not** literally define a "telemetry specification" or use the word "telemetry." The five mandatory requirements below are **Context-Derived Mandatory Requirements** — explicit stakeholder operational visibility needs extracted from the company briefing. They are the telemetry drivers, not pre-defined metrics.

This catalog translates those needs into **5 context-derived mandatory business requirements**, covered by **2 selected mandatory event types** + downstream derivation. The rubric requires that _all context-derived mandatory business needs are covered_; it does not mandate a specific raw count of mandatory event types.

This catalog translates those needs into actionable event types that a future telemetry pipeline can capture.

---

## Table of Contents

1. [Shared Event Envelope](#1-shared-event-envelope)
2. [PII / Sensitive Data Policy](#2-pii--sensitive-data-policy)
3. [Event Definitions](#3-event-definitions)
   - 3.1 [Incident Events](#31-incident-events)
   - 3.2 [Inventory / Operations Events](#32-inventory--operations-events)
   - 3.3 [Authentication / Session Events](#33-authentication--session-events)
   - 3.4 [Supplier Events](#34-supplier-events)
   - 3.5 [Error / Validation Events](#35-error--validation-events)
   - 3.6 [Performance Events](#36-performance-events)
4. [Incident >24h Strategy](#4-incident-24h-strategy)
5. [Direct Stock Modification Design Note](#5-direct-stock-modification-design-note)
6. [Stream vs Batch Summary](#6-stream-vs-batch-summary)
7. [Event Catalog Summary](#7-event-catalog-summary)
8. [Rejected or Not Applicable Candidates](#8-rejected-or-not-applicable-candidates)
9. [Out of Scope for This Design Exercise](#9-out-of-scope-for-this-design-exercise)
10. [Telemetry Risks and Failure Modes](#10-telemetry-risks-and-failure-modes)
11. [Cost / Volume / Retention by Category](#11-cost--volume--retention-by-category)

---

## 1. Shared Event Envelope

Every telemetry event **must** conform to this envelope. No additional top-level fields are permitted beyond `properties`.

| Field           | Type                     | Required     | Purpose                                               | Generation Source                                 | Privacy Treatment                                                 |
| --------------- | ------------------------ | ------------ | ----------------------------------------------------- | ------------------------------------------------- | ----------------------------------------------------------------- |
| `eventId`       | string (UUID v4)         | **required** | Unique event identifier for deduplication             | Generated at emission point                       | None (random)                                                     |
| `timestamp`     | string (ISO 8601 UTC)    | **required** | When the event occurred                               | Wall clock at emission                            | Acceptable; timezone must be UTC                                  |
| `sessionId`     | string (UUID v4) or null | **optional** | Browser/device session grouping                       | Frontend on login (localStorage)                  | **Pseudonymous** — hash with HMAC-SHA256 for retention >30 days   |
| `userId`        | string or null           | **optional** | Actor user UUID (not email, not doc_id)               | Resolved from JWT `sub` → user.uuid               | **Pseudonymous** — use `user.uuid`; hash for long-term aggregates |
| `event_type`    | string                   | **required** | Event classification key (`entity_action` snake_case) | Defined in this catalog                           | None                                                              |
| `schemaVersion` | string                   | **required** | Envelope + properties schema version                  | Fixed per catalog edition (e.g. `"1.0"`)          | None                                                              |
| `requestId`     | string (UUID v4) or null | **optional** | API request correlation ID                            | Backend middleware; null for frontend-only events | None (correlation only)                                           |
| `properties`    | object                   | **required** | Event-specific payload — see allowlists below         | Per event type                                    | Must comply with each event's allowlist; no extra properties      |

### Envelope Rules

- `eventId` **must** be unique. Duplicate `eventId`s must be discarded downstream.
- `timestamp` **must** be UTC with no offset component (e.g. `"2026-10-05T14:30:00.000Z"`).
- `userId` **must** use the user's `uuid` (stable, non-enumerable TinyDB field). Never use `email`, `doc_id`, or `hashed_password`.
- `sessionId` is `null` for backend-only events (e.g. performance monitoring, server errors).
- `requestId` is `null` for frontend-only events (e.g. page navigation).
- `properties` **must not** exceed 64 KB serialized.

---

## 2. PII / Sensitive Data Policy

### Classification Definitions

| Classification   | Meaning                                                           | Examples                                                                                                                                                       | Retention Rule                                                             |
| ---------------- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| **SAFE**         | No privacy or security implications                               | Branch enum, category enum, status, SKU code, warehouse                                                                                                        | Retain indefinitely                                                        |
| **PSEUDONYMOUS** | Identifies an entity but does not directly name a person          | User UUID, session ID (HMAC-hashed), hashed email correlation key                                                                                              | Retain with 90-day rolling window; archive after 90 days                   |
| **PII**          | Directly identifies a natural person                              | Email, name, phone, address                                                                                                                                    | **NEVER capture** in telemetry events                                      |
| **SENSITIVE**    | Operational data that could cause harm if exposed                 | Tracking number, incident description snippet, supplier notes                                                                                                  | **DO NOT CAPTURE** raw; capture derived booleans or aggregated counts only |
| **FORBIDDEN**    | Must never appear in any telemetry payload under any circumstance | Passwords, password hashes, JWT/access tokens, Authorization headers, reset tokens, stack traces, filesystem paths, raw request bodies, raw exception messages | **ABSOLUTELY FORBIDDEN**                                                   |

### Data Capture Rules

1. **Never** include free-text fields (`description`, `notes`, `title`) in telemetry properties.
2. **Never** include authentication secrets of any kind.
3. **Never** include raw IP addresses in event payloads. If rate-limiting needs an IP-derived key, use an ephemeral HMAC-based identifier discarded after rate-limit window expiry.
4. **Never** include raw exception text or stack traces. Use normalized error codes.
5. User identity correlation **must** use `user.uuid` (a stable, non-enumerable UUID). For long-term pseudonymization, apply HMAC-SHA256 (with a collector-held secret) to `user.uuid`.
6. `sessionId` should be hashed with HMAC-SHA256 for retention beyond 30 days.
7. Do NOT recommend plain SHA-256 of email for identity correlation — it enables rainbow-table attacks. Instead, use the collector-managed UUID system.

---

## 3. Event Definitions

---

### 3.1 Incident Events

These two event types collectively satisfy all five Context-Derived Mandatory Requirements:

| Requirement                                        | Covered By                                                            |
| -------------------------------------------------- | --------------------------------------------------------------------- |
| R1 — Critical incidents by branch (LA vs Zaragoza) | `incident_created` + `incident_status_transition`                     |
| R2 — Incidents open >24h                           | Derived downstream from `incident_created.timestamp` + current status |
| R3 — Operational failure visibility                | `incident_created` (all categories, origins, branches)                |
| R4 — Lifecycle traceability                        | `incident_status_transition` (valid transitions only)                 |
| R5 — SLA-impact category visibility                | `incident_created` properties (`category`, `branch`)                  |

---

#### `incident_created`

| Field                 | Value                                                                                                                                              |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Classification**    | Context-Derived Mandatory                                                                                                                          |
| **Category**          | Incidents                                                                                                                                          |
| **Business question** | What operational failures are occurring, where, and how severe? Are SLA-impact categories (lost_parcel, carrier_issue) concentrated in one market? |
| **Decision enabled**  | Staff allocation by branch; SLA risk monitoring; client reporting; trend analysis for training investment                                          |
| **Trigger**           | POST `/api/incidents` — success (HTTP 201)                                                                                                         |
| **Producer**          | backend                                                                                                                                            |
| **Entity**            | Incident                                                                                                                                           |

**Properties allowlist:**

| Property       | Type    | Req/Opt  | Example          | Privacy                                   |
| -------------- | ------- | -------- | ---------------- | ----------------------------------------- |
| `incident_id`  | integer | required | `42`             | SAFE (TinyDB doc_id)                      |
| `category`     | string  | required | `"lost_parcel"`  | SAFE (enum)                               |
| `origin`       | string  | required | `"branch"`       | SAFE (enum)                               |
| `branch`       | string  | required | `"la_warehouse"` | SAFE (enum)                               |
| `status`       | string  | required | `"open"`         | SAFE (enum)                               |
| `title_length` | integer | optional | `87`             | SAFE (derived — length only, not content) |

**Explicitly forbidden properties:** `title` (raw text), `description` (raw text), free-text fields of any kind.

| Field              | Value                                                                                                                                                                                        |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Delivery**       | STREAM                                                                                                                                                                                       |
| **Rationale**      | Thomas Harry needs real-time critical-incident visibility; Andrés Kim needs operational failure awareness without waiting for WhatsApp. Stream enables near-real-time dashboards and alerts. |
| **Volume**         | MEDIUM (daily ops incidents)                                                                                                                                                                 |
| **Sampling**       | NONE (capture all)                                                                                                                                                                           |
| **Throttle**       | NONE                                                                                                                                                                                         |
| **Deduplication**  | `eventId` — discard duplicates downstream                                                                                                                                                    |
| **Schema version** | 1.0                                                                                                                                                                                          |

---

#### `incident_status_transition`

| Field                 | Value                                                                                                                                                                   |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Classification**    | Context-Derived Mandatory                                                                                                                                               |
| **Category**          | Incidents                                                                                                                                                               |
| **Business question** | How are incidents progressing through their lifecycle? Which transitions fail validation? How long do incidents stay in each state?                                     |
| **Decision enabled**  | Process compliance monitoring; bottleneck detection (e.g. incidents stuck `in_progress`); SLA enforcement; training needs for operators who attempt invalid transitions |
| **Trigger**           | PATCH `/api/incidents/{id}/status` — success (HTTP 200)                                                                                                                 |
| **Producer**          | backend                                                                                                                                                                 |
| **Entity**            | Incident                                                                                                                                                                |

**Properties allowlist:**

| Property          | Type    | Req/Opt  | Example          | Privacy     |
| ----------------- | ------- | -------- | ---------------- | ----------- |
| `incident_id`     | integer | required | `42`             | SAFE        |
| `previous_status` | string  | required | `"open"`         | SAFE (enum) |
| `new_status`      | string  | required | `"in_progress"`  | SAFE (enum) |
| `category`        | string  | required | `"lost_parcel"`  | SAFE (enum) |
| `branch`          | string  | required | `"la_warehouse"` | SAFE (enum) |

**Explicitly forbidden properties:** incident description, title, any free text.

| Field              | Value                                                                                                                                                |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Delivery**       | STREAM                                                                                                                                               |
| **Rationale**      | SLA monitoring requires near-real-time status changes (a resolved incident ≠ a stale one). Stream enables >24h breach detection and live dashboards. |
| **Volume**         | LOW (status changes are less frequent than creation)                                                                                                 |
| **Sampling**       | NONE (capture all)                                                                                                                                   |
| **Throttle**       | NONE — debouncing legitimate state transitions could lose valid data. Deduplicate by `eventId` + `requestId`.                                        |
| **Deduplication**  | `eventId` primary; `requestId` secondary for retry correlation                                                                                       |
| **Schema version** | 1.0                                                                                                                                                  |

---

### 3.2 Inventory / Operations Events

---

#### `sku_created`

| Field                 | Value                                                                                   |
| --------------------- | --------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                             |
| **Category**          | Inventory / Operations                                                                  |
| **Business question** | How fast is the product catalog growing? Which categories and warehouses are expanding? |
| **Decision enabled**  | Warehouse space allocation; procurement planning; category expansion investment         |
| **Trigger**           | POST `/inventory/products` — success (HTTP 201)                                         |
| **Producer**          | backend                                                                                 |
| **Entity**            | SKU                                                                                     |

**Properties allowlist:**

| Property      | Type    | Req/Opt  | Example               | Privacy                             |
| ------------- | ------- | -------- | --------------------- | ----------------------------------- |
| `sku_id`      | integer | required | `7`                   | SAFE                                |
| `sku_code`    | string  | required | `"CLT-SNK-W-42"`      | SAFE (product identifier)           |
| `category`    | string  | required | `"fashion"`           | SAFE (enum)                         |
| `warehouse`   | string  | required | `"LA"`                | SAFE (enum)                         |
| `client_name` | string  | required | `"PureStep Footwear"` | SAFE (client brand, not individual) |

**Forbidden:** None beyond general policy.

| Field              | Value                                                                                          |
| ------------------ | ---------------------------------------------------------------------------------------------- |
| **Delivery**       | BATCH                                                                                          |
| **Rationale**      | Catalog growth is a cumulative metric; daily aggregation is sufficient for planning decisions. |
| **Volume**         | VERY LOW (occasional SKU creation)                                                             |
| **Sampling**       | NONE (capture all)                                                                             |
| **Throttle**       | NONE                                                                                           |
| **Deduplication**  | `eventId`                                                                                      |
| **Schema version** | 1.0                                                                                            |

---

#### `inbound_registered`

| Field                 | Value                                                                                           |
| --------------------- | ----------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                     |
| **Category**          | Inventory / Operations                                                                          |
| **Business question** | How much inventory is arriving per warehouse per SKU category? Are there inbound volume spikes? |
| **Decision enabled**  | Receiving dock staffing; warehouse scheduling; supplier receipt verification                    |
| **Trigger**           | POST `/inventory/orders/inbound` — success (HTTP 201)                                           |
| **Producer**          | backend                                                                                         |
| **Entity**            | StockEntry                                                                                      |

**Properties allowlist:**

| Property    | Type    | Req/Opt  | Example          | Privacy     |
| ----------- | ------- | -------- | ---------------- | ----------- |
| `entry_id`  | integer | required | `12`             | SAFE        |
| `sku_id`    | integer | required | `1`              | SAFE        |
| `sku_code`  | string  | required | `"CLT-SNK-W-42"` | SAFE        |
| `quantity`  | integer | required | `500`            | SAFE        |
| `warehouse` | string  | required | `"LA"`           | SAFE (enum) |
| `category`  | string  | required | `"fashion"`      | SAFE (enum) |

**Forbidden:** Reference strings (may contain PO numbers that are sensitive); `user_uuid` (pseudonymous but not needed for volume metrics).

| Field              | Value                                                                                              |
| ------------------ | -------------------------------------------------------------------------------------------------- |
| **Delivery**       | BATCH                                                                                              |
| **Rationale**      | Inbound volume is a shift-level metric; daily aggregation is sufficient for staffing and planning. |
| **Volume**         | LOW (per receipt event)                                                                            |
| **Sampling**       | NONE (capture all)                                                                                 |
| **Throttle**       | NONE                                                                                               |
| **Deduplication**  | `eventId`                                                                                          |
| **Schema version** | 1.0                                                                                                |

---

#### `outbound_registered`

| Field                 | Value                                                                                        |
| --------------------- | -------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                  |
| **Category**          | Inventory / Operations                                                                       |
| **Business question** | What is the dispatch vs loss ratio per warehouse? Is loss increasing over time?              |
| **Decision enabled**  | Loss-prevention investment; operational audit scheduling; warehouse performance benchmarking |
| **Trigger**           | POST `/inventory/orders/outbound` — success (HTTP 201)                                       |
| **Producer**          | backend                                                                                      |
| **Entity**            | StockExit                                                                                    |

**Properties allowlist:**

| Property       | Type    | Req/Opt  | Example          | Privacy                                                          |
| -------------- | ------- | -------- | ---------------- | ---------------------------------------------------------------- |
| `exit_id`      | integer | required | `5`              | SAFE                                                             |
| `sku_id`       | integer | required | `1`              | SAFE                                                             |
| `sku_code`     | string  | required | `"CLT-SNK-W-42"` | SAFE                                                             |
| `quantity`     | integer | required | `45`             | SAFE                                                             |
| `exit_type`    | string  | required | `"dispatch"`     | SAFE (enum: dispatch/loss)                                       |
| `warehouse`    | string  | required | `"LA"`           | SAFE (enum)                                                      |
| `category`     | string  | required | `"fashion"`      | SAFE (enum)                                                      |
| `has_tracking` | boolean | required | `true`           | **SENSITIVE-derived** (boolean only — never raw tracking number) |

**Forbidden:** Raw `tracking_number`, `user_uuid`.

| Field              | Value                                                                                |
| ------------------ | ------------------------------------------------------------------------------------ |
| **Delivery**       | BATCH                                                                                |
| **Rationale**      | Dispatch/loss ratio is a periodic metric; daily or weekly aggregation is sufficient. |
| **Volume**         | LOW (per dispatch/loss event)                                                        |
| **Sampling**       | NONE (capture all)                                                                   |
| **Throttle**       | NONE                                                                                 |
| **Deduplication**  | `eventId`                                                                            |
| **Schema version** | 1.0                                                                                  |

---

#### `outbound_insufficient_stock`

| Field                 | Value                                                                                                                            |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                                                      |
| **Category**          | Inventory / Operations                                                                                                           |
| **Business question** | Which SKUs run out of stock most frequently? Which warehouse experiences more shortages? How large are the shortfalls?           |
| **Decision enabled**  | Reorder point adjustment; client restock notification; safety stock policy change; supplier negotiation for faster replenishment |
| **Trigger**           | POST `/inventory/orders/outbound` — HTTP 400 with `detail` matching `"Insufficient stock for SKU..."`                            |
| **Producer**          | backend                                                                                                                          |
| **Entity**            | StockExit (rejected)                                                                                                             |

**Properties allowlist:**

| Property             | Type    | Req/Opt  | Example          | Privacy                                |
| -------------------- | ------- | -------- | ---------------- | -------------------------------------- |
| `sku_id`             | integer | required | `1`              | SAFE                                   |
| `sku_code`           | string  | required | `"CLT-SNK-W-42"` | SAFE                                   |
| `warehouse`          | string  | required | `"LA"`           | SAFE (enum)                            |
| `requested_quantity` | integer | required | `100`            | SAFE                                   |
| `available_quantity` | integer | required | `30`             | SAFE                                   |
| `shortfall`          | integer | required | `70`             | SAFE (computed: requested - available) |

**Forbidden:** Raw exception text, stack trace.

| Field              | Value                                                                                                                                                                                                     |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Delivery**       | STREAM                                                                                                                                                                                                    |
| **Rationale**      | Stock shortages have immediate operational impact — customer orders may be delayed or canceled. Stream enables real-time alerts to warehouse managers.                                                    |
| **Volume**         | LOW (occasional — happens only when stock is insufficient)                                                                                                                                                |
| **Sampling**       | NONE (capture all)                                                                                                                                                                                        |
| **Throttle**       | NONE                                                                                                                                                                                                      |
| **Deduplication**  | `eventId` — provides a stable idempotency/deduplication key. A collector may suppress repeated delivery of the same eventId without collapsing distinct business attempts. No compound time-window dedup. |
| **Schema version** | 1.0                                                                                                                                                                                                       |

---

#### `warehouse_mismatch_rejected`

| Field                 | Value                                                                                                      |
| --------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                                |
| **Category**          | Inventory / Operations                                                                                     |
| **Business question** | How often do operators attempt to register stock movements for a SKU in the wrong warehouse?               |
| **Decision enabled**  | Operator training investment; UI improvement (e.g. pre-filter warehouse based on selected SKU)             |
| **Trigger**           | POST `/inventory/orders/inbound` or `/outbound` — HTTP 400 with `detail` containing `"Warehouse mismatch"` |
| **Producer**          | backend                                                                                                    |
| **Entity**            | StockEntry / StockExit (rejected)                                                                          |

**Properties allowlist:**

| Property              | Type    | Req/Opt  | Example          | Privacy                 |
| --------------------- | ------- | -------- | ---------------- | ----------------------- |
| `operation_type`      | string  | required | `"inbound"`      | SAFE (inbound/outbound) |
| `sku_id`              | integer | required | `1`              | SAFE                    |
| `sku_code`            | string  | required | `"CLT-SNK-W-42"` | SAFE                    |
| `expected_warehouse`  | string  | required | `"LA"`           | SAFE                    |
| `attempted_warehouse` | string  | required | `"ZGZ"`          | SAFE                    |

**Forbidden:** Raw exception text, stack trace, user identification beyond what's in envelope.

| Field              | Value                                                                             |
| ------------------ | --------------------------------------------------------------------------------- |
| **Delivery**       | BATCH                                                                             |
| **Rationale**      | Warehouse mismatch is an operator training signal; periodic review is sufficient. |
| **Volume**         | VERY LOW (occasional user error)                                                  |
| **Sampling**       | NONE (capture all)                                                                |
| **Throttle**       | NONE                                                                              |
| **Deduplication**  | `eventId`                                                                         |
| **Schema version** | 1.0                                                                               |

---

#### `sku_duplicate_rejected`

| Field                 | Value                                                                                                                        |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                                                  |
| **Category**          | Inventory / Operations                                                                                                       |
| **Business question** | Are operators attempting to create SKUs that already exist? Does this indicate a problem with the SKU discovery/search flow? |
| **Decision enabled**  | UI improvement (search-before-create prompt); operator training                                                              |
| **Trigger**           | POST `/inventory/products` — HTTP 409 with `detail` containing `"already exists"`                                            |
| **Producer**          | backend                                                                                                                      |
| **Entity**            | SKU (rejected)                                                                                                               |

**Properties allowlist:**

| Property   | Type   | Req/Opt  | Example          | Privacy |
| ---------- | ------ | -------- | ---------------- | ------- |
| `sku_code` | string | required | `"CLT-SNK-W-42"` | SAFE    |

**Forbidden:** Raw exception text, stack trace.

| Field              | Value                                                                              |
| ------------------ | ---------------------------------------------------------------------------------- |
| **Delivery**       | BATCH                                                                              |
| **Rationale**      | Duplicate attempt analysis is a UX improvement signal; periodic review sufficient. |
| **Volume**         | VERY LOW                                                                           |
| **Sampling**       | NONE (capture all)                                                                 |
| **Throttle**       | NONE                                                                               |
| **Deduplication**  | `eventId`                                                                          |
| **Schema version** | 1.0                                                                                |

---

### 3.3 Authentication / Session Events

---

#### `login_succeeded`

| Field                 | Value                                                                                              |
| --------------------- | -------------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                        |
| **Category**          | Authentication / Session                                                                           |
| **Business question** | When are users logging in? What is the daily/weekly active user count? Are there peak usage times? |
| **Decision enabled**  | Infrastructure scaling; maintenance window scheduling; feature release timing                      |
| **Trigger**           | POST `/auth/login` — HTTP 200 success                                                              |
| **Producer**          | backend                                                                                            |
| **Entity**            | User session                                                                                       |

**Properties allowlist:**

| Property    | Type   | Req/Opt  | Example     | Privacy                         |
| ----------- | ------ | -------- | ----------- | ------------------------------- |
| `user_role` | string | required | `"manager"` | SAFE (enum: admin/manager/user) |

**Note:** `userId` from the envelope carries the pseudonymous user UUID. No email, no doc_id.

**Forbidden:** Email, password (any form), JWT, IP address.

| Field              | Value                                                                               |
| ------------------ | ----------------------------------------------------------------------------------- |
| **Delivery**       | BATCH                                                                               |
| **Rationale**      | Active user counts and patterns are aggregate metrics; daily summary is sufficient. |
| **Volume**         | LOW-MEDIUM (per login event)                                                        |
| **Sampling**       | NONE (capture all)                                                                  |
| **Throttle**       | NONE                                                                                |
| **Deduplication**  | `eventId`                                                                           |
| **Schema version** | 1.0                                                                                 |

---

#### `login_failed`

| Field                 | Value                                                                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                                                                 |
| **Category**          | Authentication / Session                                                                                                                    |
| **Business question** | Is there a brute-force attack in progress? Are specific accounts being targeted? Are users repeatedly failing due to forgotten credentials? |
| **Decision enabled**  | Account lockout policy; CAPTCHA enforcement; security alerting; user self-service password reset promotion                                  |
| **Trigger**           | POST `/auth/login` — HTTP 401 (wrong password, inactive account, email not found)                                                           |
| **Producer**          | backend                                                                                                                                     |
| **Entity**            | User session (failed)                                                                                                                       |

**Properties allowlist:**

| Property         | Type   | Req/Opt  | Example            | Privacy                                                         |
| ---------------- | ------ | -------- | ------------------ | --------------------------------------------------------------- |
| `failure_reason` | string | required | `"wrong_password"` | SAFE (enum: email_not_found, wrong_password, inactive)          |
| `user_role`      | string | optional | `"user"`           | SAFE — only if authentication progressed enough to resolve role |

**Explicitly forbidden:** Raw email, raw password, IP address, any form of credential.

**IP-based rate-limiting note:** If rate-limiting requires an IP-derived key, apply HMAC-SHA256 with an ephemeral key (discarded after the rate-limit window). Never include a persistent IP-derived token in the event payload.

| Field              | Value                                                                                                                |
| ------------------ | -------------------------------------------------------------------------------------------------------------------- |
| **Delivery**       | STREAM                                                                                                               |
| **Rationale**      | Failed logins are a security signal — brute-force detection and account takeovers require near-real-time visibility. |
| **Volume**         | LOW (legitimate users) but can spike during attacks                                                                  |
| **Sampling**       | NONE (capture all for security); throttle above 20 events/min per ephemeral IP-hash key                              |
| **Throttle**       | Max 20 events/min per ephemeral IP-hash key (aggregated, not in event payload)                                       |
| **Deduplication**  | `eventId`                                                                                                            |
| **Schema version** | 1.0                                                                                                                  |

---

#### `user_registered`

| Field                 | Value                                                                         |
| --------------------- | ----------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                   |
| **Category**          | Authentication / Session                                                      |
| **Business question** | How many new accounts are created per day/week? What is the user growth rate? |
| **Decision enabled**  | Onboarding flow investment; license/user-based cost planning                  |
| **Trigger**           | POST `/users` — HTTP 201 success                                              |
| **Producer**          | backend                                                                       |
| **Entity**            | User                                                                          |

**Properties allowlist:**

| Property    | Type   | Req/Opt  | Example  | Privacy                                                 |
| ----------- | ------ | -------- | -------- | ------------------------------------------------------- |
| `user_role` | string | required | `"user"` | SAFE (always `"user"` — registrations are self-service) |

**Note:** `userId` from envelope carries the newly created user's UUID. No email.

**Forbidden:** Email, name, phone, address, password.

| Field              | Value                                                             |
| ------------------ | ----------------------------------------------------------------- |
| **Delivery**       | BATCH                                                             |
| **Rationale**      | User growth is a cumulative metric; daily aggregation sufficient. |
| **Volume**         | LOW                                                               |
| **Sampling**       | NONE (capture all)                                                |
| **Throttle**       | NONE                                                              |
| **Deduplication**  | `eventId`                                                         |
| **Schema version** | 1.0                                                               |

---

### 3.4 Supplier Events

---

#### `supplier_status_changed`

| Field                 | Value                                                                                              |
| --------------------- | -------------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                        |
| **Category**          | Suppliers                                                                                          |
| **Business question** | How many suppliers are being suspended vs reactivated? Which carrier categories are most affected? |
| **Decision enabled**  | Carrier performance monitoring; supplier portfolio risk assessment; contract renegotiation timing  |
| **Trigger**           | PATCH `/suppliers/{id}/status` — HTTP 200 success                                                  |
| **Producer**          | backend                                                                                            |
| **Entity**            | Supplier                                                                                           |

**Properties allowlist:**

| Property          | Type          | Req/Opt  | Example                 | Privacy           |
| ----------------- | ------------- | -------- | ----------------------- | ----------------- |
| `supplier_id`     | integer       | required | `5`                     | SAFE              |
| `previous_status` | string        | required | `"active"`              | SAFE (enum)       |
| `new_status`      | string        | required | `"suspended"`           | SAFE (enum)       |
| `country`         | string        | required | `"USA"`                 | SAFE (enum)       |
| `categories`      | array[string] | required | `["carrier_last_mile"]` | SAFE (enum array) |

**Forbidden:** `contact_email`, `notes`, any free-text fields.

| Field              | Value                                                                                          |
| ------------------ | ---------------------------------------------------------------------------------------------- |
| **Delivery**       | BATCH                                                                                          |
| **Rationale**      | Supplier status changes are periodic; daily/weekly review sufficient for portfolio monitoring. |
| **Volume**         | VERY LOW (occasional status changes)                                                           |
| **Sampling**       | NONE (capture all)                                                                             |
| **Throttle**       | NONE                                                                                           |
| **Deduplication**  | `eventId`                                                                                      |
| **Schema version** | 1.0                                                                                            |

---

### 3.5 Error / Validation Events

---

#### `api_validation_error`

| Field                 | Value                                                                                                             |
| --------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                                       |
| **Category**          | Errors / Validation                                                                                               |
| **Business question** | Which API fields and endpoints generate the most validation errors? Are users repeatedly submitting invalid data? |
| **Decision enabled**  | Form/UX improvement prioritization; field label clarification; API documentation updates                          |
| **Trigger**           | FastAPI `RequestValidationError` raised on any endpoint (422 default or 400 for /incidents)                       |
| **Producer**          | backend                                                                                                           |
| **Entity**            | API request                                                                                                       |

**Properties allowlist:**

| Property      | Type    | Req/Opt  | Example              | Privacy                                      |
| ------------- | ------- | -------- | -------------------- | -------------------------------------------- |
| `path`        | string  | required | `"/api/incidents"`   | SAFE (normalized path — no query parameters) |
| `http_method` | string  | required | `"POST"`             | SAFE                                         |
| `error_code`  | string  | required | `"validation_error"` | SAFE (normalized code)                       |
| `field`       | string  | optional | `"title"`            | SAFE (field name only, not value)            |
| `status_code` | integer | required | `400`                | SAFE                                         |

**Explicitly forbidden:** Raw request body, submitted field values, raw exception text, stack trace, filesystem paths.

| Field              | Value                                                                                    |
| ------------------ | ---------------------------------------------------------------------------------------- |
| **Delivery**       | BATCH                                                                                    |
| **Rationale**      | Validation error patterns inform UX decisions; aggregated analysis is sufficient.        |
| **Volume**         | LOW-MEDIUM (depends on user errors)                                                      |
| **Sampling**       | Sample at 1:10 for non-incident endpoints; 100% for /incidents endpoints (critical path) |
| **Throttle**       | Max 100 events/hr per `userId` to prevent abuse-driven volume spikes                     |
| **Deduplication**  | `eventId`                                                                                |
| **Schema version** | 1.0                                                                                      |

---

#### `api_server_error`

| Field                 | Value                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                 |
| **Category**          | Errors / Validation                                                                         |
| **Business question** | Are there unexpected backend failures? Which endpoints are failing and with what frequency? |
| **Decision enabled**  | Hotfix prioritization; bug tracking; regression detection; reliability SLA monitoring       |
| **Trigger**           | Unhandled exception reaching `unhandled_exception_handler` (HTTP 500)                       |
| **Producer**          | backend                                                                                     |
| **Entity**            | API request                                                                                 |

**Properties allowlist:**

| Property      | Type    | Req/Opt  | Example                   | Privacy                |
| ------------- | ------- | -------- | ------------------------- | ---------------------- |
| `path`        | string  | required | `"/inventory/products"`   | SAFE (normalized path) |
| `http_method` | string  | required | `"GET"`                   | SAFE                   |
| `error_code`  | string  | required | `"internal_server_error"` | SAFE (normalized code) |
| `status_code` | integer | required | `500`                     | SAFE                   |

**Explicitly forbidden:** Raw exception message, stack trace, filesystem paths, request body, any variable values, secrets, environment variable values.

| Field              | Value                                                                                                        |
| ------------------ | ------------------------------------------------------------------------------------------------------------ |
| **Delivery**       | STREAM                                                                                                       |
| **Rationale**      | Server errors indicate potential service degradation — must be visible in near-real-time for rapid response. |
| **Volume**         | VERY LOW (should be rare in production)                                                                      |
| **Sampling**       | NONE (capture all — every 500 matters)                                                                       |
| **Throttle**       | NONE (but should trigger pager-duty alert downstream)                                                        |
| **Deduplication**  | `eventId`                                                                                                    |
| **Schema version** | 1.0                                                                                                          |

---

### 3.6 Performance Events

---

#### `inventory_query_duration`

| Field                 | Value                                                                                                                                                     |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Classification**    | Opportunity                                                                                                                                               |
| **Category**          | Performance                                                                                                                                               |
| **Business question** | Are the computed-stock queries (`SUM(entries) - SUM(exits)`) degrading as the database grows? Is the `/inventory/products` list endpoint becoming slower? |
| **Decision enabled**  | Materialized view introduction; index optimization; read-model caching; database migration timing                                                         |
| **Trigger**           | Completion of `_stock_for_sku()` calls inside `list_products()` and `get_product()`                                                                       |
| **Producer**          | backend                                                                                                                                                   |
| **Entity**            | Performance measurement                                                                                                                                   |

**Properties allowlist:**

| Property      | Type    | Req/Opt  | Example                 | Privacy                                           |
| ------------- | ------- | -------- | ----------------------- | ------------------------------------------------- |
| `endpoint`    | string  | required | `"/inventory/products"` | SAFE                                              |
| `sku_count`   | integer | optional | `6`                     | SAFE (number of SKUs queried — for list endpoint) |
| `duration_ms` | integer | required | `45`                    | SAFE (milliseconds, integer)                      |
| `warehouse`   | string  | optional | `"LA"`                  | SAFE (for single product queries)                 |

**Forbidden:** Query text, database credentials, connection strings, schema details.

| Field              | Value                                                                                                                                         |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **Delivery**       | STREAM                                                                                                                                        |
| **Rationale**      | Performance degradation must be detected early to prevent user-visible slowdowns. Stream enables alerting when p95 latency exceeds threshold. |
| **Volume**         | LOW (limited inventory endpoints, few users)                                                                                                  |
| **Sampling**       | NONE (capture all)                                                                                                                            |
| **Throttle**       | NONE                                                                                                                                          |
| **Deduplication**  | `eventId`                                                                                                                                     |
| **Schema version** | 1.0                                                                                                                                           |

---

## 4. Incident >24h Strategy

### Decision: Derive age downstream (OPTION A)

Incidents that have been open or in-progress for more than 24 hours will be **detected downstream** by the telemetry pipeline, not by a scheduled event producer.

**Justification:**

1. **No redundant events.** The `incident_created` event carries `created_at`/`timestamp`. The `incident_status_transition` event records every state change. A downstream batch process (or streaming analysis window) can compute age = `now - created_at` for all incidents whose latest status is `open` or `in_progress`.

2. **Correct by construction.** Deriving age from the event stream guarantees consistency: if a stale incident transitions to `resolved` at minute 1439 (before the 24h mark), it will correctly not appear in the >24h report. A scheduled `incident_stale_detected` event could race with that status transition.

3. **CEO requirement implementable.** The downstream consumer (e.g., a daily report job or a streaming window) will:
   - For each `incident_created` event, record the incident + `created_at`.
   - For each `incident_status_transition` event, update the incident's current status.
   - Periodically (every 5 minutes for stream, hourly for batch), emit a `stale_incidents` aggregate for incidents where `status in (open, in_progress)` and `age > 24h`.

4. **Future flexibility.** If real-time >24h alerts become necessary, a streaming window can emit alerts without changing the producer instrumentation.

**Explicitly excluded from the event catalog:** `incident_stale_detected` — the event is not needed as a raw telemetry event. The derived aggregate can serve as a dashboard metric or alert trigger.

---

## 5. Direct Stock Modification Design Note

**The current architecture intentionally does not expose a direct stock edit endpoint.** Stock changes occur exclusively through the well-defined business operations:

| Operation                | Endpoint                          | Effect                                          |
| ------------------------ | --------------------------------- | ----------------------------------------------- |
| Inbound (goods receipt)  | POST `/inventory/orders/inbound`  | INSERT into `stock_entries`                     |
| Outbound (dispatch/loss) | POST `/inventory/orders/outbound` | INSERT into `stock_exits`                       |
| Stock computation        | (read-only)                       | `SUM(entries) - SUM(exits)` per SKU + warehouse |

There is no PUT `/inventory/stock/{sku_id}` or similar direct mutation endpoint. Therefore:

- **Status: NOT_APPLICABLE_IN_CURRENT_ARCHITECTURE** — a `direct_stock_mutation_rejected` event cannot currently be emitted because the application does not expose a direct stock mutation endpoint.
- The `outbound_insufficient_stock` event is the closest analogue — it detects when an attempted legitimate operation fails due to stock constraints.
- If a future version introduces a direct stock adjustment endpoint (e.g., for inventory corrections after physical count), the telemetry catalog **must** add a `direct_stock_mutation_rejected` or equivalent event at that boundary.

---

## 6. Stream vs Batch Summary

| Event Type                    | Delivery   | Reasoning                                               |
| ----------------------------- | ---------- | ------------------------------------------------------- |
| `incident_created`            | **STREAM** | CEO needs real-time critical incident visibility        |
| `incident_status_transition`  | **STREAM** | SLA breach detection (>24h) requires near-real-time     |
| `sku_created`                 | **BATCH**  | Catalog growth is a cumulative metric                   |
| `inbound_registered`          | **BATCH**  | Shift-level metric; daily aggregation sufficient        |
| `outbound_registered`         | **BATCH**  | Dispatch/loss ratio is periodic                         |
| `outbound_insufficient_stock` | **STREAM** | Immediate operational impact — needs real-time alert    |
| `warehouse_mismatch_rejected` | **BATCH**  | Training signal; periodic review sufficient             |
| `sku_duplicate_rejected`      | **BATCH**  | UX signal; periodic review sufficient                   |
| `login_succeeded`             | **BATCH**  | Active user counts are aggregate metrics                |
| `login_failed`                | **STREAM** | Security signal — brute-force detection needs real-time |
| `user_registered`             | **BATCH**  | User growth is cumulative                               |
| `supplier_status_changed`     | **BATCH**  | Portfolio monitoring; periodic review sufficient        |
| `api_validation_error`        | **BATCH**  | UX improvement; aggregated analysis sufficient          |
| `api_server_error`            | **STREAM** | Service degradation requires immediate visibility       |
| `inventory_query_duration`    | **STREAM** | Performance degradation must be detected early          |

---

## 7. Event Catalog Summary

### Summary Table

| event_type                    | Classification            | Category                 | Producer | Delivery | Volume     | Sampling                              | SchemaVersion |
| ----------------------------- | ------------------------- | ------------------------ | -------- | -------- | ---------- | ------------------------------------- | ------------- |
| `incident_created`            | Context-Derived Mandatory | Incidents                | backend  | STREAM   | MEDIUM     | NONE                                  | 1.0           |
| `incident_status_transition`  | Context-Derived Mandatory | Incidents                | backend  | STREAM   | LOW        | NONE                                  | 1.0           |
| `sku_created`                 | Opportunity               | Inventory / Operations   | backend  | BATCH    | VERY LOW   | NONE                                  | 1.0           |
| `inbound_registered`          | Opportunity               | Inventory / Operations   | backend  | BATCH    | LOW        | NONE                                  | 1.0           |
| `outbound_registered`         | Opportunity               | Inventory / Operations   | backend  | BATCH    | LOW        | NONE                                  | 1.0           |
| `outbound_insufficient_stock` | Opportunity               | Inventory / Operations   | backend  | STREAM   | LOW        | NONE                                  | 1.0           |
| `warehouse_mismatch_rejected` | Opportunity               | Inventory / Operations   | backend  | BATCH    | VERY LOW   | NONE                                  | 1.0           |
| `sku_duplicate_rejected`      | Opportunity               | Inventory / Operations   | backend  | BATCH    | VERY LOW   | NONE                                  | 1.0           |
| `login_succeeded`             | Opportunity               | Authentication / Session | backend  | BATCH    | LOW-MEDIUM | NONE                                  | 1.0           |
| `login_failed`                | Opportunity               | Authentication / Session | backend  | STREAM   | LOW        | NONE                                  | 1.0           |
| `user_registered`             | Opportunity               | Authentication / Session | backend  | BATCH    | LOW        | NONE                                  | 1.0           |
| `supplier_status_changed`     | Opportunity               | Suppliers                | backend  | BATCH    | VERY LOW   | NONE                                  | 1.0           |
| `api_validation_error`        | Opportunity               | Errors / Validation      | backend  | BATCH    | LOW-MEDIUM | 1:10 (non-incident); 100% (incidents) | 1.0           |
| `api_server_error`            | Opportunity               | Errors / Validation      | backend  | STREAM   | VERY LOW   | NONE                                  | 1.0           |
| `inventory_query_duration`    | Opportunity               | Performance              | backend  | STREAM   | LOW        | NONE (capture all)                    | 1.0           |

### Counts

| Metric                               | Value                                                                                                      |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| **Context-Derived Mandatory Events** | **2** (`incident_created`, `incident_status_transition`)                                                   |
| **Mandatory Requirements Covered**   | **5** (via 2 event types + downstream derivation)                                                          |
| **Opportunity Events**               | **13**                                                                                                     |
| **Total Selected Events**            | **15**                                                                                                     |
| **Categories Covered**               | **6** (Incidents, Inventory/Operations, Authentication/Session, Suppliers, Errors/Validation, Performance) |
| **Stream Events**                    | **6**                                                                                                      |
| **Batch Events**                     | **9**                                                                                                      |

### Requirements Verification

| Requirement                               | Met?     | How                                           |
| ----------------------------------------- | -------- | --------------------------------------------- |
| ✅ >= 8 opportunity events                | YES — 13 |                                               |
| ✅ >= 3 categories                        | YES — 6  |                                               |
| ✅ All events have business question      | YES      | Per-event definition                          |
| ✅ All events have concrete decision      | YES      | Per-event definition                          |
| ✅ All events have allowlist              | YES      | Per-event definition                          |
| ✅ All events have privacy classification | YES      | Per-property classification                   |
| ✅ No raw sensitive payloads              | YES      | Enforced via allowlist + forbidden properties |
| ✅ No invented application behavior       | YES      | Every trigger verified against actual code    |

---

## 8. Rejected or Not Applicable Candidates

The following Phase 1 candidates were **excluded** from the final catalog. Each exclusion is deliberate — these events either provide marginal decision value, duplicate other events, or would require behavior that does not exist.

| Phase 1 Candidate                  | Reason for Rejection                                                                                                                                                                                                                                                     |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `incident_stale_detected`          | Redundant — age is derived downstream from `incident_created` + `incident_status_transition` (see [Section 4](#4-incident-24h-strategy)). An explicit stale-detection event would require a scheduler and could race with status transitions.                            |
| `password_reset_requested`         | Weak decision value. The backend always returns 200 (to prevent email enumeration); a telemetry event would provide no additional signal. Volume is very low.                                                                                                            |
| `password_reset_completed`         | Marginal decision value. Resets are extremely rare. If security auditing requires it in the future, this can be added from the backend log context.                                                                                                                      |
| `password_changed`                 | Marginal decision value per event, though useful for aggregate. Excluded to keep auth event set minimal. If security incident investigation needs individual change events, add later.                                                                                   |
| `session_expired`                  | Redundant — session expiry is already detectable on the frontend (401 → `auth:expired` event → redirect to login). The `login_succeeded` event after expiry already marks a new session.                                                                                 |
| `supplier_created`                 | Very low volume (suppliers are seeded and rarely added). Decision value is marginal — supplier portfolio changes are infrequent and well-known to operations.                                                                                                            |
| `supplier_rate_updated`            | Very low volume. Rate changes are financially significant but the small number of suppliers means this data is better tracked in the supplier database itself.                                                                                                           |
| `page_navigated` (all page routes) | High noise-to-signal ratio. Only 6 operational pages exist; navigation patterns can be derived from the event stream's `sessionId` + event ordering. A dedicated page navigation event adds noise without enabling a decision that the other events don't already cover. |
| `direct_stock_mutation_rejected`   | **NOT_APPLICABLE_IN_CURRENT_ARCHITECTURE.** The system has no direct stock edit endpoint. Stock changes only through inbound/outbound operations. (See [Section 5](#5-direct-stock-modification-design-note).)                                                           |

---

## 9. Out of Scope for This Design Exercise

This document is an **implementation specification only**. The following are explicitly out of scope:

- ❌ Analytics SDK selection or installation
- ❌ Event transport mechanism (HTTP, message queue, file-based)
- ❌ Event collector / ingestion service
- ❌ Telemetry database or storage
- ❌ Dashboards or visualization
- ❌ Alerting or notification system
- ❌ Instrumentation code (backend middleware, frontend hooks)
- ❌ Any modification to `services/api/`, `uis/backoffice/`, or any other application code
- ❌ Infrastructure provisioning (queues, databases, containers)

**Implementation will begin in a future phase** after the full event catalog and schemas are validated. The current artifact is a design plan, not a runtime system.

---

## 10. Telemetry Risks and Failure Modes

This section documents the key risks inherent in any telemetry pipeline. Each risk includes a design-phase mitigation that the current catalog already incorporates. **No runtime mechanisms are implemented here** — these mitigations are architectural guidelines for the future implementation phase.

---

### 10.1 Duplicate Emission

| Aspect                | Description                                                                                                                                                                                                                                                                                                                                                                        |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Risk**              | The same event may be emitted more than once (producer retry, network duplication, middleware double-write).                                                                                                                                                                                                                                                                       |
| **Impact**            | Inflated counts, broken aggregations, incorrect SLA metrics.                                                                                                                                                                                                                                                                                                                       |
| **Design Mitigation** | Every event carries an `eventId` (UUID v4) that serves as a stable idempotency/deduplication key. A collector may suppress repeated delivery of the same `eventId` without collapsing distinct business attempts. Events with transition semantics use `eventId` + `requestId` for retry correlation. No compound time-window dedup is needed — the `eventId` alone is sufficient. |

---

### 10.2 Event Loss

| Aspect                | Description                                                                                                                                                                                                                                                                                                                                                                               |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Risk**              | Telemetry events may be dropped before reaching storage (network failure, collector crash, queue overflow).                                                                                                                                                                                                                                                                               |
| **Impact**            | Gaps in dashboards, missed alerts, incomplete audit trail.                                                                                                                                                                                                                                                                                                                                |
| **Design Mitigation** | The future implementation **should** consider producer-level buffering and retry for critical STREAM events. However, **a business operation must never fail because telemetry transport fails** — telemetry is advisory, not transactional. The catalog classifies each event's delivery expectation (STREAM vs BATCH), which guides the implementation's retry/buffer investment level. |

---

### 10.3 Out-of-Order Delivery

| Aspect                | Description                                                                                                                                                                                                                                                                                                                                                          |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Risk**              | Events may arrive at the collector in a different order than they occurred (async transport, retry after temporary failure, clock differences between producers).                                                                                                                                                                                                    |
| **Impact**            | Wrong status computed for "latest" state; incorrect transition ordering.                                                                                                                                                                                                                                                                                             |
| **Design Mitigation** | Each event carries an authoritative `timestamp` (ISO 8601 UTC, set by the producer at occurrence time) and a unique `eventId`. Downstream processing **must not assume arrival order equals occurrence order**. For incident lifecycles, the downstream aggregate computes current state from the event stream using `incident_id` + `timestamp`, not arrival order. |

---

### 10.4 Clock Skew

| Aspect                | Description                                                                                                                                                                                                                                                                                                                                                                                        |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Risk**              | Producer wall clocks may drift, causing timestamps to be inaccurate relative to each other or to UTC.                                                                                                                                                                                                                                                                                              |
| **Impact**            | Misleading latency/SLA metrics; >24h detection window errors.                                                                                                                                                                                                                                                                                                                                      |
| **Design Mitigation** | All backend events use **server-generated timestamps** normalized to UTC. The `timestamp` format (`2026-10-05T14:30:00.000Z`) enforces UTC with no offset. Frontend timestamps (for session events) are acceptable but clearly flagged as potentially less precise. A future implementation may apply clock-skew correction by comparing producer timestamps against collector arrival timestamps. |

---

### 10.5 Incompatible Schema Versions

| Aspect                | Description                                                                                                                                                                                                                                                                                                                                                                             |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Risk**              | A producer emits an event with a newer payload shape that the collector or downstream consumers cannot parse.                                                                                                                                                                                                                                                                           |
| **Impact**            | Event rejection, partial data loss, pipeline crash.                                                                                                                                                                                                                                                                                                                                     |
| **Design Mitigation** | Every event includes a `schemaVersion` field (`const: "1.0"`). The event schemas define strict property allowlists with `additionalProperties: false`. A future implementation should validate incoming events against the expected schema version and reject or route mismatched payloads. Breaking changes require incrementing `schemaVersion` and updating the JSON Schema catalog. |

---

### 10.6 Telemetry Collector / Pipeline Unavailable

| Aspect                | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Risk**              | The telemetry ingestion service (collector, message queue, storage) is down or unreachable.                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **Impact**            | Events cannot be delivered; telemetry backlog grows; eventual data loss if buffer overflows.                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| **Design Mitigation** | Telemetry failure **must not block operational workflows** — the backend API continues to function even if telemetry transport fails. The catalog's STREAM vs BATCH classification guides the implementation's retry and backpressure strategy: STREAM events may justify lightweight in-process buffering with bounded retry; BATCH events can tolerate longer retry intervals. Future implementation should implement a bounded retry queue with graceful degradation (drop events under extreme backpressure rather than block the application). |

---

### 10.7 Privacy / PII Leakage

| Aspect                | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Risk**              | Sensitive user data (email, name, address, credentials) inadvertently included in event payloads.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Impact**            | GDPR/privacy-regulation violation, reputational damage, legal liability.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **Design Mitigation** | The catalog enforces three layers of protection: (1) **Strict allowlists** — every event defines exactly which properties are permitted; (2) **`additionalProperties: false`** — both on the envelope and on every property schema, rejecting any undeclared field; (3) **Forbidden-property policy** — passwords, tokens, hashes, stack traces, filesystem paths, raw exception messages, and free-text fields are explicitly banned. Additionally, `userId` uses the pseudonymous `user.uuid` (never email or doc_id), and `sessionId` must be HMAC-SHA256-hashed for retention beyond 30 days. |

---

### 10.8 Excessive Event Volume / Cost Growth

| Aspect                | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Risk**              | Telemetry volume grows unboundedly, increasing storage, bandwidth, and processing costs beyond the value delivered.                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| **Impact**            | Cost overruns, pipeline saturation, operational noise.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Design Mitigation** | Every event includes a per-event volume estimate (VERY LOW to MEDIUM), a sampling strategy, and a throttle rule. Sampling is applied only where justified (e.g., 1:10 for non-critical validation errors). Throttle rules protect against abuse-driven spikes (e.g., max 20 login-fail events/min per ephemeral IP key; max 100 validation-error events/hr per `userId`). Critical events (incidents, server errors, security failures) are **never sampled**. A future implementation should monitor telemetry volume and raise a flag if any event type exceeds its estimated ceiling. |

---

## 11. Cost / Volume / Retention by Category

This section consolidates the per-event volume, retention, and cost considerations by category. The values are sourced from the per-event definitions in Section 3 above.

| Category                   | Events | Expected Volume        | Retention / Privacy Sensitivity                           | Cost Concern                                                                      | Sampling / Throttle Approach                                                                        |
| -------------------------- | ------ | ---------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **Incidents**              | 2      | MEDIUM + LOW           | **Low** — all properties are SAFE enums or integers       | Minimal — two STREAM events with low individual payload size                      | NONE (capture all); no sampling or throttle for critical operational data                           |
| **Inventory/Operations**   | 6      | VERY LOW to LOW        | **Low** — SAFE enums, SKU codes, counts, booleans         | Low — mostly BATCH with low volume; one STREAM event (insufficient stock) is rare | NONE (capture all); no sampling — every inventory event matters for stock accuracy                  |
| **Authentication/Session** | 3      | LOW to LOW-MEDIUM      | **Medium** — pseudonymous user UUIDs; securetly-sensitive | Moderate — login_failed is STREAM and can spike during attacks; throttle protects | NONE for counts; throttle for security (20 login_fail/min per IP-hash); login_succeeded is BATCH    |
| **Suppliers**              | 1      | VERY LOW               | **Low** — SAFE enums, integer IDs                         | Negligible — one BATCH event, very rare                                           | NONE (capture all)                                                                                  |
| **Errors/Validation**      | 2      | VERY LOW to LOW-MEDIUM | **Low** — normalized codes, paths; no raw values          | Low — most are BATCH; api_server_error is STREAM but VERY LOW volume              | Sampling for api_validation_error (1:10 non-critical, 100% incidents); throttle (100/hr per userId) |
| **Performance**            | 1      | LOW                    | **Low** — SAFE integers, endpoint names, warehouse enum   | Low — STREAM but low volume; payload is tiny (duration_ms + endpoint)             | NONE (capture all); no throttle — every slow query matters                                          |

### Key Principles

1. **No raw PII** is captured in any category — all six categories rely on SAFE or Pseudonymous properties only.
2. **Free-text fields are universally banned** — no category includes `description`, `notes`, or `title` values.
3. **STREAM events are budgeted for latency** — incidents (real-time ops), insufficient stock (operations alert), login failures (security), server errors (reliability), and query duration (performance) justify the streaming cost.
4. **BATCH events are budgeted for volume** — the remaining 9 events can be aggregated daily/weekly, minimizing transport and storage cost.
5. **No invented dollar amounts** — cost concerns are expressed categorically (Negligible / Minimal / Low / Moderate) based on volume estimates and retention needs, not conjectural pricing.
