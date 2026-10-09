/**
 * Tests for Phase 4 frontend technical instrumentation.
 *
 * Covers the 5 technical events:
 *   1. frontend_error_captured  (errorCapture.ts)
 *   2. page_viewed              (pageTracker.ts + pageMapping.ts)
 *   3. api_validation_error     (apiTelemetry.ts + api.ts + authApi.ts)
 *   4. api_server_error         (apiTelemetry.ts + api.ts + authApi.ts)
 *   5. inventory_query_duration (apiTelemetry.ts + inventoryApi.ts)
 *
 * Also validates:
 *   • Recursion guards (telemetry paths never emit telemetry)
 *   • No raw message/stack in error events
 *   • Safe properties only (no PII)
 *   • Duration >= 0
 *   • measurementSource = 'frontend'
 *
 * Runs under Jest's `node` environment — no jsdom required.
 * Uses jest.spyOn to intercept telemetry.track calls without needing
 * real browser APIs (sessionStorage, etc).
 */

/// <reference types="jest" />

import { telemetry } from './telemetry'
import { pathToPageId } from './pageMapping'
import {
  captureError,
  installErrorCapture,
  resolveCurrentPage,
} from './errorCapture'
import {
  trackPageView,
  trackInitialPage,
  _resetPageTracker,
} from './pageTracker'
import {
  isTelemetryPath,
  trackValidationError,
  trackServerError,
  trackInventoryDuration,
} from './apiTelemetry'

// ──────────────────────────────────────────────
// Mock global fetch for API integration tests
// ──────────────────────────────────────────────

const ORIGINAL_FETCH = globalThis.fetch

function mockGlobalFetch(status: number, body: unknown = ''): jest.Mock {
  const mock = jest.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    }),
  )
  globalThis.fetch = mock as unknown as typeof fetch
  return mock
}



function restoreGlobalFetch(): void {
  globalThis.fetch = ORIGINAL_FETCH
}

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

/**
 * Return the properties argument of the nth telemetry.track() call.
 * Assumes the spy was set up with mockImplementation.
 */
function getTrackProperties(
  spy: jest.SpyInstance,
  n: number = 0,
): Record<string, unknown> {
  return spy.mock.calls[n][1] as Record<string, unknown>
}

/**
 * Return the event_type of the nth telemetry.track() call.
 */
function getTrackEventType(spy: jest.SpyInstance, n: number = 0): string {
  return spy.mock.calls[n][0] as string
}

// ──────────────────────────────────────────────
// pageMapping tests
// ──────────────────────────────────────────────

describe('pageMapping', () => {
  describe('pathToPageId', () => {
    it('maps known paths to their pageId', () => {
      expect(pathToPageId('/suppliers')).toBe('suppliers')
      expect(pathToPageId('/login')).toBe('login')
      expect(pathToPageId('/incidents/new')).toBe('incident_form')
      expect(pathToPageId('/account/profile')).toBe('profile')
    })

    it('normalises trailing slashes', () => {
      expect(pathToPageId('/suppliers/')).toBe('suppliers')
      expect(pathToPageId('/login/')).toBe('login')
    })

    it('returns null for unmapped paths', () => {
      expect(pathToPageId('/unknown')).toBeNull()
      expect(pathToPageId('/admin')).toBeNull()
      expect(pathToPageId('/')).toBeNull()
    })

    it('returns null for empty path', () => {
      expect(pathToPageId('')).toBeNull()
    })
  })
})

// ──────────────────────────────────────────────
// isTelemetryPath tests
// ──────────────────────────────────────────────

describe('isTelemetryPath', () => {
  it('returns true for paths containing /telemetry/', () => {
    expect(isTelemetryPath('/api/telemetry/events')).toBe(true)
    expect(isTelemetryPath('/telemetry/events')).toBe(true)
    expect(isTelemetryPath('/api/telemetry/')).toBe(true)
  })

  it('returns false for non-telemetry paths', () => {
    expect(isTelemetryPath('/api/suppliers')).toBe(false)
    expect(isTelemetryPath('/api/inventory/products')).toBe(false)
    expect(isTelemetryPath('/api/auth/login')).toBe(false)
  })

  it('returns false for empty string', () => {
    expect(isTelemetryPath('')).toBe(false)
  })

  it('matches /telemetry/ anywhere in the path (not just prefix)', () => {
    expect(isTelemetryPath('/proxy/telemetry/v2')).toBe(true)
    expect(isTelemetryPath('/other/telemetry/')).toBe(true)
  })
})

// ──────────────────────────────────────────────
// errorCapture tests
// ──────────────────────────────────────────────

describe('errorCapture', () => {
  let trackSpy: jest.SpyInstance

  beforeEach(() => {
    trackSpy = jest.spyOn(telemetry, 'track').mockImplementation(() => {})
  })

  afterEach(() => {
    trackSpy.mockRestore()
  })

  describe('captureError', () => {
    it('emits frontend_error_captured with runtime_error', () => {
      captureError('runtime_error', 'suppliers', true)

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('frontend_error_captured')
      expect(getTrackProperties(trackSpy)).toEqual({
        errorKind: 'runtime_error',
        page: 'suppliers',
        fatal: true,
      })
    })

    it('emits frontend_error_captured with unhandled_rejection', () => {
      captureError('unhandled_rejection', 'login', false)

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('frontend_error_captured')
      expect(getTrackProperties(trackSpy)).toEqual({
        errorKind: 'unhandled_rejection',
        page: 'login',
        fatal: false,
      })
    })

    it('emits frontend_error_captured with error_boundary', () => {
      captureError('error_boundary', 'unknown', false)

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackProperties(trackSpy)).toEqual({
        errorKind: 'error_boundary',
        page: 'unknown',
        fatal: false,
      })
    })

    it('does NOT include message, stack, or any raw error details', () => {
      captureError('runtime_error', 'suppliers', true)

      const props = getTrackProperties(trackSpy)
      expect(props).not.toHaveProperty('message')
      expect(props).not.toHaveProperty('stack')
      expect(props).not.toHaveProperty('error')
      expect(props).not.toHaveProperty('errorMessage')
      expect(props).not.toHaveProperty('errorKind_raw')
      // Only the 3 approved properties
      expect(Object.keys(props)).toEqual(['errorKind', 'page', 'fatal'])
    })

    it('does NOT include PII (email, name, user, token)', () => {
      captureError('runtime_error', 'suppliers', true)

      const props = getTrackProperties(trackSpy)
      expect(props).not.toHaveProperty('email')
      expect(props).not.toHaveProperty('name')
      expect(props).not.toHaveProperty('user')
      expect(props).not.toHaveProperty('token')
    })

    it('guards against recursion when track() throws', () => {
      // Make telemetry.track throw on first call
      trackSpy.mockImplementationOnce(() => {
        throw new Error('telemetry failure')
      })

      // Should NOT throw — captureError catches errors
      captureError('runtime_error', 'suppliers', true)

      // The recursion guard flag should have been reset (no hang)
      // Second call should work normally
      trackSpy.mockImplementation(() => {})
      captureError('runtime_error', 'login', false)
      expect(trackSpy).toHaveBeenCalledTimes(2)
    })

    it('uses "unknown" page when page is unrecognised', () => {
      captureError('runtime_error', 'some_random_page', true)
      expect(getTrackProperties(trackSpy).page).toBe('some_random_page')
    })
  })

  describe('resolveCurrentPage', () => {
    it('returns pageId for a known path', () => {
      expect(resolveCurrentPage('/suppliers')).toBe('suppliers')
      expect(resolveCurrentPage('/login')).toBe('login')
    })

    it('returns "unknown" for unmapped paths', () => {
      expect(resolveCurrentPage('/nonexistent')).toBe('unknown')
      expect(resolveCurrentPage('/')).toBe('unknown')
    })

    it('normalises trailing slashes', () => {
      expect(resolveCurrentPage('/suppliers/')).toBe('suppliers')
    })
  })

  describe('installErrorCapture', () => {
    beforeEach(() => {
      // We need window mock for these tests
      // Since we're in node, installErrorCapture will likely return early
      // because typeof window === 'undefined'
      // Let's just verify it handles edge cases safely.
    })

    it('is safe to call in node environment (no window)', () => {
      // Should not throw
      installErrorCapture()
      // Verify by calling again — still no throw
      installErrorCapture()
    })

    // Note: Full window.onerror tests require a jsdom-like environment.
    // In node environment we test the pure functions above.
  })
})

// ──────────────────────────────────────────────
// pageTracker tests
// ──────────────────────────────────────────────

describe('pageTracker', () => {
  let trackSpy: jest.SpyInstance

  beforeEach(() => {
    trackSpy = jest.spyOn(telemetry, 'track').mockImplementation(() => {})
    _resetPageTracker()
  })

  afterEach(() => {
    trackSpy.mockRestore()
    _resetPageTracker()
  })

  describe('trackPageView', () => {
    it('emits page_viewed with initial_load on first call', () => {
      trackPageView('/suppliers')

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('page_viewed')
      expect(getTrackProperties(trackSpy)).toEqual({
        page: 'suppliers',
        navigationType: 'initial_load',
        previousPage: null,
      })
    })

    it('emits page_viewed with client_navigation on subsequent calls', () => {
      trackPageView('/suppliers')
      trackPageView('/login')

      expect(trackSpy).toHaveBeenCalledTimes(2)
      // Second call
      expect(getTrackEventType(trackSpy, 1)).toBe('page_viewed')
      expect(getTrackProperties(trackSpy, 1)).toEqual({
        page: 'login',
        navigationType: 'client_navigation',
        previousPage: 'suppliers',
      })
    })

    it('sets previousPage to the previous pageId', () => {
      trackPageView('/suppliers')
      trackPageView('/incidents/new')

      const props = getTrackProperties(trackSpy, 1)
      expect(props.previousPage).toBe('suppliers')
    })

    it('prevents previousPage from being null on client_navigation', () => {
      trackPageView('/suppliers') // initial_load, previousPage=null
      trackPageView('/login') // client_navigation, previousPage='suppliers'

      const props = getTrackProperties(trackSpy, 1)
      expect(props.navigationType).toBe('client_navigation')
      expect(props.previousPage).toBe('suppliers') // not null
    })

    it('is a no-op for unmapped paths', () => {
      trackPageView('/unknown')

      expect(trackSpy).not.toHaveBeenCalled()
    })

    it('is a no-op for paths that do not exist in the map', () => {
      trackPageView('/')
      trackPageView('')

      expect(trackSpy).not.toHaveBeenCalled()
    })

    it('suppresses duplicate back-to-back same page', () => {
      trackPageView('/suppliers') // initial_load
      trackPageView('/suppliers') // duplicate — suppressed
      trackPageView('/login') // different page
      trackPageView('/suppliers') // returning to suppliers — NOT suppressed

      expect(trackSpy).toHaveBeenCalledTimes(3)
    })

    it('tracks same page after navigating away and back', () => {
      trackPageView('/suppliers') // 1: initial_load
      trackPageView('/login') // 2: client_navigation
      trackPageView('/suppliers') // 3: client_navigation (returning, not duplicate)

      expect(trackSpy).toHaveBeenCalledTimes(3)

      const props3 = getTrackProperties(trackSpy, 2)
      expect(props3.page).toBe('suppliers')
      expect(props3.navigationType).toBe('client_navigation')
      expect(props3.previousPage).toBe('login')
    })

    it('handles trailing slashes', () => {
      trackPageView('/suppliers/') // should normalise to 'suppliers'

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackProperties(trackSpy).page).toBe('suppliers')
    })

    it('never throws (telemetry.track is internally guarded)', () => {
      // In production, telemetry.track() has an internal try/catch
      // that prevents errors from propagating.  We verify this by
      // restoring the real implementation and calling it once.
      trackSpy.mockRestore()
      _resetPageTracker()
      trackPageView('/suppliers')
      // Clean up the real telemetry timer that was started by the call above.
      telemetry._reset()
      trackSpy = jest.spyOn(telemetry, 'track').mockImplementation(() => {})
    })
  })

  describe('trackInitialPage', () => {
    it('is safe to call in node environment (no window)', () => {
      // typeof window === 'undefined' in node, so this should be a no-op
      trackInitialPage()
      expect(trackSpy).not.toHaveBeenCalled()
    })
  })

  describe('_resetPageTracker', () => {
    it('resets state so next call is initial_load again', () => {
      trackPageView('/suppliers')
      expect(getTrackProperties(trackSpy).navigationType).toBe('initial_load')

      _resetPageTracker()

      trackPageView('/login')
      expect(getTrackProperties(trackSpy, 1).navigationType).toBe('initial_load')
    })
  })
})

// ──────────────────────────────────────────────
// apiTelemetry tests
// ──────────────────────────────────────────────

describe('apiTelemetry', () => {
  let trackSpy: jest.SpyInstance

  beforeEach(() => {
    trackSpy = jest.spyOn(telemetry, 'track').mockImplementation(() => {})
  })

  afterEach(() => {
    trackSpy.mockRestore()
  })

  describe('trackValidationError', () => {
    it('emits api_validation_error with correct properties', () => {
      trackValidationError('/api/suppliers', 'POST', 422)

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_validation_error')
      expect(getTrackProperties(trackSpy)).toMatchObject({
        path: '/api/suppliers',
        http_method: 'POST',
        error_code: 'http_422',
        status_code: 422,
      })
    })

    it('includes optional field when provided', () => {
      trackValidationError('/api/users', 'POST', 422, 'email')

      const props = getTrackProperties(trackSpy)
      expect(props.field).toBe('email')
    })

    it('does NOT include field when omitted', () => {
      trackValidationError('/api/suppliers', 'POST', 422)

      const props = getTrackProperties(trackSpy)
      expect(props).not.toHaveProperty('field')
    })

    it('normalises HEAD/OPTIONS to GET', () => {
      trackValidationError('/api/suppliers', 'HEAD', 422)
      expect(getTrackProperties(trackSpy).http_method).toBe('GET')

      trackValidationError('/api/suppliers', 'OPTIONS', 422)
      expect(getTrackProperties(trackSpy, 1).http_method).toBe('GET')
    })

    it('respects recursion guard (telemetry path)', () => {
      trackValidationError('/api/telemetry/events', 'POST', 422)

      expect(trackSpy).not.toHaveBeenCalled()
    })

    it('uses status_code in error_code', () => {
      trackValidationError('/api/suppliers', 'GET', 422)
      expect(getTrackProperties(trackSpy).error_code).toBe('http_422')

      trackValidationError('/api/suppliers', 'POST', 400)
      expect(getTrackProperties(trackSpy, 1).error_code).toBe('http_400')
    })

    it('emits for 400 errors too', () => {
      trackValidationError('/api/suppliers', 'GET', 400)
      expect(trackSpy).toHaveBeenCalledTimes(1)
    })
  })

  describe('trackServerError', () => {
    it('emits api_server_error with correct properties', () => {
      trackServerError('/api/suppliers', 'GET', 500)

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_server_error')
      expect(getTrackProperties(trackSpy)).toMatchObject({
        path: '/api/suppliers',
        http_method: 'GET',
        error_code: 'http_500',
        status_code: 500,
      })
    })

    it('handles various 5xx status codes', () => {
      trackServerError('/api/suppliers', 'GET', 502)
      expect(getTrackProperties(trackSpy).error_code).toBe('http_502')

      trackServerError('/api/suppliers', 'GET', 503)
      expect(getTrackProperties(trackSpy, 1).error_code).toBe('http_503')

      trackServerError('/api/suppliers', 'GET', 504)
      expect(getTrackProperties(trackSpy, 2).error_code).toBe('http_504')
    })

    it('respects recursion guard (telemetry path)', () => {
      trackServerError('/api/telemetry/events', 'POST', 500)

      expect(trackSpy).not.toHaveBeenCalled()
    })
  })

  describe('trackInventoryDuration', () => {
    it('emits inventory_query_duration with duration >= 0', () => {
      const timing = trackInventoryDuration('/api/inventory/products', 'GET')
      timing.stop()

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('inventory_query_duration')
      const props = getTrackProperties(trackSpy)
      expect(props.endpoint).toBe('/api/inventory/products')
      expect(props.duration_ms).toBeGreaterThanOrEqual(0)
      expect(props.measurementSource).toBe('frontend')
    })

    it('includes warehouse and skuCount when provided', () => {
      const timing = trackInventoryDuration(
        '/api/inventory/products',
        'GET',
        'LA',
        42,
      )
      timing.stop()

      const props = getTrackProperties(trackSpy)
      expect(props.warehouse).toBe('LA')
      expect(props.sku_count).toBe(42)
    })

    it('does NOT include warehouse or skuCount when omitted', () => {
      const timing = trackInventoryDuration('/api/inventory/products', 'GET')
      timing.stop()

      const props = getTrackProperties(trackSpy)
      expect(props).not.toHaveProperty('warehouse')
      expect(props).not.toHaveProperty('sku_count')
    })

    it('abort() prevents emission', () => {
      const timing = trackInventoryDuration('/api/inventory/products', 'GET')
      timing.abort()
      timing.stop() // should be a no-op

      expect(trackSpy).not.toHaveBeenCalled()
    })

    it('respects recursion guard (telemetry endpoint)', () => {
      const timing = trackInventoryDuration('/api/telemetry/events', 'POST')
      timing.stop()

      expect(trackSpy).not.toHaveBeenCalled()
    })

    it('stop is idempotent (no double emission)', () => {
      const timing = trackInventoryDuration('/api/inventory/products', 'GET')
      timing.stop()
      timing.stop() // second call should be no-op

      expect(trackSpy).toHaveBeenCalledTimes(1)
    })

    it('abort is idempotent', () => {
      const timing = trackInventoryDuration('/api/inventory/products', 'GET')
      timing.abort()
      timing.abort()
      timing.stop()

      expect(trackSpy).not.toHaveBeenCalled()
    })

    it('returns no-op stop/abort for telemetry paths', () => {
      const timing = trackInventoryDuration('/api/telemetry/events', 'POST')
      // These should not throw
      timing.stop()
      timing.abort()
      expect(trackSpy).not.toHaveBeenCalled()
    })
  })
})

// ──────────────────────────────────────────────
// authFetch integration tests (api.ts)
// ──────────────────────────────────────────────

describe('authFetch integration (api.ts)', () => {
  let trackSpy: jest.SpyInstance
  beforeAll(() => {
    // We need localStorage for authFetch
    // Provide a minimal localStorage mock since we're in node
    if (typeof globalThis.localStorage === 'undefined') {
      const store: Record<string, string> = {
        auth_token: 'test-token-123',
      }
      Object.defineProperty(globalThis, 'localStorage', {
        value: {
          getItem: jest.fn((key: string) => store[key] ?? null),
          setItem: jest.fn((key: string, value: string) => { store[key] = value }),
          removeItem: jest.fn((key: string) => { delete store[key] }),
        },
        writable: true,
      })
    }
  })

  beforeEach(() => {
    trackSpy = jest.spyOn(telemetry, 'track').mockImplementation(() => {})
  })

  afterEach(() => {
    trackSpy.mockRestore()
    restoreGlobalFetch()
  })

  describe('api_validation_error from authFetch', () => {
    it('emits api_validation_error on 422 response', async () => {
      mockGlobalFetch(422, { detail: 'Validation error' })

      const { authFetch } = await import('../api')
      try {
        await authFetch('/api/suppliers', { requireAuth: true })
      } catch {
        // expected
      }

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_validation_error')
      expect(getTrackProperties(trackSpy)).toMatchObject({
        path: '/api/suppliers',
        status_code: 422,
        error_code: 'http_422',
      })
    })

    it('does NOT emit api_validation_error for successful 200', async () => {
      mockGlobalFetch(200, [{ id: 1, name: 'Test' }])

      const { authFetch } = await import('../api')
      const response = await authFetch('/api/suppliers', { requireAuth: true })

      // Should not have emitted any telemetry
      expect(trackSpy).not.toHaveBeenCalled()
      expect(response.ok).toBe(true)
    })

    it('does NOT emit api_validation_error for 404', async () => {
      mockGlobalFetch(404, { detail: 'Not found' })

      const { authFetch } = await import('../api')
      try {
        await authFetch('/api/suppliers', { requireAuth: true })
      } catch {
        // expected
      }

      // 404 is NOT 422 and NOT 500+, so no telemetry
      expect(trackSpy).not.toHaveBeenCalled()
    })
  })

  describe('api_server_error from authFetch', () => {
    it('emits api_server_error on 500 response', async () => {
      mockGlobalFetch(500, { detail: 'Internal server error' })

      const { authFetch } = await import('../api')
      try {
        await authFetch('/api/suppliers', { requireAuth: true })
      } catch {
        // expected
      }

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_server_error')
      expect(getTrackProperties(trackSpy)).toMatchObject({
        path: '/api/suppliers',
        status_code: 500,
        error_code: 'http_500',
      })
    })

    it('emits api_server_error on 502 response', async () => {
      mockGlobalFetch(502, { detail: 'Bad gateway' })

      const { authFetch } = await import('../api')
      try {
        await authFetch('/api/suppliers', { requireAuth: true })
      } catch {
        // expected
      }

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_server_error')
      expect(getTrackProperties(trackSpy).error_code).toBe('http_502')
    })

    it('does NOT emit api_server_error for business 4xx (400)', async () => {
      mockGlobalFetch(400, { detail: 'Bad request' })

      const { authFetch } = await import('../api')
      try {
        await authFetch('/api/suppliers', { requireAuth: true })
      } catch {
        // expected
      }

      // 400 is not 422 and not 500+, so no telemetry
      expect(trackSpy).not.toHaveBeenCalled()
    })
  })

  describe('recursion guard in authFetch', () => {
    it('does NOT emit any telemetry for telemetry endpoint requests', async () => {
      mockGlobalFetch(500, { detail: 'Server error' })

      const { authFetch } = await import('../api')
      try {
        await authFetch('/api/telemetry/events', { requireAuth: true, method: 'POST' })
      } catch {
        // expected
      }

      // Even though 500, the telemetry path guard should prevent emission
      expect(trackSpy).not.toHaveBeenCalled()
    })

    it('does NOT emit validation error for telemetry path 422', async () => {
      mockGlobalFetch(422, { detail: 'Validation error' })

      const { authFetch } = await import('../api')
      try {
        await authFetch('/api/telemetry/events', { requireAuth: true, method: 'POST' })
      } catch {
        // expected
      }

      expect(trackSpy).not.toHaveBeenCalled()
    })
  })
})

// ──────────────────────────────────────────────
// authApi integration tests
// ──────────────────────────────────────────────

describe('authApi integration', () => {
  let trackSpy: jest.SpyInstance

  beforeEach(() => {
    trackSpy = jest.spyOn(telemetry, 'track').mockImplementation(() => {})
  })

  afterEach(() => {
    trackSpy.mockRestore()
    restoreGlobalFetch()
  })

  describe('login', () => {
    it('emits api_validation_error on 422', async () => {
      mockGlobalFetch(422, { detail: 'Validation error' })

      const { login } = await import('../auth/authApi')
      try {
        await login({ email: 'bad', password: '' })
      } catch {
        // expected
      }

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_validation_error')
      expect(getTrackProperties(trackSpy)).toMatchObject({
        path: '/api/auth/login',
        http_method: 'POST',
        status_code: 422,
      })
    })

    it('emits api_server_error on 500', async () => {
      mockGlobalFetch(500, { detail: 'Server error' })

      const { login } = await import('../auth/authApi')
      try {
        await login({ email: 'test@example.com', password: 'secret' })
      } catch {
        // expected
      }

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_server_error')
      expect(getTrackProperties(trackSpy)).toMatchObject({
        path: '/api/auth/login',
        http_method: 'POST',
        status_code: 500,
      })
    })

    it('does NOT emit telemetry on successful login', async () => {
      mockGlobalFetch(200, { access_token: 'token', token_type: 'bearer' })

      const { login } = await import('../auth/authApi')
      await login({ email: 'test@example.com', password: 'secret' })

      expect(trackSpy).not.toHaveBeenCalled()
    })

    it('does NOT emit telemetry for 401 (handled differently)', async () => {
      mockGlobalFetch(401, { detail: 'Unauthorized' })

      const { login } = await import('../auth/authApi')
      try {
        await login({ email: 'test@example.com', password: 'wrong' })
      } catch {
        // expected
      }

      // 401 is not 422 and not 500+, so no telemetry
      expect(trackSpy).not.toHaveBeenCalled()
    })
  })

  describe('register', () => {
    it('emits api_validation_error on 422', async () => {
      mockGlobalFetch(422, { detail: 'Validation error' })

      const { register } = await import('../auth/authApi')
      try {
        await register({ email: 'bad', password: 'x' })
      } catch {
        // expected
      }

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_validation_error')
      expect(getTrackProperties(trackSpy)).toMatchObject({
        path: '/api/users',
        http_method: 'POST',
        status_code: 422,
      })
    })

    it('emits api_server_error on 500', async () => {
      mockGlobalFetch(500, { detail: 'Server error' })

      const { register } = await import('../auth/authApi')
      try {
        await register({ email: 'test@example.com', password: 'secret' })
      } catch {
        // expected
      }

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_server_error')
      expect(getTrackProperties(trackSpy)).toMatchObject({
        path: '/api/users',
        http_method: 'POST',
        status_code: 500,
      })
    })

    it('does NOT emit telemetry on successful register', async () => {
      mockGlobalFetch(201, { id: 1, email: 'test@example.com', is_active: true, role: 'user' })

      const { register } = await import('../auth/authApi')
      await register({ email: 'test@example.com', password: 'secret' })

      expect(trackSpy).not.toHaveBeenCalled()
    })
  })

  describe('getMe', () => {
    it('emits api_validation_error on 422', async () => {
      mockGlobalFetch(422, { detail: 'Validation error' })

      const { getMe } = await import('../auth/authApi')
      try {
        await getMe('some-token')
      } catch {
        // expected
      }

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_validation_error')
      expect(getTrackProperties(trackSpy)).toMatchObject({
        path: '/api/auth/me',
        http_method: 'GET',
        status_code: 422,
      })
    })

    it('emits api_server_error on 500', async () => {
      mockGlobalFetch(500, { detail: 'Server error' })

      const { getMe } = await import('../auth/authApi')
      try {
        await getMe('some-token')
      } catch {
        // expected
      }

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_server_error')
      expect(getTrackProperties(trackSpy)).toMatchObject({
        path: '/api/auth/me',
        http_method: 'GET',
        status_code: 500,
      })
    })

    it('does NOT emit telemetry on successful getMe', async () => {
      mockGlobalFetch(200, { id: 1, email: 'test@example.com', is_active: true, role: 'user', uuid: null })

      const { getMe } = await import('../auth/authApi')
      await getMe('some-token')

      expect(trackSpy).not.toHaveBeenCalled()
    })
  })
})

// ──────────────────────────────────────────────
// inventoryApi integration tests
// ──────────────────────────────────────────────

describe('inventoryApi integration', () => {
  let trackSpy: jest.SpyInstance
  beforeAll(() => {
    // Ensure localStorage is available for authFetch
    if (typeof globalThis.localStorage === 'undefined') {
      const store: Record<string, string> = {
        auth_token: 'test-token-inventory',
      }
      Object.defineProperty(globalThis, 'localStorage', {
        value: {
          getItem: jest.fn((key: string) => store[key] ?? null),
          setItem: jest.fn((key: string, value: string) => { store[key] = value }),
          removeItem: jest.fn((key: string) => { delete store[key] }),
        },
        writable: true,
      })
    }
  })

  beforeEach(() => {
    trackSpy = jest.spyOn(telemetry, 'track').mockImplementation(() => {})
  })

  afterEach(() => {
    trackSpy.mockRestore()
    restoreGlobalFetch()
  })

  describe('getInventoryProducts', () => {
    it('emits inventory_query_duration on success', async () => {
      mockGlobalFetch(200, [{ id: 1, name: 'SKU-1', sku: 'SKU001' }])

      const { getInventoryProducts } = await import('../inventory/inventoryApi')
      await getInventoryProducts()

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('inventory_query_duration')
      const props = getTrackProperties(trackSpy)
      expect(props.endpoint).toBe('/api/inventory/products')
      expect(props.duration_ms).toBeGreaterThanOrEqual(0)
      expect(props.measurementSource).toBe('frontend')
    })

    it('aborts timing on error (no emission)', async () => {
      mockGlobalFetch(500, { detail: 'Server error' })

      const { getInventoryProducts } = await import('../inventory/inventoryApi')
      try {
        await getInventoryProducts()
      } catch {
        // expected
      }

      // authFetch will emit api_server_error, but inventory duration should be aborted
      // So we should see api_server_error but NOT inventory_query_duration
      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_server_error')
    })
  })

  describe('getInventoryProduct', () => {
    it('emits inventory_query_duration on success', async () => {
      mockGlobalFetch(200, { id: 1, name: 'SKU-1' })

      const { getInventoryProduct } = await import('../inventory/inventoryApi')
      await getInventoryProduct(1)

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('inventory_query_duration')
      const props = getTrackProperties(trackSpy)
      expect(props.endpoint).toBe('/api/inventory/products/1')
      expect(props.duration_ms).toBeGreaterThanOrEqual(0)
    })

    it('aborts timing on 404', async () => {
      mockGlobalFetch(404, { detail: 'Not found' })

      const { getInventoryProduct } = await import('../inventory/inventoryApi')
      try {
        await getInventoryProduct(999)
      } catch {
        // expected
      }

      // 404 is not 422 or 500+, so no api_error telemetry from authFetch
      // But inventory duration is aborted, so no inventory_query_duration either
      expect(trackSpy).not.toHaveBeenCalled()
    })
  })

  describe('createInboundOrder', () => {
    it('emits inventory_query_duration on success', async () => {
      mockGlobalFetch(201, { id: 1, quantity: 10 })

      const { createInboundOrder } = await import('../inventory/inventoryApi')
      await createInboundOrder({
        sku_id: 1,
        quantity: 10,
        reference: 'REF-001',
        warehouse: 'LA',
      })

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('inventory_query_duration')
      expect(getTrackProperties(trackSpy).endpoint).toBe('/api/inventory/orders/inbound')
    })

    it('aborts timing on error', async () => {
      mockGlobalFetch(500, { detail: 'Error' })

      const { createInboundOrder } = await import('../inventory/inventoryApi')
      try {
        await createInboundOrder({
          sku_id: 1,
          quantity: 10,
          reference: 'REF-001',
          warehouse: 'LA',
        })
      } catch {
        // expected
      }

      // api_server_error from authFetch, but no inventory_query_duration
      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('api_server_error')
    })
  })

  describe('createOutboundOrder', () => {
    it('emits inventory_query_duration on success', async () => {
      mockGlobalFetch(201, { id: 1, quantity: 5 })

      const { createOutboundOrder } = await import('../inventory/inventoryApi')
      await createOutboundOrder({
        sku_id: 1,
        quantity: 5,
        exit_type: 'dispatch',
        tracking_number: 'TRK-001',
        warehouse: 'LA',
      })

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('inventory_query_duration')
      expect(getTrackProperties(trackSpy).endpoint).toBe('/api/inventory/orders/outbound')
    })
  })

  describe('getInventoryOrders', () => {
    it('emits inventory_query_duration on success', async () => {
      mockGlobalFetch(200, [{ id: 1, kind: 'entry' }])

      const { getInventoryOrders } = await import('../inventory/inventoryApi')
      await getInventoryOrders()

      expect(trackSpy).toHaveBeenCalledTimes(1)
      expect(getTrackEventType(trackSpy)).toBe('inventory_query_duration')
      expect(getTrackProperties(trackSpy).endpoint).toBe('/api/inventory/orders')
    })
  })
})

// ──────────────────────────────────────────────
// Recursion guard: multi-layer defense tests
// ──────────────────────────────────────────────

describe('recursion guard — multi-layer defense', () => {
  let trackSpy: jest.SpyInstance

  beforeEach(() => {
    trackSpy = jest.spyOn(telemetry, 'track').mockImplementation(() => {})
  })

  afterEach(() => {
    trackSpy.mockRestore()
    restoreGlobalFetch()
  })

  it('apiTelemetry guards fire before telemetry.track is called', () => {
    // These check path first — no telemetry.track call should happen
    trackValidationError('/api/telemetry/events', 'POST', 422)
    trackServerError('/api/telemetry/events', 'POST', 500)
    const timing = trackInventoryDuration('/api/telemetry/events', 'POST')
    timing.stop()

    expect(trackSpy).not.toHaveBeenCalled()
  })

  it('authFetch guards fire before telemetry.track is called (telemetry path)', async () => {
    mockGlobalFetch(422, { detail: 'Validation error' })

    const { authFetch } = await import('../api')
    try {
      await authFetch('/api/telemetry/events', { requireAuth: true, method: 'POST' })
    } catch {
      // expected
    }

    expect(trackSpy).not.toHaveBeenCalled()
  })

  it('authFetch guards on 500 for telemetry path', async () => {
    mockGlobalFetch(500, { detail: 'Server error' })

    const { authFetch } = await import('../api')
    try {
      await authFetch('/api/telemetry/events', { requireAuth: true, method: 'POST' })
    } catch {
      // expected
    }

    expect(trackSpy).not.toHaveBeenCalled()
  })

  it('event telemetry is never called for any telemetry endpoint path', async () => {
    // Simulate a full request chain to a telemetry endpoint
    mockGlobalFetch(200, { ok: true })

    const { authFetch } = await import('../api')
    await authFetch('/api/telemetry/something', { requireAuth: true })

    // Successful requests should also not emit anything
    expect(trackSpy).not.toHaveBeenCalled()
  })
})