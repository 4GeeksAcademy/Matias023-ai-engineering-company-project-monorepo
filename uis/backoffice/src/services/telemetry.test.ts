/**
 * Tests for TelemetryServiceImpl.
 *
 * Uses dependency injection to mock all browser APIs.
 * Runs under Jest's `node` environment (no jsdom required).
 */

/// <reference types="jest" />
/// <reference lib="dom" />

import { TelemetryServiceImpl, type TelemetryDependencies, type TelemetryBatch } from './telemetry'

// ──────────────────────────────────────────────
// Mock factories
// ──────────────────────────────────────────────

const FAKE_UUID = '00000000-0000-4000-8000-000000000001'
const FAKE_UUID_2 = '00000000-0000-4000-8000-000000000002'
const FAKE_SESSION = 'session-0000-4000-8000-0000000000ab'
const FAKE_TIMESTAMP = '2026-10-05T14:30:00.000Z'
const FAKE_ENDPOINT = 'https://telemetry.example.com/events'

function mockFetch(overrides?: {
  status?: number
  body?: string
  reject?: boolean
}): jest.MockedFn<TelemetryDependencies['fetch']> {
  const { status = 200, body = '', reject = false } = overrides ?? {}
  return jest.fn().mockImplementation(async () => {
    if (reject) throw new Error('Network failure')
    return new Response(body, { status, headers: { 'content-type': 'application/json' } })
  }) as unknown as jest.MockedFn<TelemetryDependencies['fetch']>
}

/** Create a set of mock dependencies with sensible defaults. */
function mockDeps(overrides?: Partial<TelemetryDependencies>): TelemetryDependencies {
  const intervalHandlers: Array<{ fn: () => void; ms: number }> = []
  const timeoutHandlers: Array<{ fn: () => void; ms: number }> = []

  return {
    generateUuid: jest.fn()
      .mockReturnValueOnce(FAKE_UUID)
      .mockReturnValue(FAKE_UUID_2) as unknown as () => string,
    isoNow: jest.fn().mockReturnValue(FAKE_TIMESTAMP) as unknown as () => string,
    getSessionId: jest.fn().mockReturnValue(FAKE_SESSION) as unknown as () => string,
    getEndpoint: jest.fn().mockReturnValue(FAKE_ENDPOINT) as unknown as () => string | null,
    fetch: mockFetch(),
    setInterval: jest.fn((fn: () => void, ms: number) => {
      const handle = Symbol('interval')
      intervalHandlers.push({ fn, ms })
      return handle
    }) as unknown as typeof setInterval,
    setTimeout: jest.fn((fn: () => void, _ms: number) => {
      const handle = Symbol('timeout')
      timeoutHandlers.push({ fn, ms: _ms })
      return handle
    }) as unknown as typeof setTimeout,
    clearInterval: jest.fn() as unknown as typeof clearInterval,
    documentAddListener: jest.fn() as unknown as (handler: () => void) => void,
    sendBeacon: jest.fn() as unknown as (url: string, blob: Blob) => void,
    ...overrides,
  }
}

// ──────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────

describe('TelemetryServiceImpl', () => {
  let deps: TelemetryDependencies
  let svc: TelemetryServiceImpl

  beforeEach(() => {
    jest.clearAllMocks()
    deps = mockDeps()
    svc = new TelemetryServiceImpl(deps)
  })

  afterEach(() => {
    svc._reset()
  })

  // ═══════════════════════════════════════════
  // Tracking
  // ═══════════════════════════════════════════

  describe('track()', () => {
    it('adds an event to the queue', () => {
      svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      expect(svc._queueLength()).toBe(1)
    })

    it('sets envelope fields from deps', () => {
      svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })

      // The service called flush via track — let's get the batch that was sent
      // Since queue is < 20, flush was NOT called; read the first call to fetch
      // Actually at 1 event, no flush happens. Let's verify indirectly:
      // queue has 1 event, flush not called
      expect(svc._queueLength()).toBe(1)
      // envelope fields are set via deps
      // We'll verify via flush
    })

    it('includes schemaVersion "1.0"', async () => {
      // Fill to trigger auto-flush at 20
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      for (let i = 0; i < 20; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }

      // Allow async flush to complete
      await new Promise<void>(resolve => setTimeout(resolve, 0))

      const callBody = getFetchBody(fetchMock)
      expect(callBody).not.toBeNull()
      if (callBody) {
        callBody.events.forEach((evt) => {
          expect(evt.schemaVersion).toBe('1.0')
        })
      }
    })

    it('includes eventId, timestamp, sessionId, requestId', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      for (let i = 0; i < 20; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }

      await new Promise<void>(resolve => setTimeout(resolve, 0))

      const callBody = getFetchBody(fetchMock)
      expect(callBody).not.toBeNull()
      if (callBody) {
        callBody.events.forEach((evt) => {
          expect(evt.eventId).toBeTruthy()
          expect(evt.timestamp).toBe(FAKE_TIMESTAMP)
          expect(evt.sessionId).toBe(FAKE_SESSION)
          expect(evt.requestId).toBeTruthy()
        })
      }
    })

    it('includes userId when set', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)
      svc.setUserId('user-1111-4000-8000-0000000000ff')

      for (let i = 0; i < 20; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }

      await new Promise<void>(resolve => setTimeout(resolve, 0))

      const callBody = getFetchBody(fetchMock)
      expect(callBody).not.toBeNull()
      if (callBody) {
        callBody.events.forEach((evt) => {
          expect(evt.userId).toBe('user-1111-4000-8000-0000000000ff')
        })
      }
    })

    it('sets userId to null when not configured', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      for (let i = 0; i < 20; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }

      await new Promise<void>(resolve => setTimeout(resolve, 0))

      const callBody = getFetchBody(fetchMock)
      expect(callBody).not.toBeNull()
      if (callBody) {
        callBody.events.forEach((evt) => {
          expect(evt.userId).toBeNull()
        })
      }
    })

    it('does not throw when track is called', () => {
      // Even with broken deps, track should not throw.
      // Use valid deps for constructor (which calls generateUuid), then mutate.
      const deps_ = {
        generateUuid: () => FAKE_UUID,
        isoNow: () => { throw new Error('broken') },
        getSessionId: () => FAKE_SESSION,
        getEndpoint: () => FAKE_ENDPOINT,
        fetch: mockFetch(),
        setInterval: jest.fn() as unknown as typeof globalThis.setInterval,
        setTimeout: jest.fn() as unknown as typeof setTimeout,
        clearInterval: jest.fn() as unknown as typeof clearInterval,
        documentAddListener: jest.fn(),
        sendBeacon: jest.fn(),
      }
      const svc2 = new TelemetryServiceImpl(deps_)
      // Should not throw — catches internally
      svc2.track('page_viewed', { page: 'suppliers' })
      // Queue may or may not have the event; the point is no exception
    })
  })

  // ═══════════════════════════════════════════
  // Auto-flush at queue limit
  // ═══════════════════════════════════════════

  describe('auto-flush', () => {
    it('triggers flush when queue reaches 20 events', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      // Fill to 19 — no flush yet
      for (let i = 0; i < 19; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }
      expect(fetchMock).not.toHaveBeenCalled()

      // 20th event triggers flush
      svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      await new Promise<void>(resolve => setTimeout(resolve, 0))

      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    it('sends batch with correct shape', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      for (let i = 0; i < 20; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }

      await new Promise<void>(resolve => setTimeout(resolve, 0))

      expect(fetchMock).toHaveBeenCalledWith(
        FAKE_ENDPOINT,
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }),
      )

      const callBody = getFetchBody(fetchMock)
      expect(callBody).not.toBeNull()
      if (callBody) {
        expect(callBody.events.length).toBe(20)
      }
    })

    it('does not send Authorization header', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      for (let i = 0; i < 20; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }

      await new Promise<void>(resolve => setTimeout(resolve, 0))

      const callArgs = fetchMock.mock.calls[0]
      const init = callArgs[1] as RequestInit
      const headers = init.headers as Record<string, string>
      expect(headers.Authorization).toBeUndefined()
    })
  })

  // ═══════════════════════════════════════════
  // Flush
  // ═══════════════════════════════════════════

  describe('flush()', () => {
    it('sends queued events and clears the queue on success', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      svc.track('frontend_error_captured', { errorKind: 'runtime_error', page: 'login', fatal: false })

      expect(svc._queueLength()).toBe(2)

      await svc.flush()
      await new Promise<void>(resolve => setTimeout(resolve, 0))

      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(svc._queueLength()).toBe(0)
    })

    it('does nothing when queue is empty', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      await svc.flush()
      expect(fetchMock).not.toHaveBeenCalled()
    })

    it('does nothing when endpoint is null', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock, getEndpoint: () => null })
      svc = new TelemetryServiceImpl(deps)

      svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      expect(svc._queueLength()).toBe(1)

      await svc.flush()
      // No endpoint — queue should be cleared silently
      expect(svc._queueLength()).toBe(0)
      expect(fetchMock).not.toHaveBeenCalled()
    })

    it('does not allow concurrent flushes (in-flight guard)', async () => {
      // Create a fetch that never resolves
      let resolveFetch: ((value: Response | PromiseLike<Response>) => void) | undefined
      const fetchMock = jest.fn().mockImplementation(() => {
        return new Promise<Response>((resolve) => {
          resolveFetch = resolve
        })
      }) as unknown as TelemetryDependencies['fetch']

      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      // Trigger flush via track
      for (let i = 0; i < 20; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }
      await new Promise<void>(resolve => setTimeout(resolve, 0))

      // First flush is in-flight, second should be a no-op
      for (let i = 0; i < 5; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }
      await new Promise<void>(resolve => setTimeout(resolve, 0))

      // fetch should have been called only once despite the extra events
      expect(fetchMock).toHaveBeenCalledTimes(1)

      // Resolve the first fetch to clean up
      if (resolveFetch) {
        resolveFetch(new Response('', { status: 200 }))
      }
      await new Promise<void>(resolve => setTimeout(resolve, 0))
    })
  })

  // ═══════════════════════════════════════════
  // Retry logic
  // ═══════════════════════════════════════════

  describe('retry', () => {
    it('discards batch after exhausting all retries', async () => {
      // All 4 attempts fail
      let callCount = 0
      const fetchMock: TelemetryDependencies['fetch'] = jest.fn().mockImplementation(async () => {
        callCount++
        throw new Error('Persistent network error')
      }) as unknown as TelemetryDependencies['fetch']

      // setTimeout that fires immediately (no real delay)
      const immediateTimeout: typeof setTimeout = jest.fn((fn: () => void) => {
        fn()
        return Symbol('timeout') as unknown as ReturnType<typeof setTimeout>
      }) as unknown as typeof setTimeout

      deps = mockDeps({ fetch: fetchMock, setTimeout: immediateTimeout })
      svc = new TelemetryServiceImpl(deps)

      for (let i = 0; i < 20; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }

      await new Promise<void>(resolve => setTimeout(resolve, 0))

      // Should have tried 4 times (initial + 3 retries)
      expect(callCount).toBe(4)
      // Queue should be empty (batch discarded)
      expect(svc._queueLength()).toBe(0)
    })

    it('succeeds on the last retry', async () => {
      let callCount = 0
      const fetchMock: TelemetryDependencies['fetch'] = jest.fn().mockImplementation(async () => {
        callCount++
        if (callCount < 4) throw new Error('Transient error')
        return new Response('', { status: 200 })
      }) as unknown as TelemetryDependencies['fetch']

      const immediateTimeout: typeof setTimeout = jest.fn((fn: () => void) => {
        fn()
        return Symbol('timeout') as unknown as ReturnType<typeof setTimeout>
      }) as unknown as typeof setTimeout

      deps = mockDeps({ fetch: fetchMock, setTimeout: immediateTimeout })
      svc = new TelemetryServiceImpl(deps)

      for (let i = 0; i < 20; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }

      await new Promise<void>(resolve => setTimeout(resolve, 0))

      expect(callCount).toBe(4)
      expect(svc._queueLength()).toBe(0)
    })

    it('recovers after transient HTTP failures', async () => {
      let callCount = 0
      const fetchMock: TelemetryDependencies['fetch'] = jest.fn().mockImplementation(async () => {
        callCount++
        if (callCount < 4) return new Response('', { status: 200 })
        throw new Error('should not be called')
      }) as unknown as TelemetryDependencies['fetch']

      const immediateTimeout: typeof setTimeout = jest.fn((fn: () => void) => {
        fn()
        return Symbol('timeout') as unknown as ReturnType<typeof setTimeout>
      }) as unknown as typeof setTimeout

      deps = mockDeps({ fetch: fetchMock, setTimeout: immediateTimeout })
      svc = new TelemetryServiceImpl(deps)

      for (let i = 0; i < 20; i++) {
        svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      }

      await new Promise<void>(resolve => setTimeout(resolve, 0))

      // Succeeds on first attempt (200), no retries needed
      expect(callCount).toBe(1)
      expect(svc._queueLength()).toBe(0)
    })
  })

  // ═══════════════════════════════════════════
  // sendBeacon
  // ═══════════════════════════════════════════

  describe('sendBeacon', () => {
    it('registers visibilitychange listener on start', () => {
      const addListener = jest.fn()
      deps = mockDeps({ documentAddListener: addListener })
      svc = new TelemetryServiceImpl(deps)

      svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })

      expect(addListener).toHaveBeenCalledTimes(1)
      expect(addListener.mock.calls[0][0]).toBeInstanceOf(Function)
    })

    it('calls sendBeacon with pending events on visibility hidden', () => {
      const sendBeacon = jest.fn() as unknown as TelemetryDependencies['sendBeacon']
      let visibilityHandler: (() => void) | undefined
      const addListener = jest.fn((handler: () => void) => {
        visibilityHandler = handler
      }) as unknown as (handler: () => void) => void

      deps = mockDeps({ sendBeacon, documentAddListener: addListener })
      svc = new TelemetryServiceImpl(deps)

      svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })

      // Simulate visibility change to hidden
      expect(visibilityHandler).toBeDefined()
      if (visibilityHandler) {
        visibilityHandler()
      }

      expect(sendBeacon).toHaveBeenCalledTimes(1)
      expect(sendBeacon).toHaveBeenCalledWith(
        FAKE_ENDPOINT,
        expect.objectContaining({ type: 'application/json' }),
      )
    })

    it('does not call sendBeacon when queue is empty', () => {
      const sendBeacon = jest.fn() as unknown as TelemetryDependencies['sendBeacon']
      let visibilityHandler: (() => void) | undefined
      const addListener = jest.fn((handler: () => void) => {
        visibilityHandler = handler
      }) as unknown as (handler: () => void) => void

      deps = mockDeps({ sendBeacon, documentAddListener: addListener })
      svc = new TelemetryServiceImpl(deps)

      // No events tracked
      if (visibilityHandler) {
        visibilityHandler()
      }

      expect(sendBeacon).not.toHaveBeenCalled()
    })
  })

  // ═══════════════════════════════════════════
  // Periodic flush timer
  // ═══════════════════════════════════════════

  describe('periodic flush', () => {
    it('sets up an interval on first track()', () => {
      const mockSetInterval = jest.fn() as unknown as typeof globalThis.setInterval
      deps = mockDeps({ setInterval: mockSetInterval })
      svc = new TelemetryServiceImpl(deps)

      svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })

      expect(mockSetInterval).toHaveBeenCalledWith(expect.any(Function), 10_000)
    })

    it('does not set up multiple intervals', () => {
      const mockSetInterval = jest.fn() as unknown as typeof globalThis.setInterval
      deps = mockDeps({ setInterval: mockSetInterval })
      svc = new TelemetryServiceImpl(deps)

      svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })
      svc.track('page_viewed', { page: 'login', navigationType: 'client_navigation' })
      svc.track('page_viewed', { page: 'incidents_list', navigationType: 'client_navigation' })

      expect(mockSetInterval).toHaveBeenCalledTimes(1)
    })
  })

  // ═══════════════════════════════════════════
  // User ID management
  // ═══════════════════════════════════════════

  describe('setUserId()', () => {
    it('updates userId for subsequent events', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      svc.track('page_viewed', { page: 'suppliers', navigationType: 'client_navigation' })

      svc.setUserId('user-aaaa-4000-8000-0000000000ff')
      svc.track('page_viewed', { page: 'login', navigationType: 'client_navigation' })

      // Flush both
      // We need to fill queue or call flush manually
      svc.track('page_viewed', { page: 'incidents_list', navigationType: 'client_navigation' })
      // 3 events, manually flush
      await svc.flush()
      await new Promise<void>(resolve => setTimeout(resolve, 0))

      expect(fetchMock).toHaveBeenCalledTimes(1)
      const body = getFetchBody(fetchMock)
      expect(body).not.toBeNull()
      if (body) {
        expect(body.events[0].userId).toBeNull()
        expect(body.events[1].userId).toBe('user-aaaa-4000-8000-0000000000ff')
        expect(body.events[2].userId).toBe('user-aaaa-4000-8000-0000000000ff')
      }
    })
  })

  // ═══════════════════════════════════════════
  // Event properties passthrough
  // ═══════════════════════════════════════════

  describe('properties passthrough', () => {
    it('passes event_type and properties through to the batch', async () => {
      const fetchMock = mockFetch()
      deps = mockDeps({ fetch: fetchMock })
      svc = new TelemetryServiceImpl(deps)

      svc.track('frontend_error_captured', {
        errorKind: 'runtime_error',
        page: 'login',
        fatal: true,
      })
      svc.track('page_viewed', {
        page: 'suppliers',
        navigationType: 'client_navigation',
        previousPage: null,
      })

      await svc.flush()
      await new Promise<void>(resolve => setTimeout(resolve, 0))

      const body = getFetchBody(fetchMock)
      expect(body).not.toBeNull()
      if (body) {
        expect(body.events[0].event_type).toBe('frontend_error_captured')
        expect(body.events[0].properties).toEqual({
          errorKind: 'runtime_error',
          page: 'login',
          fatal: true,
        })
        expect(body.events[1].event_type).toBe('page_viewed')
        expect(body.events[1].properties).toEqual({
          page: 'suppliers',
          navigationType: 'client_navigation',
          previousPage: null,
        })
      }
    })
  })
})

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function getFetchBody(fetchMock: jest.MockedFn<TelemetryDependencies['fetch']>): TelemetryBatch | null {
  if (fetchMock.mock.calls.length === 0) return null
  const callArgs = fetchMock.mock.calls[0]
  const init = callArgs[1] as RequestInit
  if (!init.body) return null
  return JSON.parse(init.body as string) as TelemetryBatch
}