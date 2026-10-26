import { useEffect, useState } from 'react'
import PageHeader from '../components/PageHeader'
import {
  getRFPTickets,
  getRFPDetail,
  type RFPTicket,
  type RFPDetail,
} from '../rfpApi'
import '../App.css'

export default function RFPTicketsPage() {
  const [tickets, setTickets] = useState<RFPTicket[]>([])
  const [selected, setSelected] = useState<RFPDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    setLoading(true)
    setError(null)
    try {
      setTickets(await getRFPTickets())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al consultar RFP')
    } finally {
      setLoading(false)
    }
  }

  async function openTicket(ticketId: string) {
    setDetailLoading(true)
    setError(null)
    try {
      setSelected(await getRFPDetail(ticketId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al abrir el ticket')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  return (
    <main style={{ padding: '2rem', maxWidth: 1100, margin: '0 auto' }}>
      <PageHeader
        title="TrackFlow — RFP"
        subtitle="Gestión de solicitudes y análisis departamentales"
      >
        <span />
      </PageHeader>
      <p>Solicitudes y análisis departamentales registrados en TrackFlow.</p>

      <button type="button" onClick={() => void refresh()}>
        Actualizar tickets
      </button>

      {loading && <p>Cargando tickets...</p>}
      {error && <p role="alert">{error}</p>}

      {!loading && tickets.length === 0 && !error && (
        <p>No hay tickets RFP disponibles.</p>
      )}

      <section aria-label="Listado de tickets">
        <h2>Tickets</h2>
        <ul>
          {tickets.map((ticket) => (
            <li key={ticket.ticket_id}>
              <button
                type="button"
                onClick={() => void openTicket(ticket.ticket_id)}
              >
                {ticket.client_name || 'Cliente no identificado'}
                {' — '}
                {ticket.status}
                {' — '}
                {ticket.departments_needed.join(', ') || 'Sin departamentos'}
              </button>
            </li>
          ))}
        </ul>
      </section>

      {detailLoading && <p>Cargando detalle...</p>}

      {selected && !detailLoading && (
        <section aria-label="Detalle de RFP">
          <h2>Detalle del ticket</h2>
          <p><strong>ID:</strong> {selected.ticket_id}</p>
          <p><strong>Cliente:</strong> {selected.client_name || 'No confirmado'}</p>
          <p><strong>País:</strong> {selected.client_country || 'No confirmado'}</p>
          <p><strong>Estado:</strong> {selected.status}</p>

          {selected.sections.length === 0 && (
            <p>Todavía no hay análisis departamentales disponibles.</p>
          )}

          {selected.sections.map((section) => (
            <article
              key={section.department_id}
              style={{
                border: '1px solid #ccc',
                borderRadius: 8,
                padding: '1rem',
                marginTop: '1rem',
              }}
            >
              <h3>{section.department_id}</h3>
              <p>
                <strong>Aprobación:</strong>{' '}
                {section.approval_status || 'Pendiente / no registrada'}
              </p>

              <h4>Aspectos clave</h4>
              <ul>
                {section.key_aspects.map((aspect, i) => (
                  <li key={i}>{aspect}</li>
                ))}
              </ul>

              <h4>Borrador</h4>
              <p style={{ whiteSpace: 'pre-wrap' }}>
                {section.draft_content || 'Sin borrador'}
              </p>

              <h4>Evidencia documental</h4>
              <ul>
                {(section.evaluation_results.evidence || []).map((quote, i) => (
                  <li key={i}>{quote}</li>
                ))}
              </ul>

              <h4>Información no confirmada</h4>
              <ul>
                {(section.evaluation_results.unconfirmed || []).map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </article>
          ))}
        </section>
      )}
    </main>
  )
}
