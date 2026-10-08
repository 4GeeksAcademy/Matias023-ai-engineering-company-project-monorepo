/**
 * Global frontend error telemetry for TrackFlow.
 *
 * Captures JavaScript errors and unhandled rejections, then emits
 * sanitised `frontend_error_captured` telemetry events.
 *
 * SAFETY GUARDS:
 *   - Telemetry errors are caught — they never propagate.
 *   - A recursion guard prevents re-entrant error capture while
 *     handling an error (e.g. telemetry.track() itself crashing).
 *   - Only the approved properties from event-schemas.json are sent:
 *     errorKind, page (sanitised), fatal. NO message, stack, or PII.
 *
 * @module
 */

import { telemetry } from './telemetry'
import { pathToPageId } from './pageMapping'

// ──────────────────────────────────────────────
// State
// ──────────────────────────────────────────────

/** Recursion guard — set while we are inside handleError. */
let handlingError = false

// ──────────────────────────────────────────────
// Public API
// ──────────────────────────────────────────────

/**
 * Safely emit a frontend_error_captured event.
 *
 * @param errorKind - One of the approved schema values.
 * @param page - Sanitised pageId or the string "unknown".
 * @param fatal - Whether the error prevented rendering.
 */
export function captureError(
  errorKind: 'runtime_error' | 'unhandled_rejection' | 'error_boundary',
  page: string,
  fatal: boolean,
): void {
  if (handlingError) return // prevent recursion

  handlingError = true
  try {
    telemetry.track('frontend_error_captured', {
      errorKind,
      page,
      fatal,
    })
  } catch {
    // Telemetry must never crash the application.
  } finally {
    handlingError = false
  }
}

/**
 * Resolve the current page from window.location.pathname.
 * Returns "unknown" when the path does not map to a known pageId.
 */
export function resolveCurrentPage(pathname?: string): string {
  const path = pathname ?? (typeof window !== 'undefined' ? window.location.pathname : '/')
  return pathToPageId(path) ?? 'unknown'
}

// ──────────────────────────────────────────────
// Global installers (called from main.tsx)
// ──────────────────────────────────────────────

/**
 * Install global error handlers that emit frontend_error_captured events.
 *
 * Call once at startup.
 *
 * Installs:
 *   1. window.onerror → runtime_error
 *   2. window 'unhandledrejection' event → unhandled_rejection
 *
 * Does NOT install an ErrorBoundary — React-router v7's route structure
 * makes a generic ErrorBoundary architecturally impractical without
 * wrapping every route individually, which would duplicate the error
 * capture. runtime_error + unhandled_rejection cover the same signals.
 */
export function installErrorCapture(): void {
  if (typeof window === 'undefined') return
  if (window.onerror !== null) return // already installed

  // ── window.onerror (synchronous JS errors) ──
  window.onerror = (
    _message: string | Event,
    _source: string | undefined,
    _line: number | undefined,
    _col: number | undefined,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    _error: Error | undefined,
  ) => {
    const page = resolveCurrentPage()
    const fatal = true // JS errors at window level are always fatal to rendering
    captureError('runtime_error', page, fatal)
    // Return false to let the default handler also run (standard behaviour).
    return false
  }

  // ── Unhandled rejections (async promise rejections) ──
  window.addEventListener('unhandledrejection', (_event: Event) => {
    const page = resolveCurrentPage()
    const fatal = false // async rejections may not prevent rendering
    captureError('unhandled_rejection', page, fatal)
  })
}