import { authFetch } from '../api'

export type RfpCreatedEvent = {
  id: string
  ticket_id: string
  status: string
}

type Handlers = {
  onEvent: (event: RfpCreatedEvent) => void
  onConnected: () => void
}

export function parseRfpSseFrame(frame: string): RfpCreatedEvent | null {
  let eventName = ''
  let eventId = ''
  const dataLines: string[] = []

  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue

    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('id:')) {
      eventId = line.slice(3).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }

  if (eventName !== 'rfp.created' || !/^\d+-\d+$/.test(eventId)) {
    return null
  }

  try {
    const value: unknown = JSON.parse(dataLines.join('\n'))

    if (!value || typeof value !== 'object') return null

    const data = value as Record<string, unknown>

    if (typeof data.ticket_id !== 'string' ||
        typeof data.status !== 'string') {
      return null
    }

    return {
      id: eventId,
      ticket_id: data.ticket_id,
      status: data.status,
    }
  } catch {
    return null
  }
}

export function subscribeToRfpNotifications(
  handlers: Handlers,
): () => void {
  let stopped = false
  let cursor: string | null = null
  let attempts = 0
  let controller: AbortController | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  const seenEventIds = new Set<string>()

  async function connect(): Promise<void> {
    if (stopped) return

    const currentController = new AbortController()
    controller = currentController

    try {
      const headers = new Headers()
      headers.set('Accept', 'text/event-stream')

      if (cursor) {
        headers.set('Last-Event-ID', cursor)
      }

      const response = await authFetch('/api/rfp/events', {
        method: 'GET',
        headers,
        signal: currentController.signal,
        cache: 'no-store',
      })

      if (!response.ok || !response.body) {
        throw new Error(`SSE unavailable: HTTP ${response.status}`)
      }

      const contentType = response.headers.get('content-type') || ''

      if (!contentType.includes('text/event-stream')) {
        throw new Error('Unexpected SSE content type')
      }

      attempts = 0
      handlers.onConnected()

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let pending = ''

      try {
        while (!stopped) {
          const { value, done } = await reader.read()

          if (done) break

          pending += decoder.decode(value, { stream: true })
          pending = pending.replace(/\r\n/g, '\n')

          if (pending.length > 65536) {
            throw new Error('SSE frame too large')
          }

          let separator = pending.indexOf('\n\n')

          while (separator !== -1) {
            const frame = pending.slice(0, separator)
            pending = pending.slice(separator + 2)

            const event = parseRfpSseFrame(frame)

            if (event && !seenEventIds.has(event.id)) {
              seenEventIds.add(event.id)
              cursor = event.id
              handlers.onEvent(event)
            }

            separator = pending.indexOf('\n\n')
          }
        }
      } finally {
        void reader.cancel().catch(() => undefined)
      }
    } catch (error) {
      if (stopped || currentController.signal.aborted) return

      const message = error instanceof Error ? error.message : ''

      if (
        message === 'Authentication required' ||
        message === 'Session expired'
      ) {
        stopped = true
        return
      }
    } finally {
      if (controller === currentController) controller = null

      if (!stopped) {
        const delay = Math.min(1000 * 2 ** attempts, 30000)
        attempts = Math.min(attempts + 1, 5)

        retryTimer = setTimeout(() => {
          retryTimer = null
          void connect()
        }, delay)
      }
    }
  }

  void connect()

  return () => {
    stopped = true

    if (retryTimer !== null) {
      clearTimeout(retryTimer)
    }

    controller?.abort()
  }
}

export function mergeRfpTicketSnapshot<T extends { ticket_id: string }>(
  latest: T[],
  current: T[],
  startedAtRevision: number,
  liveTicketRevision: ReadonlyMap<string, number>,
): T[] {
  const merged = new Map<string, T>(
    latest.map((ticket) => [ticket.ticket_id, ticket])
  )

  for (const ticket of current) {
    const revision = liveTicketRevision.get(ticket.ticket_id) ?? 0

    if (revision > startedAtRevision) {
      merged.set(ticket.ticket_id, ticket)
    }
  }

  return [...merged.values()]
}
