/**
 * Unit tests for `src/inventory/inventoryApi.ts`.
 *
 * We test pure functions (parseInventoryError) directly and test API
 * functions by mocking the authFetch import so no real HTTP calls or
 * localStorage setup is needed.
 */

/// <reference types="jest" />
/// <reference lib="dom" />

import {
  parseInventoryError,
  getInventoryProducts,
  getInventoryProduct,
  createInboundOrder,
  createOutboundOrder,
  getInventoryOrders,
  type StockEntryCreate,
  type StockExitCreate,
} from './inventoryApi'

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function mockResponse(ok: boolean, body: unknown): { ok: boolean; json: () => Promise<unknown> } {
  return { ok, json: async () => body }
}

let authFetchMock: jest.Mock

jest.mock('../api', () => ({
  authFetch: jest.fn(),
}))

beforeEach(() => {
  authFetchMock = jest.requireMock('../api').authFetch
})

afterEach(() => {
  jest.restoreAllMocks()
})

// ══════════════════════════════════════════════
// parseInventoryError()
// ══════════════════════════════════════════════

describe('parseInventoryError()', () => {
  test('returns detail string when body has a detail string', async () => {
    const response = mockResponse(false, { detail: 'Product not found' }) as Response
    const result = await parseInventoryError(response)
    expect(result).toBe('Product not found')
  })

  test('returns joined validation messages on 422 detail array', async () => {
    const body = {
      detail: [
        { loc: ['body', 'quantity'], msg: 'ensure this value is greater than 0' },
        { loc: ['body', 'reference'], msg: 'field required' },
      ],
    }
    const response = mockResponse(false, body) as Response
    const result = await parseInventoryError(response)
    expect(result).toBe('quantity: ensure this value is greater than 0; reference: field required')
  })

  test('filters out "body" segments from loc paths', async () => {
    const body = {
      detail: [{ loc: ['body', 'sku_id'], msg: 'field required' }],
    }
    const response = mockResponse(false, body) as Response
    const result = await parseInventoryError(response)
    expect(result).toBe('sku_id: field required')
  })

  test('returns fallback for non-object body', async () => {
    const response = mockResponse(false, 'broken') as Response
    const result = await parseInventoryError(response)
    expect(result).toBe('Something went wrong. Please try again.')
  })

  test('returns fallback when JSON parsing fails', async () => {
    const response = {
      ok: false,
      json: async () => {
        throw new Error('Invalid JSON')
      },
    } as unknown as Response
    const result = await parseInventoryError(response)
    expect(result).toBe('Something went wrong. Please try again.')
  })

  test('returns fallback when detail is an empty array', async () => {
    const response = mockResponse(false, { detail: [] }) as Response
    const result = await parseInventoryError(response)
    expect(result).toBe('Something went wrong. Please try again.')
  })

  test('returns fallback when detail is a non-string, non-array type', async () => {
    const response = mockResponse(false, { detail: 42 }) as Response
    const result = await parseInventoryError(response)
    expect(result).toBe('Something went wrong. Please try again.')
  })
})

// ══════════════════════════════════════════════
// getInventoryProducts()
// ══════════════════════════════════════════════

describe('getInventoryProducts()', () => {
  test('returns product list on success', async () => {
    const products = [
      { id: 1, name: 'T-Shirt', sku: 'TSH-001', client_name: 'BrandA', category: 'fashion', warehouse: 'LA', current_stock: 25, created_at: '2024-01-01T00:00:00Z' },
    ]
    authFetchMock.mockResolvedValue(mockResponse(true, products))

    const result = await getInventoryProducts()

    expect(result).toEqual(products)
    expect(authFetchMock).toHaveBeenCalledWith('/api/inventory/products', { requireAuth: true })
  })

  test('throws on API error', async () => {
    authFetchMock.mockResolvedValue(mockResponse(false, { detail: 'Forbidden' }))

    await expect(getInventoryProducts()).rejects.toThrow('Forbidden')
  })
})

// ══════════════════════════════════════════════
// getInventoryProduct()
// ══════════════════════════════════════════════

describe('getInventoryProduct()', () => {
  test('returns single product on success', async () => {
    const product = { id: 99, name: 'Shoes', sku: 'SHO-099', client_name: 'BrandB', category: 'fashion', warehouse: 'ZGZ', current_stock: 5, created_at: '2024-02-01T00:00:00Z' }
    authFetchMock.mockResolvedValue(mockResponse(true, product))

    const result = await getInventoryProduct(99)

    expect(result).toEqual(product)
    expect(authFetchMock).toHaveBeenCalledWith('/api/inventory/products/99', { requireAuth: true })
  })

  test('throws on API error', async () => {
    authFetchMock.mockResolvedValue(mockResponse(false, { detail: 'Not found' }))

    await expect(getInventoryProduct(999)).rejects.toThrow('Not found')
  })
})

// ══════════════════════════════════════════════
// createInboundOrder()
// ══════════════════════════════════════════════

describe('createInboundOrder()', () => {
  const payload: StockEntryCreate = {
    sku_id: 1,
    quantity: 50,
    reference: 'PO-2024-0098',
    warehouse: 'LA',
  }

  test('posts to inbound endpoint and returns entry response', async () => {
    const response = { id: 10, sku_id: 1, quantity: 50, reference: 'PO-2024-0098', warehouse: 'LA', created_at: '2024-03-01T00:00:00Z', user_uuid: 'abc-123' }
    authFetchMock.mockResolvedValue(mockResponse(true, response))

    const result = await createInboundOrder(payload)

    expect(result).toEqual(response)
    expect(authFetchMock).toHaveBeenCalledWith(
      '/api/inventory/orders/inbound',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        requireAuth: true,
      }),
    )
  })

  test('throws on API error', async () => {
    authFetchMock.mockResolvedValue(mockResponse(false, { detail: 'SKU not found' }))

    await expect(createInboundOrder(payload)).rejects.toThrow('SKU not found')
  })
})

// ══════════════════════════════════════════════
// createOutboundOrder()
// ══════════════════════════════════════════════

describe('createOutboundOrder()', () => {
  const payload: StockExitCreate = {
    sku_id: 2,
    quantity: 3,
    exit_type: 'dispatch',
    tracking_number: '1Z999AA10123456784',
    warehouse: 'ZGZ',
  }

  test('posts to outbound endpoint and returns exit response', async () => {
    const response = { id: 20, sku_id: 2, quantity: 3, exit_type: 'dispatch', tracking_number: '1Z999AA10123456784', warehouse: 'ZGZ', created_at: '2024-04-01T00:00:00Z', user_uuid: 'def-456' }
    authFetchMock.mockResolvedValue(mockResponse(true, response))

    const result = await createOutboundOrder(payload)

    expect(result).toEqual(response)
    expect(authFetchMock).toHaveBeenCalledWith(
      '/api/inventory/orders/outbound',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        requireAuth: true,
      }),
    )
  })

  test('throws on API error', async () => {
    authFetchMock.mockResolvedValue(mockResponse(false, { detail: 'Insufficient stock' }))

    await expect(createOutboundOrder(payload)).rejects.toThrow('Insufficient stock')
  })
})

// ══════════════════════════════════════════════
// getInventoryOrders()
// ══════════════════════════════════════════════

describe('getInventoryOrders()', () => {
  test('returns movement list on success', async () => {
    const movements = [
      { id: 1, kind: 'entry', sku_id: 1, sku: 'TSH-001', sku_name: 'T-Shirt', warehouse: 'LA', quantity: 50, reference: 'PO-001', exit_type: null, tracking_number: null, user_uuid: 'abc', created_at: '2024-01-01T00:00:00Z' },
    ]
    authFetchMock.mockResolvedValue(mockResponse(true, movements))

    const result = await getInventoryOrders()

    expect(result).toEqual(movements)
    expect(authFetchMock).toHaveBeenCalledWith('/api/inventory/orders', { requireAuth: true })
  })

  test('throws on API error', async () => {
    authFetchMock.mockResolvedValue(mockResponse(false, { detail: 'Server error' }))

    await expect(getInventoryOrders()).rejects.toThrow('Server error')
  })
})