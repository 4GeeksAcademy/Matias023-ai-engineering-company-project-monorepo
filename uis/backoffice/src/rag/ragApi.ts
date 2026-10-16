import { authFetch } from '../api'

export type RagSource = {
  citation: number
  source_document: string
  source_file: string | null
  section: string | null
  chunk_index: number | null
  score: number | null
}

export type RagAnswer = {
  answer: string
  abstained: boolean
  reason: string
  sources: RagSource[]
  threshold: number
}

export async function askRagQuestion(
  question: string,
  signal?: AbortSignal,
): Promise<RagAnswer> {
  const value = question.trim()

  if (!value || value.length > 1000) {
    throw new Error('La pregunta debe tener entre 1 y 1000 caracteres.')
  }

  const response = await authFetch('/api/rag/query', {
    method: 'POST',
    requireAuth: true,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question: value }),
    signal,
  })

  if (!response.ok) {
    if (response.status === 503) {
      throw new Error(
        'El asistente no está disponible. Inténtalo más tarde.',
      )
    }

    if (response.status === 422) {
      throw new Error('La pregunta enviada no es válida.')
    }

    throw new Error(
      `No se pudo consultar el asistente (HTTP ${response.status}).`,
    )
  }

  return (await response.json()) as RagAnswer
}
