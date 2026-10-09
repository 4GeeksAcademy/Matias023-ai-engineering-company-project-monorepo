/**
 * TelemetryService — frontend event capture for TrackFlow.
 *
 * Features:
 *   • track(eventType, properties) — public API, never throws
 *   • In-memory queue (max 20), auto-flushes when full
 *   • Periodic flush every 10 seconds (singleton timer)
 *   • Batch POST to VITE_TELEMETRY_ENDPOINT (no Authorization header)
 *   • sendBeacon fallback on visibilitychange === "hidden"
 *   • Exponential backoff retries: initial + 3 retries (1s, 2s, 4s)
 *   • In-flight guard + snapshot strategy for safe concurrency
 *   • Automatic envelope: eventId, timestamp, sessionId, userId,
 *     schemaVersion "1.0", requestId
 *
 * @module
 */

import { getTelemetryEndpoint } from './telemetryConfig'

export type TelemetryEvent = {
  eventId: string
  timestamp: string
  sessionId: string | null
  userId: string | null
  event_type: string
  schemaVersion: string
  requestId: string | null
  properties: Record<string, unknown>
}

export type TelemetryBatch = {
  events: TelemetryEvent[]
}

// ──────────────────────────────────────────────
// Dependency injection helpers (overridable in tests)
// ──────────────────────────────────────────────

export interface TelemetryDependencies {
  generateUuid: () => string
  isoNow: () => string
  getSessionId: () => string
  getEndpoint: () => string | null
  fetch: typeof fetch
  setInterval: typeof setInterval
  setTimeout: typeof setTimeout
  clearInterval: typeof clearInterval
  documentAddListener: (handler: () => void) => void
  sendBeacon: ((url: string, blob: Blob) => void) | null
}

function realGenerateUuid(): string {
  return crypto.randomUUID()
}

function realIsoNow(): string {
  return new Date().toISOString()
}

const SESSION_STORAGE_KEY = 'telemetry_session_id'

function realGetSessionId(): string {
  let id: string | null = null
  if (typeof sessionStorage !== 'undefined') {
    id = sessionStorage.getItem(SESSION_STORAGE_KEY)
  }
  if (!id) {
    id = realGenerateUuid()
    if (typeof sessionStorage !== 'undefined') {
      try {
        sessionStorage.setItem(SESSION_STORAGE_KEY, id)
      } catch {
        // storage may be full or unavailable — proceed with in-memory id
      }
    }
  }
  return id
}

function realGetEndpoint(): string | null {
  // Delegate to the Vite-specific config module.
  // import.meta.env is handled by Vite at build time — no eval needed.
  return getTelemetryEndpoint()
}

function realDocumentAddListener(handler: () => void): void {
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        handler()
      }
    })
  }
}

function realSendBeacon(url: string, blob: Blob): void {
  if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
    navigator.sendBeacon(url, blob)
  }
}

/** Default dependencies — use live browser APIs. */
const DEFAULT_DEPS: TelemetryDependencies = {
  generateUuid: realGenerateUuid,
  isoNow: realIsoNow,
  getSessionId: realGetSessionId,
  getEndpoint: realGetEndpoint,
  fetch: /* @__PURE__ */ (url, init) => fetch(url, init),
  setInterval: /* @__PURE__ */ (fn, ms) => setInterval(fn, ms),
  setTimeout: /* @__PURE__ */ (fn, ms) => setTimeout(fn, ms),
  clearInterval: /* @__PURE__ */ (id) => clearInterval(id),
  documentAddListener: realDocumentAddListener,
  sendBeacon: realSendBeacon,
}

// ──────────────────────────────────────────────
// Service implementation
// ──────────────────────────────────────────────

const FLUSH_INTERVAL_MS = 10_000
const MAX_QUEUE_SIZE = 20
const MAX_RETRIES = 3 // initial attempt + 3 retries = 4 total

class TelemetryServiceImpl {
  private queue: TelemetryEvent[] = []
  private userId: string | null = null
  private requestId: string
  private sessionId: string
  private inFlight = false
  private timerHandle: ReturnType<typeof setInterval> | null = null
  private endpoint: string | null
  private started = false
  private deps: TelemetryDependencies

  constructor(deps: TelemetryDependencies = DEFAULT_DEPS) {
    this.deps = deps
    this.sessionId = deps.getSessionId()
    this.requestId = deps.generateUuid()
    this.endpoint = deps.getEndpoint()
  }

  // ── Public API ──

  /** Set the current user UUID. Pass null when the user logs out. */
  setUserId(id: string | null): void {
    this.userId = id
  }

  /**
   * Enqueue a telemetry event and flush immediately if the queue is full.
   *
   * @param eventType - The snake_case event type (e.g. "page_viewed").
   * @param properties - Strict allowed-list properties for this event type.
   *
   * This method never throws — errors are logged to console.warn.
   */
  track(eventType: string, properties: Record<string, unknown>): void {
    try {
      this.ensureStarted()

      const event: TelemetryEvent = {
        eventId: this.deps.generateUuid(),
        timestamp: this.deps.isoNow(),
        sessionId: this.sessionId,
        userId: this.userId,
        event_type: eventType,
        schemaVersion: '1.0',
        requestId: this.requestId,
        properties,
      }

      this.queue.push(event)

      if (this.queue.length >= MAX_QUEUE_SIZE) {
        this.flush()
      }
    } catch (err) {
      console.warn('[TelemetryService] track() failed:', err)
    }
  }

  /**
   * Force-flush the in-memory queue.
   * Safe to call externally; respects in-flight guard.
   */
  async flush(): Promise<void> {
    if (this.inFlight) return
    if (this.queue.length === 0) return
    if (!this.endpoint) {
      this.queue = []
      return
    }

    this.inFlight = true

    // Snapshot & clear the queue atomically
    const batch: TelemetryBatch = { events: this.queue.splice(0) }

    try {
      await this.deliverWithRetry(batch)
    } catch {
      // All retries exhausted — discard the batch silently.
      // Logging is handled inside deliverWithRetry.
    } finally {
      this.inFlight = false
    }
  }

  // ── Internal ──

  private ensureStarted(): void {
    if (this.started) return
    this.started = true

    // Periodic flush
    this.timerHandle = this.deps.setInterval(() => {
      this.flush()
    }, FLUSH_INTERVAL_MS)

    // sendBeacon on visibility hidden (browser tab close / navigate away)
    this.deps.documentAddListener(() => this.sendBeaconFlush())
  }

  private async deliverWithRetry(batch: TelemetryBatch): Promise<void> {
    const endpoint = this.endpoint
    if (!endpoint) return

    let lastError: unknown

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      if (attempt > 0) {
        // Exponential backoff: 1s, 2s, 4s
        const backoffMs = 1_000 * Math.pow(2, attempt - 1)
        await new Promise<void>((resolve) => this.deps.setTimeout(resolve, backoffMs))
      }

      try {
        const response = await this.deps.fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(batch),
        })

        if (!response.ok) {
          lastError = new Error(`HTTP ${response.status}`)
          continue
        }

        // Success — no more retries needed
        return
      } catch (err) {
        lastError = err
        // Network error, will retry
      }
    }

    // All attempts exhausted
    console.warn(
      '[TelemetryService] batch discarded after',
      MAX_RETRIES + 1,
      'attempts:',
      lastError,
    )
  }

  /**
   * Best-effort synchronous flush using `navigator.sendBeacon`.
   * Used when the browser tab is closing — fetch() may be interrupted
   * before the request completes.
   */
  private sendBeaconFlush(): void {
    if (this.queue.length === 0) return
    if (!this.endpoint) {
      this.queue = []
      return
    }
    if (!this.deps.sendBeacon) return

    // Avoid re-entering while a periodic flush is in-flight
    if (!this.inFlight) {
      const batch: TelemetryBatch = { events: this.queue.splice(0) }
      const blob = new Blob([JSON.stringify(batch)], { type: 'application/json' })
      this.deps.sendBeacon(this.endpoint, blob)
    }
  }

  // ── Testing hooks ──

  /** @internal Expose queue length for tests. */
  _queueLength(): number {
    return this.queue.length
  }

  /** @internal Reset to initial state (tests only). */
  _reset(): void {
    this.queue = []
    this.userId = null
    this.requestId = this.deps.generateUuid()
    this.sessionId = this.deps.getSessionId()
    this.inFlight = false
    if (this.timerHandle !== null) {
      this.deps.clearInterval(this.timerHandle)
      this.timerHandle = null
    }
    this.started = false
  }
}

// ──────────────────────────────────────────────
// Singleton export
// ──────────────────────────────────────────────

/**
 * Global TelemetryService instance.
 *
 * Import this singleton throughout the application:
 * ```ts
 * import { telemetry } from '../services/telemetry'
 * telemetry.setUserId(someUuid)
 * telemetry.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
 * ```
 */
export const telemetry = new TelemetryServiceImpl()

// Export the class for testing / alternate instances
export { TelemetryServiceImpl }