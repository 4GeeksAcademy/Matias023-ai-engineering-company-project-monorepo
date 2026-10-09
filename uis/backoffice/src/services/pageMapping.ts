/**
 * Shared mapping between URL paths and the approved pageId enum.
 *
 * This is the single source of truth for path → pageId resolution,
 * used by both page_viewed tracking and frontend_error_captured to
 * determine the current logical page without accessing raw URLs.
 *
 * The pageId values are constrained by the schema enum:
 *   docs/telemetry/event-schemas.json → $defs/pageId
 */

export const PAGE_MAP: Record<string, string> = {
  '/login': 'login',
  '/register': 'register',
  '/forgot-password': 'forgot_password',
  '/reset-password': 'reset_password',
  '/suppliers': 'suppliers',
  '/backoffice/inventory/products': 'inventory_products',
  '/backoffice/inventory/orders/inbound': 'inbound_order',
  '/backoffice/inventory/orders/outbound': 'outbound_order',
  '/backoffice/inventory/orders': 'orders_list',
  '/incidents': 'incidents_list',
  '/incidents/new': 'incident_form',
  '/incidents/summary': 'incidents_summary',
  '/account/profile': 'profile',
  '/account/change-password': 'change_password',
  '/profile': 'profile',
}

/**
 * Map a URL path to the approved pageId enum value.
 *
 * @param path - URL pathname (e.g. "/incidents/new").
 * @returns The pageId value, or null if the path does not match a known page.
 */
export function pathToPageId(path: string): string | null {
  // Strip trailing slash (except for root "/")
  const normalized = path.endsWith('/') && path.length > 1
    ? path.slice(0, -1)
    : path

  return PAGE_MAP[normalized] ?? null
}