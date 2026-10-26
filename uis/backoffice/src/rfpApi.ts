import { authFetch } from './api'

export type RFPTicket = {
  ticket_id: string
  status: string
  created_at: string
  client_name: string | null
  departments_needed: string[]
}

export type RFPSection = {
  department_id: string
  key_aspects: string[]
  draft_content: string | null
  evaluation_results: {
    evidence?: string[]
    unconfirmed?: string[]
  }
  approval_status: string | null
}

export type RFPDetail = RFPTicket & {
  client_country: string | null
  sections: RFPSection[]
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`RFP API error: HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export async function getRFPTickets(): Promise<RFPTicket[]> {
  const response = await authFetch('/api/rfp/tickets')
  const data = await readJson<{ tickets: RFPTicket[] }>(response)
  return data.tickets
}

export async function getRFPDetail(
  ticketId: string,
): Promise<RFPDetail> {
  const response = await authFetch(
    `/api/rfp/tickets/${encodeURIComponent(ticketId)}`,
  )
  return readJson<RFPDetail>(response)
}
