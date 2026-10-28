import { useEffect, useState } from 'react'
import PageHeader from '../components/PageHeader'
import {
  getRFPTickets,
  getRFPDetail,
  uploadRFP,
  confirmRFPCommercialMetric,
  finalizeRFP,
  downloadFinalRFP,
  regenerateRFPDepartment,
  startRFPGeneration,
  startRFPApproval,
  submitRFPApproval,
  type RFPTicket,
  type RFPDetail,
} from '../rfpApi'
import '../App.css'

const COMMERCIAL_METRICS: Record<
  string,
  { field: string; label: string; unit: string; min: number }
> = {
  warehouse: {
    field: 'monthly_capacity',
    label: 'Capacidad mensual',
    unit: 'unidades/mes',
    min: 0,
  },
  lastmile: {
    field: 'monthly_volume',
    label: 'Volumen mensual',
    unit: 'pedidos/mes',
    min: 0,
  },
  reverse: {
    field: 'returns_turnaround_hours',
    label: 'Tiempo de procesamiento de devoluciones',
    unit: 'horas',
    min: 48,
  },
}

export default function RFPTicketsPage() {
  const [tickets, setTickets] = useState<RFPTicket[]>([])
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)
  const [uploadInputKey, setUploadInputKey] = useState(0)
  const [selected, setSelected] = useState<RFPDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [approvalBusy, setApprovalBusy] = useState(false)
  const [feedback, setFeedback] = useState<Record<string, string>>({})
  const [metricValues, setMetricValues] = useState<Record<string, string>>({})
  const [metricSources, setMetricSources] = useState<Record<string, string>>({})
  const [metricNotice, setMetricNotice] = useState<Record<string, string>>({})

  async function handleGenerateRFP() {
    if (!selected || selected.status !== 'analisis_completo') return

    const ticketId = selected.ticket_id

    setApprovalBusy(true)
    setError(null)

    try {
      await startRFPGeneration(ticketId)
      await openTicket(ticketId)
      await refresh()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Error al iniciar generación RFP',
      )
    } finally {
      setApprovalBusy(false)
    }
  }

  async function handleRegeneration(departmentId: string) {
    if (!selected) return

    setApprovalBusy(true)
    setError(null)

    try {
      await regenerateRFPDepartment(
        selected.ticket_id,
        departmentId,
      )
      await openTicket(selected.ticket_id)
      await refresh()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Error al solicitar la regeneración',
      )
    } finally {
      setApprovalBusy(false)
    }
  }

  async function handleFinalizeRFP() {
    if (!selected) return

    const ticketId = selected.ticket_id
    setApprovalBusy(true)
    setError(null)

    try {
      await finalizeRFP(ticketId)
      await openTicket(ticketId)
      await refresh()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Error al finalizar la propuesta',
      )
    } finally {
      setApprovalBusy(false)
    }
  }

  async function handleDownloadRFP() {
    if (!selected) return

    setApprovalBusy(true)
    setError(null)

    try {
      const blob = await downloadFinalRFP(selected.ticket_id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')

      link.href = url
      link.download = `rfp-${selected.ticket_id}.md`

      document.body.appendChild(link)
      link.click()
      link.remove()

      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Error al descargar la propuesta',
      )
    } finally {
      setApprovalBusy(false)
    }
  }

  async function handleConfirmCommercialMetric(departmentId: string) {
    if (!selected) return

    const ticketId = selected.ticket_id
    const key = `${ticketId}:${departmentId}`
    const rawValue = (metricValues[key] || '').trim()
    const source = (metricSources[key] || '').trim()
    const value = Number(rawValue)
    const minimum = departmentId === 'reverse' ? 48 : 0

    if (
      !rawValue ||
      !Number.isFinite(value) ||
      value < minimum ||
      source.length < 8
    ) {
      setError('Ingresa un valor válido y una referencia de al menos 8 caracteres')
      return
    }

    setApprovalBusy(true)
    setError(null)

    try {
      await confirmRFPCommercialMetric(ticketId, departmentId, value, source)
      await openTicket(ticketId)
      await refresh()
      setMetricNotice((current) => ({
        ...current,
        [key]: 'Métrica confirmada y registrada',
      }))
      setMetricValues((current) => ({ ...current, [key]: '' }))
      setMetricSources((current) => ({ ...current, [key]: '' }))
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Error al confirmar la métrica comercial',
      )
    } finally {
      setApprovalBusy(false)
    }
  }

  async function handleApproval(
    departmentId: string,
    action: 'start' | 'approve' | 'request_changes',
  ) {
    if (!selected) return

    setApprovalBusy(true)
    setError(null)

    try {
      if (action === 'start') {
        await startRFPApproval(selected.ticket_id, departmentId)
      } else {
        await submitRFPApproval(
          selected.ticket_id,
          departmentId,
          action,
          feedback[departmentId],
        )
      }

      await openTicket(selected.ticket_id)
      await refresh()
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Error en aprobación RFP',
      )
    } finally {
      setApprovalBusy(false)
    }
  }


  async function handleUploadRFP() {
    if (!uploadFile) return

    if (
      !uploadFile.name.toLowerCase().endsWith('.pdf') ||
      uploadFile.size === 0 ||
      uploadFile.size > 15 * 1024 * 1024
    ) {
      setError('Selecciona un PDF válido de máximo 15 MB')
      return
    }

    setUploadBusy(true)
    setError(null)
    setUploadMessage(null)

    try {
      const result = await uploadRFP(uploadFile)
      await refresh()
      setUploadMessage(
        `PDF recibido. Ticket: ${result.ticket_id}. Estado: ${result.status}`
      )
      setUploadFile(null)
      setUploadInputKey((current) => current + 1)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'No fue posible recibir el PDF'
      )
    } finally {
      setUploadBusy(false)
    }
  }

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

      <section
        aria-label="Cargar nueva RFP"
        style={{ marginTop: '1rem', marginBottom: '1rem' }}
      >
        <h2>Subir RFP (PDF)</h2>
        <p>Selecciona una solicitud PDF de máximo 15 MB.</p>

        <input
          key={uploadInputKey}
          type="file"
          accept=".pdf,application/pdf"
          aria-label="Seleccionar archivo RFP"
          disabled={uploadBusy}
          onChange={(event) => {
            setUploadFile(event.target.files?.[0] ?? null)
            setUploadMessage(null)
          }}
        />

        <button
          type="button"
          disabled={!uploadFile || uploadBusy}
          onClick={() => void handleUploadRFP()}
        >
          {uploadBusy ? 'Enviando PDF...' : 'Subir RFP'}
        </button>

        {uploadMessage && <p role="status">{uploadMessage}</p>}
      </section>

      {detailLoading && <p>Cargando detalle...</p>}

      {selected && !detailLoading && (
        <section aria-label="Detalle de RFP">
          <h2>Detalle del ticket</h2>
          <p><strong>ID:</strong> {selected.ticket_id}</p>
          <p><strong>Cliente:</strong> {selected.client_name || 'No confirmado'}</p>
          <p><strong>País:</strong> {selected.client_country || 'No confirmado'}</p>
          <p><strong>Estado:</strong> {selected.status}</p>

          {selected.status === 'analisis_completo' && (
            <button
              type="button"
              disabled={approvalBusy}
              onClick={() => void handleGenerateRFP()}
            >
              {approvalBusy
                ? 'Iniciando generación...'
                : 'Generar propuestas departamentales'}
            </button>
          )}


          {selected.status === 'esperando_aprobación' &&
            selected.sections.length > 0 &&
            selected.sections.every(
              (section) => section.approval_status === 'approved'
            ) && (
              <button
                type="button"
                disabled={approvalBusy}
                onClick={() => void handleFinalizeRFP()}
              >
                Finalizar propuesta RFP
              </button>
            )}

          {selected.status === 'terminado' && (
            <button
              type="button"
              disabled={approvalBusy}
              onClick={() => void handleDownloadRFP()}
            >
              Descargar propuesta final
            </button>
          )}

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

              {selected.status === 'esperando_aprobación' &&
                section.draft_content &&
                (section.approval_status === null ||
                  section.approval_status === 'pending') &&
                COMMERCIAL_METRICS[section.department_id] && (
                  <div
                    aria-label={`Confirmación comercial de ${section.department_id}`}
                    style={{
                      border: '1px solid #aaa',
                      borderRadius: 8,
                      padding: '0.75rem',
                      marginTop: '0.75rem',
                    }}
                  >
                    <h4>Confirmación comercial</h4>
                    <p>
                      Registra únicamente valores comprobados por el
                      responsable del departamento. No utilices estimaciones
                      generadas por IA.
                    </p>

                    {section.evaluation_results?.verified_commercial_metrics && (
                      <p role="status">
                        Métrica registrada:{' '}
                        {String(
                          section.evaluation_results.verified_commercial_metrics[
                            COMMERCIAL_METRICS[section.department_id].field
                          ] ?? 'Sin valor'
                        )}
                        {' — '}
                        Confirmación humana existente
                      </p>
                    )}

                    <label>
                      {COMMERCIAL_METRICS[section.department_id].label}
                      {' '}
                      ({COMMERCIAL_METRICS[section.department_id].unit})
                      <input
                        type="number"
                        step="any"
                        min={COMMERCIAL_METRICS[section.department_id].min}
                        value={
                          metricValues[
                            `${selected.ticket_id}:${section.department_id}`
                          ] || ''
                        }
                        onChange={(event) => {
                          const key = `${selected.ticket_id}:${section.department_id}`
                          setMetricValues((current) => ({
                            ...current,
                            [key]: event.target.value,
                          }))
                        }}
                        disabled={approvalBusy}
                      />
                    </label>

                    <label>
                      Referencia documental de respaldo
                      <input
                        type="text"
                        maxLength={160}
                        placeholder="Referencia interna verificable"
                        value={
                          metricSources[
                            `${selected.ticket_id}:${section.department_id}`
                          ] || ''
                        }
                        onChange={(event) => {
                          const key = `${selected.ticket_id}:${section.department_id}`
                          setMetricSources((current) => ({
                            ...current,
                            [key]: event.target.value,
                          }))
                        }}
                        disabled={approvalBusy}
                      />
                    </label>

                    <button
                      type="button"
                      disabled={approvalBusy}
                      onClick={() =>
                        void handleConfirmCommercialMetric(section.department_id)
                      }
                    >
                      Confirmar métrica comercial
                    </button>

                    {metricNotice[
                      `${selected.ticket_id}:${section.department_id}`
                    ] && (
                      <p role="status">
                        {metricNotice[
                          `${selected.ticket_id}:${section.department_id}`
                        ]}
                      </p>
                    )}
                  </div>
                )}

              {section.approval_status === 'request_changes' && (
                <button
                  type="button"
                  disabled={approvalBusy}
                  onClick={() =>
                    void handleRegeneration(section.department_id)
                  }
                >
                  Regenerar propuesta
                </button>
              )}

              {section.draft_content &&
                ['en_evaluación', 'needs_human_review', 'esperando_aprobación']
                  .includes(selected.status) &&
                (section.approval_status === null ||
                  section.approval_status === 'pending') && (
                  <div aria-label={`Aprobación de ${section.department_id}`}>
                    {section.approval_status === null ? (
                      <button
                        type="button"
                        disabled={approvalBusy}
                        onClick={() => void handleApproval(section.department_id, 'start')}
                      >
                        Iniciar revisión
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          disabled={approvalBusy}
                          onClick={() => void handleApproval(section.department_id, 'approve')}
                        >
                          Aprobar sección
                        </button>
                        <textarea
                          aria-label={`Correcciones de ${section.department_id}`}
                          placeholder="Describe las correcciones necesarias"
                          value={feedback[section.department_id] || ''}
                          onChange={(event) => setFeedback((current) => ({
                            ...current,
                            [section.department_id]: event.target.value,
                          }))}
                        />
                        <button
                          type="button"
                          disabled={
                            approvalBusy ||
                            !feedback[section.department_id]?.trim()
                          }
                          onClick={() => void handleApproval(section.department_id, 'request_changes')}
                        >
                          Solicitar cambios
                        </button>
                      </>
                    )}
                  </div>
                )}

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
