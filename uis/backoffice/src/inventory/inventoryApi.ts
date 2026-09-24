// ──────────────────────────────────────────────
// Inventory API — dedicated integration module
// ──────────────────────────────────────────────
//
// Reuses authFetch from ../api so all requests inherit:
//   Authorization: Bearer <token>
//   auth:expired dispatch on 401
//
// No component calls fetch directly.

import { authFetch } from '../api'

// ──────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────

export type Warehouse = 'LA' | 'ZGZ'
export type Category = 'fashion' | 'electronics' | 'cosmetics'
export type ExitType = 'dispatch' | 'loss'
export type MovementKind = 'entry' | 'exit'

export type SKUResponse = {
  id: number
  name: string
  sku: string
  client_name: string
  category: Category
  warehouse: Warehouse
  current_stock: number
  created_at: string
}

export type StockEntryCreate = {
  sku_id: number
  quantity: number
  reference: string
  warehouse: Warehouse
}

export type StockEntryResponse = {
  id: number
  sku_id: number
  quantity: number
  reference: string
  warehouse: Warehouse
  created_at: string
  user_uuid: string
}

export type StockExitCreate = {
  sku_id: number
  quantity: number
  exit_type: ExitType
  tracking_number: string | null
  warehouse: Warehouse
}

export type StockExitResponse = {
  id: number
  sku_id: number
  quantity: number
  exit_type: ExitType
  tracking_number: string | null
  warehouse: Warehouse
  created_at: string
  user_uuid: string
}

export type StockMovementResponse = {
  id: number
  kind: MovementKind
  sku_id: number
  sku: string
  sku_name: string
  warehouse: Warehouse
  quantity: number
  reference: string | null
  exit_type: ExitType | null
  tracking_number: string | null
  user_uuid: string
  created_at: string
}

// ──────────────────────────────────────────────
// Error parsing
// ──────────────────────────────────────────────

/**
 * Parse a FastAPI error response into a human-readable string.
 *
 * Handles:
 *   { "detail": "message" }                  — standard 4xx
 *   { "detail": [{ "loc": [...], "msg": "..." }] }  — 422 validation
 *   unparseable bodies                        — generic fallback
 */
export async function parseInventoryError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()

    if (body && typeof body === 'object') {
      const obj = body as Record<string, unknown>

      // Standard detail string
      if (typeof obj.detail === 'string' && obj.detail.length > 0) {
        return obj.detail
      }

      // 422 validation errors
      if (Array.isArray(obj.detail)) {
        const messages: string[] = []
        for (const err of obj.detail) {
          if (err && typeof err === 'object') {
            const e = err as Record<string, unknown>
            if (typeof e.msg === 'string') {
              const loc = Array.isArray(e.loc)
                ? e.loc.filter((p: unknown) => p !== 'body' && typeof p === 'string').join('.')
                : ''
              messages.push(loc ? `${loc}: ${e.msg}` : e.msg)
            }
          }
        }
        if (messages.length > 0) {
          return messages.join('; ')
        }
      }
    }

    return 'Something went wrong. Please try again.'
  } catch {
    return 'Something went wrong. Please try again.'
  }
}

// ──────────────────────────────────────────────
// API functions
// ──────────────────────────────────────────────

export async function getInventoryProducts(): Promise<SKUResponse[]> {
  const response = await authFetch('/api/inventory/products', { requireAuth: true })

  if (!response.ok) {
    throw new Error(await parseInventoryError(response))
  }

  return response.json()
}

export async function getInventoryProduct(id: number): Promise<SKUResponse> {
  const response = await authFetch(`/api/inventory/products/${id}`, { requireAuth: true })

  if (!response.ok) {
    throw new Error(await parseInventoryError(response))
  }

  return response.json()
}

export async function createInboundOrder(
  payload: StockEntryCreate,
): Promise<StockEntryResponse> {
  const response = await authFetch('/api/inventory/orders/inbound', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    requireAuth: true,
  })

  if (!response.ok) {
    throw new Error(await parseInventoryError(response))
  }

  return response.json()
}

export async function createOutboundOrder(
  payload: StockExitCreate,
): Promise<StockExitResponse> {
  const response = await authFetch('/api/inventory/orders/outbound', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    requireAuth: true,
  })

  if (!response.ok) {
    throw new Error(await parseInventoryError(response))
  }

  return response.json()
}

export async function getInventoryOrders(): Promise<StockMovementResponse[]> {
  const response = await authFetch('/api/inventory/orders', { requireAuth: true })

  if (!response.ok) {
    throw new Error(await parseInventoryError(response))
  }

  return response.json()
}