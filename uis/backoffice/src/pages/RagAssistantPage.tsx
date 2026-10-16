import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { askRagQuestion } from '../rag/ragApi'
import type { RagAnswer } from '../rag/ragApi'
import './RagAssistantPage.css'

const examples = [
  '¿Qué transportista ofrece mejor cobertura en Aragón rural?',
  '¿Cómo se gestionan las devoluciones internacionales?',
  '¿Quién debe aprobar los descuentos de almacenamiento?',
]

export default function RagAssistantPage() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<RagAnswer | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const activeRequest = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => activeRequest.current?.abort()
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const value = question.trim()

    if (!value || loading) return

    const controller = new AbortController()
    activeRequest.current = controller

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const answer = await askRagQuestion(
        value,
        controller.signal,
      )

      if (!controller.signal.aborted) {
        setResult(answer)
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(
          err instanceof Error
            ? err.message
            : 'No fue posible realizar la consulta.',
        )
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false)
      }

      if (activeRequest.current === controller) {
        activeRequest.current = null
      }
    }
  }

  return (
    <main className="page rag-page">
      <section className="header">
        <div>
          <p className="eyebrow">TrackFlow Knowledge Base</p>
          <h1>Asistente de conocimiento</h1>
          <p className="subtitle">
            Consulta las políticas oficiales de logística,
            devoluciones, transportistas y almacenamiento.
          </p>
        </div>
        <Link
          to="/suppliers"
          className="secondary-button nav-link"
        >
          Volver a proveedores
        </Link>
      </section>

      <section className="state-card rag-panel">
        <h2>Haz una pregunta</h2>

        <form onSubmit={(event) => { void handleSubmit(event) }}>
          <label htmlFor="rag-question">
            Pregunta sobre TrackFlow
          </label>

          <textarea
            id="rag-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={1000}
            rows={4}
            required
            disabled={loading}
            placeholder="Escribe aquí tu consulta..."
            className="rag-input"
          />

          <div className="rag-actions">
            <span className="rag-counter">
              {question.length}/1000 caracteres
            </span>

            <button
              type="submit"
              className="primary-button"
              disabled={loading || !question.trim()}
            >
              {loading ? 'Consultando...' : 'Consultar'}
            </button>
          </div>
        </form>

        <div className="rag-examples">
          <h3>Preguntas de ejemplo</h3>
          <div className="rag-example-list">
            {examples.map((example) => (
              <button
                key={example}
                type="button"
                className="secondary-button"
                onClick={() => setQuestion(example)}
                disabled={loading}
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      </section>

      {loading && (
        <section className="state-card" role="status">
          Buscando fuentes y generando una respuesta...
        </section>
      )}

      {error && (
        <section className="state-card error" role="alert">
          <h2>No se pudo completar la consulta</h2>
          <p>{error}</p>
        </section>
      )}

      {result && (
        <section
          className="state-card rag-panel"
          aria-label="Resultado del asistente"
          aria-live="polite"
        >
          <h2>
            {result.abstained
              ? 'Información insuficiente'
              : 'Respuesta'}
          </h2>

          <p className="rag-answer">{result.answer}</p>

          {result.abstained && (
            <p className="subtitle">
              El asistente no encontró respaldo suficiente
              para entregar una respuesta confiable.
            </p>
          )}

          {!result.abstained && result.sources.length > 0 && (
            <div className="rag-sources">
              <h3>Fuentes documentales</h3>

              <ol>
                {result.sources.map((source) => (
                  <li
                    key={[
                      source.citation,
                      source.source_document,
                      source.chunk_index,
                    ].join('-')}
                  >
                    <strong>
                      [{source.citation}]{' '}
                      {source.source_file
                        ?? source.source_document}
                    </strong>

                    {source.section && (
                      <span> — {source.section}</span>
                    )}

                    {source.chunk_index !== null && (
                      <span>
                        {' '}· Fragmento {source.chunk_index}
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </section>
      )}
    </main>
  )
}
