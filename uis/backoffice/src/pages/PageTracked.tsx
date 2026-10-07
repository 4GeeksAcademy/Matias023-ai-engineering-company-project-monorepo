/**
 * Page-tracking wrapper for react-router-dom v7 Route elements.
 *
 * Usage in App.tsx:
 * ```tsx
 * <Route path="/login" element={<PageTracked><LoginPage /></PageTracked>} />
 * ```
 *
 * The wrapper fires a `page_viewed` telemetry event each time the route is
 * actually rendered (i.e. the route matches), using the path attribute to
 * determine the logical page ID.  It does NOT emit for unmapped paths.
 *
 * @module
 */

import { trackPageView } from '../services/pageTracker'

export default function PageTracked({ children }: { children: React.ReactNode }): React.ReactNode {
  // Resolve the page from the current window pathname at render time.
  // This fires every time this Route's element is rendered (route matches).
  if (typeof window !== 'undefined') {
    trackPageView(window.location.pathname)
  }
  return children
}