/**
 * Page-view telemetry for TrackFlow backoffice.
 *
 * Tracks approved `page_viewed` events with correct navigationType and
 * previousPage semantics.  Uses a single centralised state so all callers
 * share the same "current page" view — no scattered `useEffect` across
 * individual page components.
 *
 * SAFETY:
 *   • `trackPageView` never throws (telemetry.track is already guarded).
 *   • Unmapped routes are silently ignored — no invalid enum values.
 *   • Duplicate page IDs (same page, back-to-back) are suppressed in
 *     `client_navigation` mode.
 *
 * @module
 */

import { telemetry } from './telemetry'
import { pathToPageId } from './pageMapping'

// ──────────────────────────────────────────────
// State (shared across the entire backoffice)
// ──────────────────────────────────────────────

/** The pageId of the last tracked page, or null initially. */
let currentPageId: string | null = null

/** True until the first call to trackPageView (initial_load). */
let isFirstPage = true

// ──────────────────────────────────────────────
// Public API
// ──────────────────────────────────────────────

/**
 * Track a page_viewed event.
 *
 * @param path - The URL pathname to resolve (e.g. "/incidents/new").
 *
 * The navigationType is automatically determined:
 *   - First call → `initial_load` (previousPage = null)
 *   - Subsequent calls → `client_navigation` (previousPage = previous pageId)
 *
 * If the path does not map to a known pageId the call is a no-op.
 * If the path maps to the **same** pageId as the current one and this is
 * a client_navigation, the event is suppressed (no duplicate).
 */
export function trackPageView(path: string): void {
  const pageId = pathToPageId(path)
  if (pageId === null) return // unmapped route — skip

  // Determine navigation type
  const navigationType: 'initial_load' | 'client_navigation' =
    isFirstPage ? 'initial_load' : 'client_navigation'

  // Suppress duplicate events for the same page in client_navigation
  if (navigationType === 'client_navigation' && pageId === currentPageId) return

  const previousPage: string | null = isFirstPage ? null : currentPageId
  currentPageId = pageId
  isFirstPage = false

  telemetry.track('page_viewed', {
    page: pageId,
    navigationType,
    previousPage,
  })
}

/**
 * Convenience: track the page determined by `window.location.pathname`.
 *
 * Safe to call from main.tsx after mount — resolveCurrentPage will use
 * the browser's current pathname.
 */
export function trackInitialPage(): void {
  if (typeof window === 'undefined') return
  trackPageView(window.location.pathname)
}

// ──────────────────────────────────────────────
// Testing hooks
// ──────────────────────────────────────────────

/** @internal Reset the tracker state (for tests). */
export function _resetPageTracker(): void {
  currentPageId = null
  isFirstPage = true
}