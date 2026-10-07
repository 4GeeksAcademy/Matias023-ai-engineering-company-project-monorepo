/**
 * Frontend-observed API telemetry for TrackFlow.
 *
 * Provides helpers to emit:
 *   • api_validation_error  — from 400/422 responses
 *   • api_server_error      — from 500 responses
 *   • inventory_query_duration — request→response timing for inventory
 *
 * All events are emitted via the centralised `track()` path.
 *
 * RECURSION GUARD:
 *   Requests whose path contains "telemetry" are NEVER instrumented —
 *   telemetry delivery must never create telemetry about telemetry.
 *
 * @module
 */

import { telemetry } from './telemetry'

// ──────────────────────────────────────────────
// Recursion guard
// ──────────────────────────────────────────────

/**
 * Return true when the path is the telemetry ingestion endpoint — caller
 * should NOT emit any api_validation_error / api_server_error event.
 *
 * Recognises both the Vite-proxied form (`/api/telemetry/...`) and the
 * backend-real form (`/telemetry/...`).
 */
export function isTelemetryPath(path: string): boolean {
  return path.includes('/telemetry/')
}

// ──────────────────────────────────────────────
// HTTP method extraction
// ──────────────────────────────────────────────

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

/** Normalise a request method to the schema enum. */
function normalizeMethod(method: string): HttpMethod {
  const m = method.toUpperCase()
  // map non-standard methods to their conceptual equivalent
  if (m === 'HEAD' || m === 'OPTIONS') return 'GET'
  return m as HttpMethod
}

// ──────────────────────────────────────────────
// api_validation_error
// ──────────────────────────────────────────────

/**
 * Emit an api_validation_error event.
 *
 * Safe to call — guards against telemetry-path recursion internally.
 */
export function trackValidationError(
  path: string,
  method: string,
  statusCode: number,
  field?: string,
): void {
  if (isTelemetryPath(path)) return

  telemetry.track('api_validation_error', {
    path,
    http_method: normalizeMethod(method),
    error_code: `http_${statusCode}`,
    status_code: statusCode,
    ...(field ? { field } : {}),
  })
}

// ──────────────────────────────────────────────
// api_server_error
// ──────────────────────────────────────────────

/**
 * Emit an api_server_error event.
 *
 * Safe to call — guards against telemetry-path recursion internally.
 */
export function trackServerError(
  path: string,
  method: string,
  statusCode: number,
): void {
  if (isTelemetryPath(path)) return

  telemetry.track('api_server_error', {
    path,
    http_method: normalizeMethod(method),
    error_code: `http_${statusCode}`,
    status_code: statusCode,
  })
}

// ──────────────────────────────────────────────
// inventory_query_duration
// ──────────────────────────────────────────────

/**
 * Measure and emit an inventory_query_duration event.
 *
 * Usage:
 * ```ts
 * import { trackInventoryDuration } from '../services/apiTelemetry'
 *
 * const stop = trackInventoryDuration('/api/inventory/products', 'GET')
 * // … do inventory request …
 * stopResult(stop)  // emits the event
 * ```
 *
 * SAFETY: telemetry-path requests are skipped (no-op start).
 */

export type InventoryDurationStop = {
  /** Call to emit the duration event. */
  stop: () => void
  /** Abort without emitting. */
  abort: () => void
}

/** Start timing an inventory request. */
export function trackInventoryDuration(
  endpoint: string,
  _method: string,
  warehouse?: string,
  skuCount?: number,
): InventoryDurationStop {
  if (isTelemetryPath(endpoint)) {
    return { stop: () => {}, abort: () => {} }
  }

  const start = Date.now()
  let aborted = false
  let stopped = false

  return {
    stop: () => {
      if (aborted || stopped) return
      stopped = true
      const elapsedMs = Date.now() - start
      const durationMs = Math.round(elapsedMs)

      const properties: Record<string, unknown> = {
        endpoint,
        duration_ms: durationMs,
        measurementSource: 'frontend',
      }
      if (warehouse !== undefined) properties.warehouse = warehouse
      if (skuCount !== undefined) properties.sku_count = skuCount

      telemetry.track('inventory_query_duration', properties)
    },
    abort: () => {
      aborted = true
    },
  }
}