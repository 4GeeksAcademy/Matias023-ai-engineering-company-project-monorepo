/// <reference types="jest" />
import { parseRfpSseFrame } from './rfpSse'

describe('RFP SSE framing', () => {
  it('reads a named RFP creation event', () => {
    const event = parseRfpSseFrame(
      'id: 100-0\n' +
      'event: rfp.created\n' +
      'data: {"ticket_id":"rfp-123","status":"analizando"}'
    )

    expect(event).toEqual({
      id: '100-0',
      ticket_id: 'rfp-123',
      status: 'analizando',
    })
  })

  it('ignores heartbeat frames', () => {
    expect(parseRfpSseFrame(': keep-alive')).toBeNull()
  })

  it('rejects malformed event payloads', () => {
    expect(
      parseRfpSseFrame(
        'id: 100-0\n' +
        'event: rfp.created\n' +
        'data: not-json'
      )
    ).toBeNull()
  })

  it('ignores unrelated event types', () => {
    expect(
      parseRfpSseFrame(
        'id: 100-0\n' +
        'event: other.event\n' +
        'data: {"ticket_id":"123","status":"analizando"}'
      )
    ).toBeNull()
  })
})
