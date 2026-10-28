/// <reference types="jest" />
import { mergeRfpTicketSnapshot } from './rfpSse'

type Ticket = {
  ticket_id: string
  status: string
}

describe('RFP SSE snapshot concurrency', () => {
  const ticket = (ticket_id: string, status: string): Ticket => ({
    ticket_id,
    status,
  })

  test('preserves a new SSE ticket against an older HTTP response', () => {
    const result = mergeRfpTicketSnapshot(
      [ticket('A', 'analizando')],
      [ticket('B', 'analizando'), ticket('A', 'analizando')],
      0,
      new Map([['B', 1]])
    )

    expect(result.map((item) => item.ticket_id)).toEqual(['A', 'B'])
  })

  test('preserves newer SSE detail against stale HTTP data', () => {
    const result = mergeRfpTicketSnapshot(
      [ticket('A', 'analizando')],
      [ticket('A', 'analisis_completo')],
      2,
      new Map([['A', 3]])
    )

    expect(result[0].status).toBe('analisis_completo')
  })

  test('accepts newer HTTP data when SSE has not intervened', () => {
    const result = mergeRfpTicketSnapshot(
      [ticket('A', 'esperando_aprobación')],
      [ticket('A', 'analizando')],
      3,
      new Map([['A', 3]])
    )

    expect(result[0].status).toBe('esperando_aprobación')
  })

  test('does not duplicate tickets', () => {
    const result = mergeRfpTicketSnapshot(
      [ticket('A', 'analizando')],
      [ticket('A', 'analisis_completo')],
      0,
      new Map([['A', 1]])
    )

    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('analisis_completo')
  })
})
