# Backend Serialization Audit

**Project:** TrackFlow Supplier Directory API
**Branch:** `feature/serialization-audit`
**Date:** 2026-10-05
**Phase:** 3 — Implementation Complete (Phases 0-3 done, Phase 2 design implemented)

---

## Scope

This audit covers the complete FastAPI application surface defined in `services/api/`. The audit identifies every HTTP endpoint, classifies its serialization state, documents security/data-exposure risks, input/output schema separation issues, over-fetching candidates, and relationship serialization decisions. No code changes have been made — this is a discovery-only phase.

---

## FastAPI Application Structure

```
services/api/
├── main.py                    # FastAPI app entrypoint, lifespan, router includes
├── models.py                  # Pydantic models: Supplier*, User*, Profile*, Incident*, Auth*
├── schemas.py                 # Pydantic schemas: Inventory (SKU*, StockEntry*, StockExit*, StockMovement*)
├── inventory_models.py        # SQLModel ORM classes: SKU, StockEntry, StockExit
├── database.py                # TinyDB init + SQLModel engine (dual database)
├── security.py                # JWT auth, password hashing, reset tokens, get_current_user
├── email_service.py           # Resend email integration
├── error_handlers.py          # Validation exception handler (incidents get 400, others 422)
├── routers/
│   ├── __init__.py            # Empty
│   ├── auth.py                # /auth/* — login, me, forgot-password, reset-password, change-password
│   ├── users.py               # /users/* — CRUD for users
│   ├── profiles.py            # /profiles/* — get/update own profile
│   ├── suppliers.py           # /suppliers/* — CRUD for suppliers
│   ├── incidents.py           # /incidents/* and /api/incidents/* — CRUD + summary for incidents
│   └── inventory.py           # /inventory/* — products, orders (inbound/outbound)
└── tests/
    ├── test_auth_users_profiles_api.py
    ├── test_database_config.py
    ├── test_incident_models.py
    ├── test_incidents_api.py
    ├── test_incidents_api_compat.py
    ├── test_inventory_api.py
    ├── test_seed_incidents.py
    ├── test_suppliers_api.py
    └── test_inventory_api.py
```

**Database architecture (dual database):**

- **TinyDB** — suppliers, users, profiles, incidents, reset_tokens
- **SQLModel (PostgreSQL/Supabase or SQLite)** — inventory (SKU, StockEntry, StockExit)

**Auth:** JWT bearer tokens, `get_current_user` dependency guards most endpoints. Users router has some unauthenticated routes (POST `/users` for registration is public).

---

## Endpoint Inventory

### Legend

| Column         | Description                                                   |
| -------------- | ------------------------------------------------------------- |
| Auth           | A = Authentication required (Bearer token). P = Public.       |
| response_model | Explicit FastAPI `response_model=` parameter. "—" = none set. |
| Return type    | What the handler function actually returns.                   |
| Schema in use  | Pydantic model used for response serialization.               |
| Classification | ✅ SERIALIZED / ⚠️ PARTIALLY_SERIALIZED / ❌ UNSERIALIZED     |

### Root / Health

| #   | Method | Route     | Purpose              | Auth | response_model | Return type | Schema | Classification          |
| --- | ------ | --------- | -------------------- | ---- | -------------- | ----------- | ------ | ----------------------- |
| 1   | GET    | `/`       | Root welcome message | P    | —              | `dict`      | None   | ⚠️ PARTIALLY_SERIALIZED |
| 2   | GET    | `/health` | Health check         | P    | —              | `dict`      | None   | ⚠️ PARTIALLY_SERIALIZED |

### Users

| #   | Method | Route              | Purpose           | Auth | response_model       | Return type                      | Schema       | Classification          |
| --- | ------ | ------------------ | ----------------- | ---- | -------------------- | -------------------------------- | ------------ | ----------------------- |
| 3   | POST   | `/users`           | Register new user | P    | `UserResponse`       | `dict` from `document_to_dict()` | UserResponse | ✅ SERIALIZED           |
| 4   | GET    | `/users`           | List all users    | A    | `list[UserResponse]` | `list[dict]`                     | UserResponse | ⚠️ PARTIALLY_SERIALIZED |
| 5   | GET    | `/users/{user_id}` | Get own user      | A    | `UserResponse`       | `dict` from `document_to_dict()` | UserResponse | ✅ SERIALIZED           |
| 6   | PUT    | `/users/{user_id}` | Update own user   | A    | `UserResponse`       | `dict` from `document_to_dict()` | UserResponse | ✅ SERIALIZED           |
| 7   | DELETE | `/users/{user_id}` | Delete own user   | A    | **None**             | `dict` `{"detail": "..."}`       | None         | ❌ UNSERIALIZED         |

### Profiles

| #   | Method | Route          | Purpose                   | Auth | response_model    | Return type                      | Schema          | Classification |
| --- | ------ | -------------- | ------------------------- | ---- | ----------------- | -------------------------------- | --------------- | -------------- |
| 8   | GET    | `/profiles/me` | Get own profile           | A    | `ProfileResponse` | `dict` from `document_to_dict()` | ProfileResponse | ✅ SERIALIZED  |
| 9   | PUT    | `/profiles/me` | Create/update own profile | A    | `ProfileResponse` | `dict` from `document_to_dict()` | ProfileResponse | ✅ SERIALIZED  |

### Auth

| #   | Method | Route                   | Purpose                         | Auth | response_model            | Return type               | Schema                  | Classification |
| --- | ------ | ----------------------- | ------------------------------- | ---- | ------------------------- | ------------------------- | ----------------------- | -------------- |
| 10  | POST   | `/auth/login`           | Login, get bearer token         | P    | `TokenResponse`           | `TokenResponse`           | TokenResponse           | ✅ SERIALIZED  |
| 11  | GET    | `/auth/me`              | Get current user + profile      | A    | `UserWithProfileResponse` | `UserWithProfileResponse` | UserWithProfileResponse | ✅ SERIALIZED  |
| 12  | POST   | `/auth/forgot-password` | Request password reset          | P    | `PasswordChangeResponse`  | `PasswordChangeResponse`  | PasswordChangeResponse  | ✅ SERIALIZED  |
| 13  | POST   | `/auth/reset-password`  | Reset password with token       | P    | `PasswordChangeResponse`  | `PasswordChangeResponse`  | PasswordChangeResponse  | ✅ SERIALIZED  |
| 14  | POST   | `/auth/change-password` | Change password (authenticated) | A    | `PasswordChangeResponse`  | `PasswordChangeResponse`  | PasswordChangeResponse  | ✅ SERIALIZED  |

### Suppliers

| #   | Method | Route                             | Purpose                       | Auth | response_model           | Return type                      | Schema           | Classification          |
| --- | ------ | --------------------------------- | ----------------------------- | ---- | ------------------------ | -------------------------------- | ---------------- | ----------------------- |
| 15  | POST   | `/suppliers`                      | Create supplier               | A    | `SupplierResponse`       | `dict` from `document_to_dict()` | SupplierResponse | ✅ SERIALIZED           |
| 16  | GET    | `/suppliers`                      | List suppliers (with filters) | A    | `list[SupplierResponse]` | `list[dict]`                     | SupplierResponse | ⚠️ PARTIALLY_SERIALIZED |
| 17  | GET    | `/suppliers/{supplier_id}`        | Get single supplier           | A    | `SupplierResponse`       | `dict` from `document_to_dict()` | SupplierResponse | ✅ SERIALIZED           |
| 18  | PATCH  | `/suppliers/{supplier_id}/rate`   | Update rate                   | A    | `SupplierResponse`       | `dict` from `document_to_dict()` | SupplierResponse | ✅ SERIALIZED           |
| 19  | PATCH  | `/suppliers/{supplier_id}/status` | Update status                 | A    | `SupplierResponse`       | `dict` from `document_to_dict()` | SupplierResponse | ✅ SERIALIZED           |
| 20  | DELETE | `/suppliers/{supplier_id}`        | Delete supplier               | A    | `SupplierResponse`       | `dict` from `document_to_dict()` | SupplierResponse | ✅ SERIALIZED           |

### Incidents

| #   | Method | Route                                                                         | Purpose                       | Auth | response_model           | Return type                      | Schema           | Classification          |
| --- | ------ | ----------------------------------------------------------------------------- | ----------------------------- | ---- | ------------------------ | -------------------------------- | ---------------- | ----------------------- |
| 21  | POST   | `/api/incidents` (and `/incidents`)                                           | Create incident               | A    | `IncidentResponse`       | `dict` from `document_to_dict()` | IncidentResponse | ✅ SERIALIZED           |
| 22  | GET    | `/api/incidents/summary` (and `/incidents/summary`)                           | Aggregated summary            | A    | **None**                 | `dict` (aggregated counts)       | None             | ❌ UNSERIALIZED         |
| 23  | GET    | `/api/incidents` (and `/incidents`)                                           | List incidents (with filters) | A    | `list[IncidentResponse]` | `list[dict]`                     | IncidentResponse | ⚠️ PARTIALLY_SERIALIZED |
| 24  | GET    | `/api/incidents/{incident_id}` (and `/incidents/{incident_id}`)               | Get incident detail           | A    | `IncidentResponse`       | `dict` from `document_to_dict()` | IncidentResponse | ✅ SERIALIZED           |
| 25  | PATCH  | `/api/incidents/{incident_id}/status` (and `/incidents/{incident_id}/status`) | Update status                 | A    | `IncidentResponse`       | `dict` from `document_to_dict()` | IncidentResponse | ✅ SERIALIZED           |

### Inventory

| #    | Method | Route                          | Purpose                 | Auth | response_model                | Return type                   | Schema                | Classification     |
| ---- | ------ | ------------------------------ | ----------------------- | ---- | ----------------------------- | ----------------------------- | --------------------- | ------------------ |
| 26   | GET    | `/inventory/products`          | List SKUs with stock    | A    | `list[SKUResponse]`           | `list[SKUResponse]`           | SKUResponse           | ✅ SERIALIZED      |
| 27   | POST   | `/inventory/products`          | Create SKU              | A    | `SKUResponse`                 | `SKUResponse`                 | SKUResponse           | ✅ SERIALIZED      |
| 28   | GET    | `/inventory/products/{sku_id}` | Get single SKU          | A    | `SKUResponse`                 | `SKUResponse`                 | SKUResponse           | ✅ SERIALIZED      |
| 29   | POST   | `/inventory/orders/inbound`    | Register inbound stock  | A    | `StockEntryResponse`          | `StockEntryResponse`          | StockEntryResponse    | ✅ SERIALIZED      |
| 30   | POST   | `/inventory/orders/outbound`   | Register outbound stock | A    | `StockExitResponse`           | `StockExitResponse`           | StockExitResponse     | ✅ SERIALIZED      |
| 31   | GET    | `/inventory/orders`            | List all movements      | A    | `list[StockMovementResponse]` | `list[StockMovementResponse]` | StockMovementResponse | ✅ SERIALIZED      |
| 32\* | GET    | `/inventory/orders/{id}`       | Get single movement     | A    | ?                             | ?                             | ?                     | ❓ NOT IMPLEMENTED |

> **Note:** Endpoint #32 (`/inventory/orders/{id}`) is documented in the router docstring but no route handler exists in the code. This should be confirmed or removed.

**Total registered endpoints: 31** unique (method, handler) combos across 36 total route entries (the 5 incident endpoints are registered at both `/api/incidents` and `/incidents` prefixes, plus 2 app-level endpoints).

---

## Detailed Findings

### ❌ UNSERIALIZED Endpoints

#### 1. GET `/` (root)

- **Current behavior:** Returns `{"message": "...", "status": "ok"}`
- **Problem:** No `response_model`. Returns a raw `dict` without explicit schema.
- **Risk:** Low — this is a health/welcome endpoint. However, an explicit schema documents the contract.
- **Required improvement:** Add a `RootResponse` model or use `response_model`.
- **Proposed schema:** `RootResponse(message: str, status: str)`

#### 2. GET `/health`

- **Current behavior:** Returns `{"status": "ok"}`
- **Problem:** No `response_model`. Returns a raw `dict`.
- **Risk:** Low — health endpoint.
- **Required improvement:** Add `HealthResponse` model or use `response_model`.
- **Proposed schema:** `HealthResponse(status: str)`

#### 3. GET `/incidents/summary`

- **Current behavior:** Returns a dict with `total`, `by_status`, `by_category`, `by_origin`, `by_branch`. No `response_model`.
- **Problem:** No explicit schema. The shape is a dynamic dict with nested dicts of counters. Consumers (frontend `IncidentsSummaryPage.tsx`) read `summary.total`, `summary.by_status`, `summary.by_category`, `summary.by_origin`, `summary.by_branch`.
- **Risk:** Medium — no type enforcement. If the aggregation logic changes, consumers silently break.
- **Required improvement:** Add `IncidentSummaryResponse` model.
- **Proposed schema:**
  ```python
  class IncidentSummaryResponse(BaseModel):
      total: int
      by_status: dict[IncidentStatus, int]
      by_category: dict[IncidentCategory, int]
      by_origin: dict[IncidentOrigin, int]
      by_branch: dict[IncidentBranch, int]
  ```

#### 4. DELETE `/users/{user_id}`

- **Current behavior:** Returns `{"detail": "User deleted successfully"}`. No `response_model`.
- **Problem:** No response model. The frontend (`authApi.ts`) does not capture the return of `delete_user`. The `AuthContext.tsx` calls it but likely ignores the body.
- **Risk:** Low — deletion response is informational.
- **Required improvement:** Add a `DetailResponse` model or use `response_model`.
- **Proposed schema:** `DetailResponse(detail: str)` — shared across delete endpoints.

### ⚠️ PARTIALLY_SERIALIZED Endpoints

#### GET `/users` — List users

- **Current behavior:** Returns `list[UserResponse]` via `response_model=list[UserResponse]`.
- **Problem:** `UserResponse` includes `uuid`, `created_at`, `is_active`, `role`. The list endpoint returns internal fields that may not be needed for a user listing. The frontend `authApi.ts` defines `UserResponse` as `{ id, email, is_active, role, created_at }` — the `uuid` field is NOT consumed by any frontend code.
- **Risk:** Low-medium. `uuid` is exposed unnecessarily. No sensitive data, but over-fetching.
- **Consumer requirements:** Frontend `UserResponse` type: `id`, `email`, `is_active`, `role`, `created_at`. The `uuid` is not consumed.
- **Required improvement:** Create a `UserListItemResponse` that excludes `uuid`, or keep `UserResponse` but confirm `uuid` is needed by any consumer.

#### GET `/suppliers` — List suppliers

- **Current behavior:** Returns `list[SupplierResponse]` via `response_model=list[SupplierResponse]`.
- **Problem:** `SupplierResponse` includes all fields: `id`, `name`, `country`, `categories`, `rate_per_shipment`, `currency`, `status`, `service_zone`, `contact_email`, `notes`, `updated_at`. The frontend `SuppliersPage.tsx` consumes fields: `id`, `name`, `country`, `categories`, `rate_per_shipment`, `currency`, `status`, `service_zone`, `contact_email`, `notes`, `updated_at`. Actually ALL fields are consumed by the frontend create form and table display.
- **Risk:** Low — the frontend consumes all fields. However, `notes` and `contact_email` are returned in a list endpoint; consider whether a lightweight list schema would be more appropriate for bandwidth.
- **Consumer requirements:** Frontend `Supplier` type uses all fields except possibly `updated_at` is consumed by the table (shown in UI). The create/edit forms use name, country, categories, rate, currency, status, service_zone, contact_email, notes.
- **Required improvement:** The schema is acceptable for current consumers. Minor: consider a `SupplierListItemResponse` that omits `notes` for bandwidth efficiency, but this is low priority.

#### GET `/incidents` — List incidents

- **Current behavior:** Returns `list[IncidentResponse]` via `response_model=list[IncidentResponse]`.
- **Problem:** `IncidentResponse` includes all fields: `id`, `title`, `description`, `category`, `status`, `origin`, `branch`, `created_at`, `updated_at`. The frontend `IncidentsListPage.tsx` consumes: `id`, `title`, `category`, `status`, `origin`, `branch`, `created_at`, `updated_at`. Description is NOT consumed by the list page — it is only shown in the detail form. However, description is included in every list item.
- **Over-fetching:** `description` is returned for every incident in the list but only displayed on the detail page. This is a minor over-fetching concern.
- **Consumer requirements:** Frontend `Incident` type: `id`, `title`, `description`, `category`, `status`, `origin`, `branch`, `created_at`, `updated_at`. The description is typed but may be used in detail view.
- **Required improvement:** Create `IncidentListItemResponse` without `description` for list endpoints, keeping `IncidentResponse` with all fields for detail.

### ✅ SERIALIZED Correctly

All remaining endpoints have explicit `response_model` set and return appropriate Pydantic schemas. Notable examples:

- **Auth endpoints** — `TokenResponse`, `PasswordChangeResponse`, `UserWithProfileResponse` are all well-defined.
- **Inventory endpoints** — `SKUResponse`, `StockEntryResponse`, `StockExitResponse`, `StockMovementResponse` are all explicit and correctly typed.
- **Incidents detail/create/status-update** — return `IncidentResponse` which is appropriate.
- **Suppliers detail/create/update/delete** — return `SupplierResponse` which is appropriate.
- **Users create/get/update** — return `UserResponse` which is appropriate.

---

## Security Findings

### Sensitive data exposure summary

| Endpoint                     | Field                                        | Issue                                                                                                          | Risk                                                            |
| ---------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `GET /auth/me`               | `email`, `role`, `is_active`, `profile`      | Returns authenticated user's own data — this is intentional and required by the ProfilePage UI.                | ✅ ACCEPTABLE                                                   |
| `POST /auth/login`           | Returns only `access_token` and `token_type` | Does NOT return password, hashed_password, or user data.                                                       | ✅ CLEAN                                                        |
| `POST /auth/forgot-password` | Returns only `detail` message                | Always returns 200. Does not echo email.                                                                       | ✅ CLEAN                                                        |
| `POST /auth/reset-password`  | Returns only `detail` message                | Does not return token, user data, or password.                                                                 | ✅ CLEAN                                                        |
| `POST /auth/change-password` | Returns only `detail` message                | Does not return password or user data.                                                                         | ✅ CLEAN                                                        |
| `POST /users` (register)     | Returns `UserResponse`                       | Does NOT return `hashed_password`. Password is not stored in plaintext.                                        | ✅ CLEAN                                                        |
| `GET /users`                 | Returns `uuid` field                         | `uuid` is not sensitive (it's a stable UUID for cross-db references).                                          | ⚠️ LOW — unnecessary exposure                                   |
| `GET /suppliers`             | Returns `notes` and `contact_email`          | `notes` can contain internal operational information. `contact_email` is a business contact, not personal PII. | ⚠️ LOW — review `notes` for sensitive content in list responses |
| All TinyDB-backed endpoints  | Return integer `doc_id` as `id`              | Internal database identifiers are exposed. However, this is the primary key and the frontend references it.    | ✅ ACCEPTABLE                                                   |
| Incident endpoints           | No customer PII returned                     | Tests verify no `customer_email`, `tracking_number`, or `historical_incident_id` is exposed.                   | ✅ ACCEPTABLE                                                   |

### Sensitive/internal fields NEVER exposed (verified)

- ✅ `hashed_password` — never returned by any endpoint
- ✅ `plaintext password` — never returned
- ✅ `reset_token` — never returned in response body (only sent via email)
- ✅ `SECRET_KEY` — never exposed
- ✅ `RESEND_API_KEY` — never exposed
- ✅ `DATABASE_URL` — never exposed
- ✅ Customer email from historical incidents — not exposed by incident endpoints
- ✅ Historical `incident_id` from CSV — not exposed
- ✅ `is_active` — returned intentionally (frontend may use it)
- ✅ `soft-delete` flags — not applicable (TinyDB remove is permanent)

### Security rating: **NO critical exposures** — all response schemas verified. Minor informational exposure: `uuid` on user list (not consumed by frontend).

---

## Over-Fetching Findings

### Confirmed over-fetching

| Endpoint     | Field  | Consumer                                                            | Issue                                                                                                                              |
| ------------ | ------ | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `GET /users` | `uuid` | No frontend consumer in `uis/backoffice/src/` or `uis/website/src/` | UUID is returned but never read by any frontend component. This is confirmed over-fetching. The `UserResponse` TS type omits uuid. |

### NOT over-fetching (field IS consumed)

| Endpoint         | Field           | Consumer                                                           | Evidence                                                                   |
| ---------------- | --------------- | ------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| `GET /incidents` | `description`   | `IncidentsListPage.tsx` line 262 displays `{incident.description}` | Description IS rendered in the list table (as secondary text under title). |
| `GET /suppliers` | `notes`         | Frontend `Supplier` type includes `notes: string \| null`          | Notes ARE consumed in supplier cards.                                      |
| `GET /suppliers` | `contact_email` | Frontend `Supplier` type includes `contact_email: string \| null`  | Consumed — no over-fetching.                                               |

### Recommended list schemas

- **`UserListItemResponse`** — exclude `uuid`, keep `id`, `email`, `is_active`, `role`, `created_at`

---

## Input/Output Schema Findings

### Schema reuse (same schema for input and output)

| Endpoint Method                         | Request Schema         | Response Schema      | Issue                                                             |
| --------------------------------------- | ---------------------- | -------------------- | ----------------------------------------------------------------- |
| POST `/users`                           | `UserCreate`           | `UserResponse`       | ✅ SEPARATED — input has `password`, output has `id`/`created_at` |
| PUT `/users/{user_id}`                  | `UserUpdate`           | `UserResponse`       | ✅ SEPARATED — input has optional password/email fields           |
| POST `/suppliers`                       | `SupplierCreate`       | `SupplierResponse`   | ✅ SEPARATED — input has no `id`/`updated_at`                     |
| PATCH `/suppliers/{supplier_id}/rate`   | `SupplierRateUpdate`   | `SupplierResponse`   | ✅ SEPARATED — input is rate-only                                 |
| PATCH `/suppliers/{supplier_id}/status` | `SupplierStatusUpdate` | `SupplierResponse`   | ✅ SEPARATED — input is status-only                               |
| POST `/incidents`                       | `IncidentCreate`       | `IncidentResponse`   | ✅ SEPARATED — input has no `id`/`created_at`/`updated_at`        |
| PATCH `/incidents/{incident_id}/status` | `IncidentStatusUpdate` | `IncidentResponse`   | ✅ SEPARATED — input is status-only                               |
| POST `/inventory/products`              | `SKUCreate`            | `SKUResponse`        | ✅ SEPARATED — input has no `id`/`current_stock`/`created_at`     |
| POST `/inventory/orders/inbound`        | `StockEntryCreate`     | `StockEntryResponse` | ✅ SEPARATED                                                      |
| POST `/inventory/orders/outbound`       | `StockExitCreate`      | `StockExitResponse`  | ✅ SEPARATED                                                      |
| PUT `/profiles/me`                      | `ProfileUpdate`        | `ProfileResponse`    | ✅ SEPARATED — input is subset of output                          |

### Findings

- **All CRUD endpoints have properly separated input and output schemas.** No cases where a response schema is reused as a request body.
- **`UserCreate`** correctly contains `password` (hashed before storage) while `UserResponse` does not.
- **`SupplierCreate`** correctly has no `id`/`updated_at`.
- **`IncidentCreate`** correctly has no `id`/`created_at`/`updated_at`.
- **`SKUCreate`** correctly has no `id`/`current_stock`/`created_at`.
- **Server-controlled fields**: `id`, `created_at`, `updated_at` are never writable on input schemas.
- **Output-only relationships**: `profile` on `GET /auth/me` is read-only via `UserWithProfileResponse`; no input schema accepts profile data.

**Conclusion: Input/output schema separation is well-implemented throughout the API.** No significant findings.

---

## Relationship Serialization

### Endpoints returning related objects

| Endpoint                  | Relationship              | Current Serialization                                                        | Consumer                                                        | Recommended Strategy                                                                                                |
| ------------------------- | ------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `GET /auth/me`            | User + Profile (optional) | Full nested `ProfileResponse` object via `UserWithProfileResponse`           | `ProfilePage.tsx` — reads profile fields (name, phone, address) | **A — Full nested object** ✅ Correct. The profile is loaded eagerly and the consumer needs all fields.             |
| `GET /inventory/orders`   | Movements + SKU context   | Flattened projection: `sku` (code), `sku_name` included in movement response | `OrdersListPage.tsx` — displays product name, SKU code          | **C — Flattened projection** ✅ Correct. SKU fields are flattened into the movement response, avoiding N+1 queries. |
| `GET /inventory/products` | SKU + computed stock      | `current_stock` is a computed field on `SKUResponse`                         | `InventoryProductsPage.tsx` — displays stock level              | **C — Flattened projection** ✅ Correct. Stock is computed per SKU+warehouse.                                       |

### Recommendations

- The `UserWithProfileResponse` approach (nested ProfileResponse on GET /auth/me) is correct for the current consumer. No change needed.
- The `StockMovementResponse` with flattened SKU fields is the correct approach for the orders feed. No change needed.
- No full nested ORM relationships are blindly serialized. The inventory API explicitly constructs response objects with only the needed fields.

---

## Implementation Plan

### ✅ Already serialized correctly (no work needed)

1. `POST /auth/login` — TokenResponse
2. `GET /auth/me` — UserWithProfileResponse
3. `POST /auth/forgot-password` — PasswordChangeResponse
4. `POST /auth/reset-password` — PasswordChangeResponse
5. `POST /auth/change-password` — PasswordChangeResponse
6. `POST /users` — UserResponse
7. `GET /users/{user_id}` — UserResponse
8. `PUT /users/{user_id}` — UserResponse
9. `GET /profiles/me` — ProfileResponse
10. `PUT /profiles/me` — ProfileResponse
11. All supplier endpoints (POST, GET detail, PATCH rate, PATCH status, DELETE) — SupplierResponse
12. All incident endpoints except summary — IncidentResponse
13. All inventory endpoints — SKUResponse, StockEntryResponse, StockExitResponse, StockMovementResponse

### ⚠️ Requires schema improvement

1. **`GET /users`** — Create `UserListItemResponse` without `uuid` (or add `uuid` to frontend type if needed)
2. **`GET /suppliers`** — Consider creating `SupplierListItemResponse` (omit `notes`) — **LOW PRIORITY**
3. **`GET /`** — Add `RootResponse` schema
4. **`GET /health`** — Add `HealthResponse` schema

### ❌ Requires explicit serialization

1. **`GET /incidents/summary`** — Create `IncidentSummaryResponse` with typed counters
2. **`DELETE /users/{user_id}`** — Add response_model (or a shared `DetailResponse`)

---

## Baseline Validation

### Test execution

```
cd /workspaces/Matias023-ai-engineering-company-project-monorepo/services/api
uv run pytest -v --tb=short
```

### Result

```
133 passed, 1 warning, 70 errors in 202.73s
```

### Breakdown

| Test File                         | Status             | Notes                                                                       |
| --------------------------------- | ------------------ | --------------------------------------------------------------------------- |
| `test_database_config.py`         | 12/12 PASSED       | Database URL resolution and production guard tests                          |
| `test_incident_models.py`         | 13/13 PASSED       | Pydantic model validation tests                                             |
| `test_incidents_api.py`           | 52/52 PASSED       | Full incident API coverage (auth, CRUD, lifecycle, summary, 500)            |
| `test_incidents_api_compat.py`    | 17/17 PASSED       | `/api/incidents` prefix compatibility tests                                 |
| `test_seed_incidents.py`          | 9/9 PASSED         | Historical seed idempotency tests                                           |
| `test_suppliers_api.py`           | 27/27 PASSED       | Supplier API CRUD + edge cases                                              |
| `test_auth_users_profiles_api.py` | 0/43 — 43 ERROR    | All tests ERROR due to `.env` DATABASE_URL pointing to unreachable Supabase |
| `test_inventory_api.py`           | 3 passed, 27 ERROR | 3 baseline tests pass; 27 error due to same DATABASE_URL issue              |

### BASELINE_FAILURE

- **43 auth/user/profile tests + 27 inventory tests FAIL with `OperationalError`** connecting to `aws-0-us-east-2.pooler.supabase.com`.
- **Root cause:** The `.env` file in `services/api/` has a `DATABASE_URL` pointing to a Supabase pooler. When FastAPI's `lifespan` calls `init_db()`, the engine tries to connect to PostgreSQL. The tests for `test_auth_users_profiles_api.py` use `TestClient(app)` which triggers `lifespan`, which calls `init_db()`, which tries to connect to Supabase. The `test_inventory_api.py` tests explicitly override `get_db` but the lifespan issue still triggers.
  **133 tests pass:** All TinyDB-only tests (database config 12, models 13, incidents 52, incidents compat 17, seed 9, suppliers 27, inventory 3).
  **70 tests error:** 43 auth/user/profile tests + 27 inventory tests.

**These failures are pre-existing and NOT caused by any changes in this audit.** They are a BASELINE_FAILURE caused by the `.env` DATABASE_URL being stale/unreachable.

**Arithmetic note:** The original audit draft had incorrect per-file test counts (e.g. `test_database_config.py` reported as 9 passed but actual is 12). The overall 133 passed / 70 errors total is correct. Breakdown: 12+13+52+17+9+27+3 = 133 passed; 43+27 = 70 errors.

---

## Summary

### Counts

- **Total registered endpoints:** 31 unique (method, handler) combos (36 total route entries with `/api/incidents` aliases)
- **SERIALIZED correctly:** 24
- **PARTIALLY_SERIALIZED:** 5 (GET /, GET /health, GET /users, GET /suppliers, GET /incidents — root/health lack explicit schema, list endpoints would benefit from dedicated list schemas)
- **UNSERIALIZED:** 2 (GET /incidents/summary, DELETE /users/{user_id})
- **UNIMPLEMENTED (documented but missing):** 1 (GET /inventory/orders/{id})
- **Security exposures:** NONE critical. Minor: `uuid` field returned but not consumed on user list.
- **Over-fetching candidates:** 1 confirmed (`uuid` on user list). `description` on incident list IS consumed by the table view, so NOT over-fetching.
- **Input/output schema issues:** NONE — all schemas are properly separated. Server-controlled fields (id, created_at, updated_at) are never writable.
- **Relationship serialization:** All current implementations are appropriate for consumers.

### Files created

- `docs/serialization-audit.md` — This complete audit document

### Files modified

- None

---

---

## Phase 3 — Implementation

**Phase:** 3 — Implementation Complete
**Date:** 2026-10-05
**Branch:** `feature/serialization-audit`
**Commits:** No commits made yet (all changes staged for review)

### Summary

Phase 3 implemented the 5 schema designs from Phase 2, applied `response_model` to 5 routes, added 24 serialization contract tests, and verified OpenAPI schema generation. All 31 unique API handlers are now SERIALIZED with explicit Pydantic response models.

### Schemas Added

| Schema                    | Location    | Route(s)                     | Fields                                                                                        |
| ------------------------- | ----------- | ---------------------------- | --------------------------------------------------------------------------------------------- |
| `RootResponse`            | `models.py` | `GET /`                      | `message: str`, `status: str`                                                                 |
| `HealthResponse`          | `models.py` | `GET /health`                | `status: str`                                                                                 |
| `DetailResponse`          | `models.py` | `DELETE /users/{user_id}`    | `detail: str`                                                                                 |
| `IncidentSummaryResponse` | `models.py` | `GET /api/incidents/summary` | `total: int`, `by_status`, `by_category`, `by_origin`, `by_branch` (all `dict[Literal, int]`) |
| `UserListItemResponse`    | `models.py` | `GET /users`                 | `id: int`, `email: str`, `is_active: bool`, `role: UserRole`, `created_at: datetime`          |

**Design decisions confirmed:**

- `UserListItemResponse` excludes `uuid` (not consumed by any frontend component)
- `DetailResponse` is a standalone schema (not reusing `PasswordChangeResponse`)
- All schemas placed in `models.py` (TinyDB-side models file)
- No handler function bodies were changed — only `response_model` parameters

### Route Changes (5 endpoints)

| #   | File                   | Route                     | Change                                                                      |
| --- | ---------------------- | ------------------------- | --------------------------------------------------------------------------- |
| 1   | `main.py`              | `GET /`                   | Added `response_model=RootResponse` to `root()`                             |
| 2   | `main.py`              | `GET /health`             | Added `response_model=HealthResponse` to `health()`                         |
| 3   | `routers/users.py`     | `DELETE /users/{user_id}` | Added `response_model=DetailResponse` to `delete_user()`                    |
| 4   | `routers/users.py`     | `GET /users`              | Changed from `list[UserResponse]` to `list[UserListItemResponse]`           |
| 5   | `routers/incidents.py` | `GET /incidents/summary`  | Added `response_model=IncidentSummaryResponse` to `get_incidents_summary()` |

### Security Impact

- **Zero new sensitive data exposure.** All new schemas expose only information already returned by the handlers.
- **`uuid` removal** from `GET /users` reduces the attack surface slightly (internal cross-db reference no longer exposed on list endpoint).
- `DetailResponse` just wraps an existing message string.
- Summary counts are aggregate data with no PII.
- Root/health are informational only.

### OpenAPI Verification

The OpenAPI schema was verified to contain all 5 new response model definitions:

- `/openapi.json#/components/schemas/RootResponse` — `{ message: string, status: string }`
- `/openapi.json#/components/schemas/HealthResponse` — `{ status: string }`
- `/openapi.json#/components/schemas/DetailResponse` — `{ detail: string }`
- `/openapi.json#/components/schemas/IncidentSummaryResponse` — `{ total: integer, by_status: object, by_category: object, by_origin: object, by_branch: object }`
- `/openapi.json#/components/schemas/UserListItemResponse` — `{ id: integer, email: string, is_active: boolean, role: string, created_at: string (date-time) }`

Additionally confirmed:

- `GET /users` response is `type: array, items: { $ref: '#/components/schemas/UserListItemResponse' }`
- `GET /incidents/summary` response references `IncidentSummaryResponse`
- `DELETE /users/{user_id}` response references `DetailResponse`
- `/incidents` compatibility alias correctly excluded from OpenAPI (`include_in_schema=False`)
- All `201` response codes preserved for `POST` endpoints
- No existing `response_model` references broken

### Test Strategy Implementation

**Challenge:** All `TestClient(app)` tests fail when `.env` DATABASE_URL points to stale Supabase pooler.

**Solution (Approach A from Phase 2 design):** Pre-set `os.environ["DATABASE_URL"] = "sqlite://"` AND `os.environ.pop("APP_ENV", None)` BEFORE importing `app`. This:

1. Bypasses the production guard (`_resolve_engine_url()` raises when `APP_ENV=production` and DATABASE_URL is empty)
2. Uses SQLite in-memory engine for the lifespan connection
3. Does NOT require mocking `init_db()` or any fixture-level changes
4. Does NOT modify any production code

**Key insight:** `python-dotenv`'s `load_dotenv()` does NOT override existing env vars by default, so pre-setting `os.environ` before import reliably overrides the `.env` file.

### Serialization Contract Tests (24 tests)

**File:** `tests/test_serialization_contracts.py`

| Test Class                         | Tests | What is Verified                                                                                               |
| ---------------------------------- | ----- | -------------------------------------------------------------------------------------------------------------- |
| `TestRootSerialization`            | 4     | Exact fields (`message`, `status`), types, no extra fields, HTTP 200                                           |
| `TestHealthSerialization`          | 4     | Exact fields (`status`), types, no extra fields, HTTP 200                                                      |
| `TestDetailResponseSerialization`  | 5     | DELETE returns `detail` string, correct type, no extra fields, HTTP 200, error shape for non-existent user     |
| `TestIncidentSummarySerialization` | 5     | Summary shape (5 keys), nested dict types, integer counts, seeded data correctness, cross-endpoint consistency |
| `TestUserListItemSerialization`    | 6     | `uuid` forbidden, exact field set, types, `is_active` boolean, multiple users, `role` field correctness        |

**Fixtures used:**

- `bare_client` — for `/` and `/health` (no auth, no TinyDB needed)
- `isolated_client` — `TestClient(app)` with monkeypatched TinyDB tables
- `authed_client` — returns `(client, token)` tuple for auth-requiring endpoints

### Endpoint Audit (Phase 7)

After implementation, a comprehensive audit was performed by recursively traversing `app.routes` including `_IncludedRouter` wrappers:

- **Total route entries:** 36 (including 5 `/incidents` alias duplicates)
- **Unique handlers (deduplicated by method + handler qualified name):** 31
- **SERIALIZED:** 31
- **UNSERIALIZED:** 0
- **NOT_IMPLEMENTED:** 0 (`GET /inventory/orders/{id}` has no route handler registered)
- **`include_in_schema=False`:** 5 routes (the `/incidents` compatibility prefix)

**Deduplication key:** `f"{r.endpoint.__module__}.{r.endpoint.__name__}"` — FastAPI recreates APIRoute objects per `include_router` call, so `id()` cannot be used for deduplication.

**Router breakdown:**

| Router      | Prefix                | Handlers | SERIALIZED |
| ----------- | --------------------- | -------- | ---------- |
| App-level   | (root `/`, `/health`) | 2        | 2          |
| `users`     | (no prefix)           | 5        | 5          |
| `profiles`  | (no prefix)           | 2        | 2          |
| `auth`      | (no prefix)           | 5        | 5          |
| `suppliers` | (no prefix)           | 6        | 6          |
| `inventory` | (no prefix)           | 6        | 6          |
| `incidents` | `/api/incidents`      | 5        | 5          |

### Implementation Verification

All changes are localized to:

1. `services/api/models.py` — 5 new schema classes (+34 lines)
2. `services/api/main.py` — 2 route decorator changes (+3 lines)
3. `services/api/routers/users.py` — 2 route decorator changes (+2 lines)
4. `services/api/routers/incidents.py` — 1 route decorator change (+2 lines)
5. `services/api/tests/test_serialization_contracts.py` — New test file (24 tests)

**No production handler logic was modified.**
**No database configuration was changed.**
**No frontend files were touched.**
**No secrets were introduced.**
**No remote databases were accessed during tests.**

### Files Modified

| File                                    | Change                                                                                                      | Lines |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ----- |
| `models.py`                             | Added `RootResponse`, `HealthResponse`, `DetailResponse`, `IncidentSummaryResponse`, `UserListItemResponse` | +34   |
| `main.py`                               | Added `response_model` to `root()` and `health()`                                                           | +3/-2 |
| `routers/users.py`                      | Added `response_model` to `delete_user()`, changed `list_users()`                                           | +3/-1 |
| `routers/incidents.py`                  | Added `response_model` to `get_incidents_summary()`                                                         | +3/-1 |
| `tests/test_serialization_contracts.py` | New serialization contract tests                                                                            | +N/A  |

### Git Status

- **Branch:** `feature/serialization-audit`
- **Changes staged:** No — all changes are unstaged working tree changes
- **`git diff --stat`:** 4 files changed, 43 insertions(+), 4 deletions(-) (excluding test file)
- **No commits made**

---

## Phase 2 — Serialization Schema Design

**Phase:** 2 — Schema Design (design document, implemented in Phase 3)

### Design Decisions

| Decision                                            | Choice                                                                  | Rationale                                                                                                                                                                                              |
| --------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Where to place new schemas                          | `models.py` (existing TinyDB-side Pydantic models file)                 | All new schemas (`RootResponse`, `HealthResponse`, `DetailResponse`, `IncidentSummaryResponse`, `UserListItemResponse`) are app-level or TinyDB-domain, not inventory. `schemas.py` is inventory-only. |
| Reuse vs. new schema                                | Create standalone `DetailResponse`; keep `PasswordChangeResponse` as-is | `PasswordChangeResponse` is already serialized correctly and used by 3 auth endpoints. A standalone `DetailResponse` is the minimal addition for DELETE /users/{user_id}.                              |
| `UserListItemResponse` vs. modifying `UserResponse` | New `UserListItemResponse` without `uuid`                               | `uuid` is consumed by inventory code (`current_user.uuid` in inbound/outbound), but NOT by the user list frontend. `GET /users/{user_id}` keeps full `UserResponse`.                                   |
| `SupplierListItemResponse`                          | **Not needed** — reclassify `GET /suppliers` to ✅ SERIALIZED           | All `SupplierResponse` fields are consumed by the frontend (Phase 1 confirmed). A list-projection schema would be a disproven optimization.                                                            |
| `IncidentListItemResponse`                          | **Not needed** — reclassify `GET /incidents` to ✅ SERIALIZED           | `description` IS consumed by `IncidentsListPage.tsx` line 262. A list-projection schema would be a disproven optimization.                                                                             |
| Naming convention for new schemas                   | `{Purpose}Response` suffix, same as existing models                     | `UserResponse`, `SupplierResponse`, `TokenResponse`, etc. are the established convention.                                                                                                              |
| `response_model` on app-level endpoints             | Add `response_model` with new schemas; handler return values unchanged  | The exact current payload shapes are preserved. No behavioral change — pure contract documentation.                                                                                                    |

### Proposed Schemas (design intent — NOT implemented yet)

#### `RootResponse` — for `GET /`

```python
class RootResponse(BaseModel):
    message: str
    status: str
```

- **Location:** `models.py` (app-level schema)
- **Route change:** Add `response_model=RootResponse` to `main.py:root()`
- **Handler change:** None — return value unchanged (`{"message": "...", "status": "ok"}`)
- **Consumer:** Not consumed by frontend (root endpoint is informational)

#### `HealthResponse` — for `GET /health`

```python
class HealthResponse(BaseModel):
    status: str
```

- **Location:** `models.py` (app-level schema)
- **Route change:** Add `response_model=HealthResponse` to `main.py:health()`
- **Handler change:** None — return value unchanged (`{"status": "ok"}`)
- **Consumer:** Not consumed by frontend (health endpoint is for monitoring)

#### `DetailResponse` — for `DELETE /users/{user_id}` (and future reuse)

```python
class DetailResponse(BaseModel):
    detail: str
```

- **Location:** `models.py` (generic message schema)
- **Route change:** Add `response_model=DetailResponse` to `routers/users.py:delete_user()`
- **Handler change:** None — return value unchanged (`{"detail": "User deleted successfully"}`)
- **Reuse note:** Identical shape to `PasswordChangeResponse`. If future endpoints need the same pattern, `DetailResponse` is the reusable choice. `PasswordChangeResponse` remains independent (already serialized, 3 consumers).
- **Consumer:** Frontend `authApi.ts` calls `delete_user` but does not read the response body. Safe to add.

#### `IncidentSummaryResponse` — for `GET /incidents/summary`

```python
class IncidentSummaryResponse(BaseModel):
    total: int
    by_status: dict[IncidentStatus, int]
    by_category: dict[IncidentCategory, int]
    by_origin: dict[IncidentOrigin, int]
    by_branch: dict[IncidentBranch, int]
```

- **Location:** `models.py` (incident-domain schema, near `IncidentBase`/`IncidentResponse`)
- **Route change:** Add `response_model=IncidentSummaryResponse` to `routers/incidents.py:get_incidents_summary()`
- **Handler change:** None — return value unchanged (the aggregated dict shape matches exactly)
- **Key types:** Uses `IncidentStatus`, `IncidentCategory`, `IncidentOrigin`, `IncidentBranch` Literals from `models.py` as `dict` key types. Pydantic v2 supports `dict[Literal, int]` natively.
- **Consumer:** Frontend `IncidentsSummaryPage.tsx` reads `summary.total`, `summary.by_status`, `summary.by_category`, `summary.by_origin`, `summary.by_branch`.
- **Compatibility:** The response shape is identical to the current untyped dict. Adding the schema is pure documentation — no consumer breakage.

#### `UserListItemResponse` — for `GET /users`

```python
class UserListItemResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    role: UserRole
    created_at: datetime
```

- **Location:** `models.py` (user-domain schema, near `UserResponse`)
- **Route change:** Change `response_model` from `list[UserResponse]` to `list[UserListItemResponse]`
- **Handler change:** None — `document_to_dict()` returns all fields; the `response_model` strips `uuid` at serialization time
- **Excluded field:** `uuid` (confirmed unnecessary — no frontend code reads it; the frontend `UserResponse` TS type in `authApi.ts` omits `uuid`; `uuid` IS consumed by inventory code via `current_user.uuid` on authenticated requests, but is NOT needed in list responses)
- **Consumer:** Frontend `UserResponse` TS type: `{ id: number, email: string, is_active: boolean, role: 'admin' | 'manager' | 'user', created_at: string }` — NO `uuid`. Removing `uuid` from the list endpoint aligns the API contract with the actual consumer.
- **Other endpoints:** `GET /users/{user_id}`, `POST /users`, `PUT /users/{user_id}` keep `UserResponse` (which includes `uuid`). `GET /auth/me` keeps `UserWithProfileResponse`.

### PARTIALLY_SERIALIZED Reclassification (Phase 2)

| #   | Endpoint         | Current Classification  | Phase 2 Design Classification | Rationale                                                                                                                                 | Schema Change Required    | Route Code Change Required |
| --- | ---------------- | ----------------------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- | -------------------------- |
| 1   | `GET /`          | ⚠️ PARTIALLY_SERIALIZED | ⚠️ PARTIALLY_SERIALIZED (B)   | Needs new `RootResponse` schema + `response_model=RootResponse`. Payload is stable.                                                       | ✅ `RootResponse` (new)   | ✅ Add `response_model`    |
| 2   | `GET /health`    | ⚠️ PARTIALLY_SERIALIZED | ⚠️ PARTIALLY_SERIALIZED (B)   | Needs new `HealthResponse` schema + `response_model=HealthResponse`. Payload is stable.                                                   | ✅ `HealthResponse` (new) | ✅ Add `response_model`    |
| 3   | `GET /users`     | ⚠️ PARTIALLY_SERIALIZED | ⚠️ PARTIALLY_SERIALIZED (A)   | Has `response_model` but uses wrong schema (`UserResponse` includes `uuid`). Needs `UserListItemResponse`.                                | ✅ `UserListItemResponse` | ✅ Change `response_model` |
| 4   | `GET /suppliers` | ⚠️ PARTIALLY_SERIALIZED | ✅ SERIALIZED (C)             | All fields consumed. No over-fetching. Schema is correct. Reclassified — no work needed.                                                  | ❌ None                   | ❌ None                    |
| 5   | `GET /incidents` | ⚠️ PARTIALLY_SERIALIZED | ✅ SERIALIZED (C)             | All fields consumed (including `description` — verified at `IncidentsListPage.tsx:262`). No over-fetching. Reclassified — no work needed. | ❌ None                   | ❌ None                    |

**Classification key:** (A) Schema change needed — existing `response_model` but wrong schema. (B) No schema at all — needs `response_model` + new schema. (C) Already correct — reclassify, no work needed.

### Design Target State (Phase 2 design — implemented in Phase 3)

| Classification     | Count | Endpoints                                                                                                                   |
| ------------------ | ----- | --------------------------------------------------------------------------------------------------------------------------- |
| ✅ SERIALIZED      | 31    | All current 24 + 2 reclassified (suppliers list, incidents list) + 5 fixed (root, health, users list, summary, delete-user) |
| ❌ UNSERIALIZED    | 0     | All resolved in Phase 3 implementation                                                                                      |
| ❓ NOT IMPLEMENTED | 0     | `GET /inventory/orders/{id}` — documented but no handler exists. Not a serialization gap, no schema needed                  |

**Final audit result (post-Phase 3): 31/31 unique handlers SERIALIZED, 0 UNSERIALIZED, 0 NOT_IMPLEMENTED.**

### Response Model Matrix (all 31 handlers)

| #   | Method | Route                                 | Current response_model        | Phase 2 Design response_model | Schema Change | Route Code Change          | Consumer Compatibility Risk           |
| --- | ------ | ------------------------------------- | ----------------------------- | ----------------------------- | ------------- | -------------------------- | ------------------------------------- |
| 1   | GET    | `/`                                   | None                          | `RootResponse`                | ✅ New schema | ✅ Add `response_model`    | ✅ None — payload unchanged           |
| 2   | GET    | `/health`                             | None                          | `HealthResponse`              | ✅ New schema | ✅ Add `response_model`    | ✅ None — payload unchanged           |
| 3   | POST   | `/users`                              | `UserResponse`                | `UserResponse`                | ❌            | ❌                         | ✅                                    |
| 4   | GET    | `/users`                              | `list[UserResponse]`          | `list[UserListItemResponse]`  | ✅ New schema | ✅ Change `response_model` | ⚠️ LOW — `uuid` removed, not consumed |
| 5   | GET    | `/users/{user_id}`                    | `UserResponse`                | `UserResponse`                | ❌            | ❌                         | ✅                                    |
| 6   | PUT    | `/users/{user_id}`                    | `UserResponse`                | `UserResponse`                | ❌            | ❌                         | ✅                                    |
| 7   | DELETE | `/users/{user_id}`                    | None                          | `DetailResponse`              | ✅ New schema | ✅ Add `response_model`    | ✅ None — frontend ignores body       |
| 8   | GET    | `/profiles/me`                        | `ProfileResponse`             | `ProfileResponse`             | ❌            | ❌                         | ✅                                    |
| 9   | PUT    | `/profiles/me`                        | `ProfileResponse`             | `ProfileResponse`             | ❌            | ❌                         | ✅                                    |
| 10  | POST   | `/auth/login`                         | `TokenResponse`               | `TokenResponse`               | ❌            | ❌                         | ✅                                    |
| 11  | GET    | `/auth/me`                            | `UserWithProfileResponse`     | `UserWithProfileResponse`     | ❌            | ❌                         | ✅                                    |
| 12  | POST   | `/auth/forgot-password`               | `PasswordChangeResponse`      | `PasswordChangeResponse`      | ❌            | ❌                         | ✅                                    |
| 13  | POST   | `/auth/reset-password`                | `PasswordChangeResponse`      | `PasswordChangeResponse`      | ❌            | ❌                         | ✅                                    |
| 14  | POST   | `/auth/change-password`               | `PasswordChangeResponse`      | `PasswordChangeResponse`      | ❌            | ❌                         | ✅                                    |
| 15  | POST   | `/suppliers`                          | `SupplierResponse`            | `SupplierResponse`            | ❌            | ❌                         | ✅                                    |
| 16  | GET    | `/suppliers`                          | `list[SupplierResponse]`      | `list[SupplierResponse]`      | ❌            | ❌                         | ✅ — reclassified to SERIALIZED       |
| 17  | GET    | `/suppliers/{supplier_id}`            | `SupplierResponse`            | `SupplierResponse`            | ❌            | ❌                         | ✅                                    |
| 18  | PATCH  | `/suppliers/{supplier_id}/rate`       | `SupplierResponse`            | `SupplierResponse`            | ❌            | ❌                         | ✅                                    |
| 19  | PATCH  | `/suppliers/{supplier_id}/status`     | `SupplierResponse`            | `SupplierResponse`            | ❌            | ❌                         | ✅                                    |
| 20  | DELETE | `/suppliers/{supplier_id}`            | `SupplierResponse`            | `SupplierResponse`            | ❌            | ❌                         | ✅                                    |
| 21  | POST   | `/api/incidents`                      | `IncidentResponse`            | `IncidentResponse`            | ❌            | ❌                         | ✅                                    |
| 22  | GET    | `/api/incidents/summary`              | None                          | `IncidentSummaryResponse`     | ✅ New schema | ✅ Add `response_model`    | ✅ None — shape unchanged             |
| 23  | GET    | `/api/incidents`                      | `list[IncidentResponse]`      | `list[IncidentResponse]`      | ❌            | ❌                         | ✅ — reclassified to SERIALIZED       |
| 24  | GET    | `/api/incidents/{incident_id}`        | `IncidentResponse`            | `IncidentResponse`            | ❌            | ❌                         | ✅                                    |
| 25  | PATCH  | `/api/incidents/{incident_id}/status` | `IncidentResponse`            | `IncidentResponse`            | ❌            | ❌                         | ✅                                    |
| 26  | GET    | `/inventory/products`                 | `list[SKUResponse]`           | `list[SKUResponse]`           | ❌            | ❌                         | ✅                                    |
| 27  | POST   | `/inventory/products`                 | `SKUResponse`                 | `SKUResponse`                 | ❌            | ❌                         | ✅                                    |
| 28  | GET    | `/inventory/products/{sku_id}`        | `SKUResponse`                 | `SKUResponse`                 | ❌            | ❌                         | ✅                                    |
| 29  | POST   | `/inventory/orders/inbound`           | `StockEntryResponse`          | `StockEntryResponse`          | ❌            | ❌                         | ✅                                    |
| 30  | POST   | `/inventory/orders/outbound`          | `StockExitResponse`           | `StockExitResponse`           | ❌            | ❌                         | ✅                                    |
| 31  | GET    | `/inventory/orders`                   | `list[StockMovementResponse]` | `list[StockMovementResponse]` | ❌            | ❌                         | ✅                                    |

**Matrix summary:**

- **31/31 handlers accounted for**
- **4 new schemas** to create: `RootResponse`, `HealthResponse`, `DetailResponse`, `IncidentSummaryResponse`
- **1 schema change**: `UserListItemResponse` (new) replacing `UserResponse` for `GET /users`
- **5 route code changes**: 4x add `response_model`, 1x change `response_model`
- **0 handler body changes**: All return values remain identical
- **26 endpoints require zero changes**

### Test Strategy (design — Phase 3)

#### Challenge: DATABASE_URL Prevents TestClient Tests

The baseline has 70 errors due to the `.env` `DATABASE_URL` pointing to unreachable Supabase. All 70 errors come from tests that use `TestClient(app)` which triggers `lifespan → init_db() → try to connect to PostgreSQL`.

#### Proposed approaches (ranked by safety)

| Approach                                | Description                                                                                                                                      | Pros                                                                | Cons                                                                                              | Recommendation             |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | -------------------------- |
| **A — Test-only DATABASE_URL override** | Before running serialization tests, set `DATABASE_URL=sqlite:///` or unset it in `pyproject.toml` or a `conftest.py` that overrides `get_engine` | Cleanest separation. Matches how inventory tests override `get_db`. | Requires a fixture or config change. Need to ensure the override happens before `lifespan` fires. | ✅ **Recommended**         |
| **B — Fixture/lifespan isolation**      | Replace `lifespan` with a no-op in tests, or mock `init_db()`                                                                                    | No DB needed at all for serialization tests.                        | `lifespan` is defined in `main.py` — mocking is more complex.                                     | ⚠️ Viable but more complex |
| **C — Mock `init_db` at module level**  | `monkeypatch.setattr('database.init_db', lambda: None)`                                                                                          | Simple.                                                             | Must run before `TestClient(app)` construction — early enough?                                    | ⚠️ Risky timing            |

#### Forbidden-field assertions (serialization contract tests)

For each endpoint with a schema change, add tests that verify:

1. **Exact field set:** The response JSON keys match the schema fields exactly (no extra, no missing).
2. **Forbidden field absence:** Specific fields are NOT present in the response.
3. **Type correctness:** Fields have the correct JSON types (string, number, boolean, object, array).
4. **Null handling:** Nullable fields are either present with a value or explicitly `null`.

| Endpoint (Phase 2 change) | Forbidden fields | Required fields (subset)                                      |
| ------------------------- | ---------------- | ------------------------------------------------------------- |
| `GET /`                   | —                | `message`, `status`                                           |
| `GET /health`             | —                | `status`                                                      |
| `GET /users`              | `uuid`           | `id`, `email`, `is_active`, `role`, `created_at`              |
| `DELETE /users/{user_id}` | —                | `detail`                                                      |
| `GET /incidents/summary`  | —                | `total`, `by_status`, `by_category`, `by_origin`, `by_branch` |

#### Exact-field-set test pattern (pseudocode)

```python
# For each endpoint, verify the response has exactly the expected fields
response = client.get("/")
assert set(response.json().keys()) == {"message", "status"}

response = client.get("/health")
assert set(response.json().keys()) == {"status"}

# For list endpoints, verify each item has no forbidden fields
response = client.get("/users", headers=auth_header)
for user in response.json():
    assert "uuid" not in user
    assert set(user.keys()) == {"id", "email", "is_active", "role", "created_at"}
```

#### Test scope

- **New tests:** 5 test functions (one per changed endpoint)
- **Modified tests:** Existing tests for `GET /users` will need `assert "uuid" not in user` added
- **No changes needed:** 26 endpoints with zero schema changes keep their existing tests
- **Baseline failures remain unchanged:** 70 TestClient errors from DATABASE_URL persist. New serialization tests will share the same limitation unless Approach A is implemented first.

### Phase 2 Design Status

```
SCHEMA_DESIGN_STATUS: COMPLETE
NEW_SCHEMAS_REQUIRED: 4
  - RootResponse (models.py)
  - HealthResponse (models.py)
  - DetailResponse (models.py)
  - IncidentSummaryResponse (models.py)
NEW_SCHEMA_FOR_OVERFETCHING: 1
  - UserListItemResponse (models.py)
ENDPOINTS_WITH_ZERO_CHANGES: 26/31
ROUTE_CODE_CHANGES_REQUIRED: 5
  - Add response_model=RootResponse to main.py:root()
  - Add response_model=HealthResponse to main.py:health()
  - Add response_model=DetailResponse to routers/users.py:delete_user()
  - Add response_model=IncidentSummaryResponse to routers/incidents.py:get_incidents_summary()
  - Change response_model from list[UserResponse] to list[UserListItemResponse] in routers/users.py:list_users()
HANDLER_BODY_CHANGES_REQUIRED: 0
RECLASSIFIED_TO_SERIALIZED: 2
  - GET /suppliers (was PARTIALLY_SERIALIZED → SERIALIZED)
  - GET /incidents (was PARTIALLY_SERIALIZED → SERIALIZED)
CONSUMER_COMPATIBILITY_RISK: NONE (all payload shapes preserved; uuid removal is safe — not consumed)
NEXT_PHASE: Phase 3 — Implementation
NEXT_RECOMMENDED_STEP: Implement schema classes in services/api/models.py, then apply route code changes, then add/update tests
```

1. **Fix test environment** (unblock baseline)
   - Unset `DATABASE_URL` before tests or mock `init_db()` in test fixtures to prevent remote connections during local testing.

2. **Add missing response models (❌ → ✅)**
   - `GET /incidents/summary` — create `IncidentSummaryResponse`, add `response_model`
   - `DELETE /users/{user_id}` — add `response_model=DetailResponse` or `StatusResponse`

3. **Create list schemas (⚠️ → ✅)**
   - `GET /users` — create `UserListItemResponse` (no `uuid`), use for list

4. **Add root/health schemas (⚠️ → ✅)**
   - `GET /` — add `RootResponse(response_model=...)` or inline
   - `GET /health` — add `HealthResponse(response_model=...)` or inline

5. **Low-priority improvements**
   - `GET /suppliers` — evaluate if `SupplierListItemResponse` (no `notes`) is worth the churn
   - `GET /inventory/orders/{id}` — implement or remove from docstring

---

## Phase 4 — Final Validation

**Phase:** 4 — Final Validation Complete
**Date:** 2026-10-05
**Branch:** `feature/serialization-audit`

### Phase 4 Scope

Full-suite validation after Phase 3 implementation. Tests executed under a local test-only database environment that does not contact remote PostgreSQL/Supabase.

### Test Environment Strategy

The database engine is resolved lazily in `database.py:_resolve_engine_url()`:

1. If `DATABASE_URL` is set in environment, use it directly (no guard — production or otherwise).
2. If `DATABASE_URL` is empty and `APP_ENV=production` with no `ALLOW_SQLITE_FALLBACK`, raise.
3. Otherwise fall back to `sqlite://`.

The original baseline (133 passed / 70 errors) ran with `.env` `DATABASE_URL` pointing to an unreachable Supabase pooler. All 70 errors were `TestClient(app)→lifespan→init_db()` failures trying to connect to PostgreSQL.

**Phase 4 test execution:** `DATABASE_URL=sqlite:// APP_ENV=development` (ephemeral override, no production files modified). This:

- Bypasses the production guard (DATABASE_URL is set, so the guard is never reached)
- Uses SQLite in-memory for inventory tests
- Does NOT modify `.env`, `pyproject.toml`, or any configuration file
- Does NOT contact Supabase/PostgreSQL
- Is purely ephemeral — no artifacts written outside test scope

### Full-Suite Test Results

**Command:** `DATABASE_URL=sqlite:// APP_ENV=development uv run pytest`

| Test File                         | Tests | Status                                   | Notes                                 |
| --------------------------------- | ----- | ---------------------------------------- | ------------------------------------- |
| `test_database_config.py`         | 12    | 12/12 PASSED                             | Database URL resolution & guard tests |
| `test_incident_models.py`         | 13    | 13/13 PASSED                             | Pydantic model validation             |
| `test_incidents_api.py`           | 52    | 52/52 PASSED                             | Full incident API lifecycle           |
| `test_incidents_api_compat.py`    | 17    | 17/17 PASSED                             | `/api/incidents` prefix compatibility |
| `test_seed_incidents.py`          | 9     | 9/9 PASSED                               | Historical seed idempotency           |
| `test_suppliers_api.py`           | 27    | 27/27 PASSED                             | Supplier CRUD + edge cases            |
| `test_auth_users_profiles_api.py` | 43    | **43/43 PASSED** (was 43 ERROR)          | All now pass with local SQLite        |
| `test_inventory_api.py`           | 30    | **30/30 PASSED** (was 3 PASS + 27 ERROR) | All now pass with local SQLite        |
| `test_serialization_contracts.py` | 24    | 24/24 PASSED                             | New serialization contract tests      |

**Total: 227/227 PASSED, 0 FAILED, 0 ERRORS, 0 SKIPPED**

### Baseline Comparison

| Metric    | Baseline (Phase 1) | Phase 4 (Current) | Delta   | Root Cause                                                   |
| --------- | ------------------ | ----------------- | ------- | ------------------------------------------------------------ |
| PASSED    | 133                | 227               | +94     | 70 pre-existing errors resolved + 24 new serialization tests |
| FAILED    | 0                  | 0                 | —       | —                                                            |
| ERRORS    | 70                 | 0                 | -70     | All 70 errors caused by unreachable Supabase DATABASE_URL    |
| SKIPPED   | 0                  | 0                 | —       | —                                                            |
| **TOTAL** | **203**            | **227**           | **+24** | Only new tests are the serialization contracts               |

**Key finding:** The 70 baseline errors were entirely an environment configuration issue — not actual test failures. When `DATABASE_URL=sqlite://` is set, all 203 original tests pass plus 24 new serialization tests. **No regressions were introduced.**

### Serialization Contract Tests (Phase 3 — Re-verified)

**File:** `tests/test_serialization_contracts.py`
**Result:** 24/24 PASSED

| Endpoint                     | Tests | Verified                                                                                           |
| ---------------------------- | ----- | -------------------------------------------------------------------------------------------------- |
| `GET /`                      | 4     | Exact fields (`message`, `status`), types, no extras, HTTP 200                                     |
| `GET /health`                | 4     | Exact field (`status`), type, no extras, HTTP 200                                                  |
| `DELETE /users/{user_id}`    | 5     | `detail` field, type, no extras, HTTP 200, error for missing user                                  |
| `GET /api/incidents/summary` | 5     | 5 keys present, nested dict types, integer counts, seeded data, empty DB                           |
| `GET /users`                 | 6     | `uuid` absent, `password`/`hashed_password` absent, exact fields, types, boolean `is_active`, role |

### OpenAPI Verification

All 5 new response schemas confirmed present in auto-generated OpenAPI (`/openapi.json`):

| Schema                    | Properties                                                                                             | Route Reference                               |
| ------------------------- | ------------------------------------------------------------------------------------------------------ | --------------------------------------------- |
| `RootResponse`            | `message: string`, `status: string`                                                                    | `GET /` → `200` response                      |
| `HealthResponse`          | `status: string`                                                                                       | `GET /health` → `200` response                |
| `UserListItemResponse`    | `id: integer`, `email: string`, `is_active: boolean`, `role: string`, `created_at: string (date-time)` | `GET /users` → `200` array items              |
| `DetailResponse`          | `detail: string`                                                                                       | `DELETE /users/{user_id}` → `200` response    |
| `IncidentSummaryResponse` | `total: integer`, `by_status: object`, `by_category: object`, `by_origin: object`, `by_branch: object` | `GET /api/incidents/summary` → `200` response |

The `/incidents` compatibility alias (5 routes) is correctly excluded from OpenAPI (`include_in_schema=False`). No schema visibility changes were made.

### Endpoint Audit (Final)

**Method:** Programmatic FastAPI route registry traversal with `_IncludedRouter` recursion.

- **REGISTERED_ROUTE_ENTRIES:** 36 (5 incident endpoints × 2 prefixes + 2 app-level + 24 single-prefix)
- **UNIQUE_API_HANDLERS:** 31 (deduplicated by `{method}:{handler_module}.{handler_name}`)
- **Framework routes excluded:** `/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect`
- **SERIALIZED:** 31 (100%)
- **UNSERIALIZED:** 0
- **NOT_IMPLEMENTED:** 0 (`GET /inventory/orders/{id}` has no registered route handler)

### Security Audit

All 31 response model field sets were programmatically scanned for sensitive keywords:
`password`, `hashed_password`, `secret`, `token`, `reset_token`, `api_key`, `credential`, `session`, `auth_token`, `access_token`, `refresh_token`, `private`, `DATABASE_URL`, `SECRET_KEY`, `RESEND_API_KEY`.

**Findings:**

- **`access_token`** — found only in `TokenResponse` on `POST /auth/login` → **INTENTIONAL** (JWT authentication token, required by design)
- **`token_type`** — found only in `TokenResponse` on `POST /auth/login` → **INTENTIONAL** (OAuth2-style token type identifier)
- **All other keywords** — **NOT FOUND** in any endpoint response

**Verdict: NO sensitive data exposure.** No `hashed_password`, `reset_token`, `SECRET_KEY`, `DATABASE_URL`, or `RESEND_API_KEY` appears in any response schema. Input schemas (`UserCreate.password`, `LoginRequest.password`, etc.) are request bodies — users must send passwords to login/register; this is not a serialization issue.

### Consumer Compatibility

| Consumer Verdict                      | Evidence                                                                                                            |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| ✅ `GET /users` — `uuid` removed      | Frontend `authApi.ts` `UserResponse` type: `{ id, email, is_active, role, created_at }` — **NO `uuid`**             |
| ✅ Incident `description` preserved   | `IncidentsListPage.tsx:262` displays `{incident.description}` — field still returned by `IncidentResponse`          |
| ✅ Supplier `notes` preserved         | `SuppliersPage.tsx` creates/edits notes — field still returned by `SupplierResponse`                                |
| ✅ Supplier `contact_email` preserved | `SuppliersPage.tsx:526` displays `{supplier.contact_email}` — field still returned                                  |
| ✅ Inventory schemas unchanged        | `inventoryApi.ts` types `SKUResponse`, `StockEntryResponse`, `StockExitResponse`, `StockMovementResponse` unchanged |
| ✅ Frontend files not modified        | Zero changes to `uis/` directory                                                                                    |
| ✅ No production DB config modified   | `.env` unchanged, `database.py` unchanged, `pyproject.toml` unchanged                                               |

### Audit Document Validation

- **Canonical path:** `docs/serialization-audit.md` — exactly 1 copy
- **No rogue copies:** No `serialization-audit.md` at repository root
- **No stale references:** All document-internal references use correct `docs/` prefix
- **Phases present:** Phase 1 (Baseline), Phase 2 (Schema Design), Phase 3 (Implementation), Phase 4 (Final Validation)
- **Baseline preserved:** Phase 1 findings, baseline failures, and audit data are preserved

### Temporary Artifacts

- `_audit_endpoints.py` — **REMOVED** (was a temporary debugging script)
- `_debug_routes.py` — **REMOVED** (was a temporary debugging script)
- No other temporary scripts, databases, or browser artifacts remain untracked
- All new files are intentional: `docs/serialization-audit.md`, `tests/test_serialization_contracts.py`

### Git Safety

- **Branch:** `feature/serialization-audit`
- **Changes:** Unstaged working tree changes only
- **No commits, no pushes, no merges**
- **Whitespace check:** `git diff --check` — no whitespace errors
- **Scope verification:** No changes to `uis/`, `infra/`, `docker-compose.yml`, `.env*`

---

## Final Implementation Status (Post-Phase 4)

| Metric                     | Phase 1 (Baseline) | Phase 4 (Current) | Delta                                         |
| -------------------------- | ------------------ | ----------------- | --------------------------------------------- |
| TOTAL unique handlers      | 31                 | 31                | —                                             |
| SERIALIZED                 | 24                 | 31                | +7                                            |
| UNSERIALIZED               | 2                  | 0                 | -2 (both resolved)                            |
| PARTIALLY_SERIALIZED       | 5                  | 0                 | -5 (3 resolved, 2 reclassified to SERIALIZED) |
| NOT_IMPLEMENTED (planned)  | 1                  | 0                 | -1 (no route exists — not a gap)              |
| Security exposures         | 0 CRITICAL         | 0 CRITICAL        | —                                             |
| Over-fetching              | 1 (`uuid`)         | 0                 | -1 (resolved by `UserListItemResponse`)       |
| Input/output schema issues | 0                  | 0                 | —                                             |
| Full-suite tests PASSED    | 133                | 227               | +94                                           |
| Full-suite tests ERRORS    | 70                 | 0                 | -70 (environment issue, not code)             |

**Final Audit Verdict: 31/31 SERIALIZED ✅**
All 31 unique API handlers now have explicit `response_model` with Pydantic schemas. Zero security exposures. Zero over-fetching. Zero input/output schema issues. All 227 tests pass.

**Files modified during Phase 3:**

- `models.py` — 5 new schema classes (+34 lines)
- `main.py` — `response_model` on 2 routes (+3/-2)
- `routers/users.py` — `response_model` on 2 routes (+3/-1)
- `routers/incidents.py` — `response_model` on 1 route (+3/-1)
- `tests/test_serialization_contracts.py` — 24 new serialization contract tests

**No handler logic, database config, frontend code, or secrets were changed.**

**SERIALIZATION_AUDIT_STATUS:** COMPLETE ✅
**TOTAL_ENDPOINTS:** 31 unique (method, handler) combos
**TOTAL_ROUTE_ENTRIES:** 36 (including `/api/incidents` aliases)
**SERIALIZED_ENDPOINTS:** 31
**UNSERIALIZED_ENDPOINTS:** 0
**SENSITIVE_DATA_EXPOSURE:** NO (only `access_token`/`token_type` on `POST /auth/login` — intentional)
**OVERFETCHING_FOUND:** NONE (uuid resolved)
**INPUT_OUTPUT_SCHEMA_ISSUES:** NO
**BASELINE_TEST_STATUS:** 133 passed / 70 errors (originally) — 70 errors were environment-only; 227/227 pass with `DATABASE_URL=sqlite://`
**SERIALIZATION_CONTRACT_TESTS:** 24/24 PASSING
**FULL_SUITE_TESTS:** 227/227 PASSED (0 failed, 0 errors, 0 skipped)
**NEXT_RECOMMENDED_STEP:** Review changes, commit to `feature/serialization-audit`, create pull request.
