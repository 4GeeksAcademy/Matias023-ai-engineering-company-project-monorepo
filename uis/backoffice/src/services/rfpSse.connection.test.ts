/** @jest-environment node */
/// <reference types="jest" />

import { authFetch } from '../api'
import { subscribeToRfpNotifications } from './rfpSse'

jest.mock('../api', () => ({
  authFetch: jest.fn(),
}))

const mockFetch = authFetch as jest.MockedFunction<typeof authFetch>

function response(ids: string[]): Response {
  const chunks = ids.map((id) => {
    const frame = `id: ${id}\nevent: rfp.created\n` +
      'data: {"ticket_id":"test-1","status":"analizando"}\n\n'

    return Uint8Array.from(
      [...frame].map((character) => character.charCodeAt(0))
    )
  })

  let index = 0

  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'text/event-stream' }),
    body: {
      getReader: () => ({
        read: async () =>
          index < chunks.length
            ? { done: false, value: chunks[index++] }
            : { done: true, value: undefined },
        cancel: async () => undefined,
      }),
    },
  } as unknown as Response
}

async function flush() {
  for (let i = 0; i < 30; i++) {
    await Promise.resolve()
  }
}

describe('RFP SSE reconnection', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    mockFetch.mockReset()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('recovers missed events without duplicating IDs', async () => {
    mockFetch
      .mockResolvedValueOnce(response(['100-0']))
      .mockResolvedValueOnce(response(['100-0', '101-0']))

    const onEvent = jest.fn()
    const stop = subscribeToRfpNotifications({
      onEvent,
      onConnected: jest.fn(),
    })

    await flush()
    expect(onEvent).toHaveBeenCalledTimes(1)

    jest.advanceTimersByTime(1000)
    await flush()

    expect(mockFetch).toHaveBeenCalledTimes(2)

    const options = mockFetch.mock.calls[1][1]
    const headers = options?.headers as Headers

    expect(headers.get('Last-Event-ID')).toBe('100-0')
    expect(onEvent).toHaveBeenCalledTimes(2)
    expect(onEvent.mock.calls[1][0].id).toBe('101-0')

    stop()
  })

  it('uses exponential backoff after failures', async () => {
    mockFetch.mockRejectedValue(new Error('Network unavailable'))

    const stop = subscribeToRfpNotifications({
      onEvent: jest.fn(),
      onConnected: jest.fn(),
    })

    await flush()
    expect(mockFetch).toHaveBeenCalledTimes(1)

    jest.advanceTimersByTime(1000)
    await flush()
    expect(mockFetch).toHaveBeenCalledTimes(2)

    jest.advanceTimersByTime(2000)
    await flush()
    expect(mockFetch).toHaveBeenCalledTimes(3)

    stop()
  })

  it('cancels retries when unsubscribing', async () => {
    mockFetch.mockRejectedValue(new Error('Network unavailable'))

    const stop = subscribeToRfpNotifications({
      onEvent: jest.fn(),
      onConnected: jest.fn(),
    })

    await flush()

    stop()

    jest.advanceTimersByTime(30000)
    await flush()

    expect(mockFetch).toHaveBeenCalledTimes(1)
  })
})
