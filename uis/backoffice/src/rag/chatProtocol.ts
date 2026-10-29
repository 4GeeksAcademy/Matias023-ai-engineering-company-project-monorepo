/**
 * Lógica independiente de React para el chat WebSocket.
 * El servidor sigue siendo la autoridad sobre sesiones e historial.
 */

export type ProtocolMessage = {
  message_id: string
  role: 'user' | 'assistant'
  content: string
  status: string
  sequence: number
}

/**
 * Separación local por credencial.
 * Este identificador NO sustituye la autorización del backend.
 */
export function storageScope(token: string): string {
  let hash = 2166136261

  for (let i = 0; i < token.length; i += 1) {
    hash ^= token.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }

  return (hash >>> 0).toString(16).padStart(8, '0')
}

export function reconcileSnapshot<T extends ProtocolMessage>(
  _local: T[],
  server: T[],
): T[] {
  // El snapshot es autoritativo. No conservar mensajes "pending"
  // que el servidor ya haya registrado.
  return [...server]
}

export function appendStreamingToken<T extends ProtocolMessage>(
  messages: T[],
  token: string,
  sequence: number,
): T[] {
  if (
    !token ||
    !Number.isInteger(sequence) ||
    sequence < 1
  ) {
    return messages
  }

  const last = messages[messages.length - 1]

  if (
    !last ||
    last.role !== 'assistant' ||
    last.status !== 'streaming' ||
    sequence <= last.sequence
  ) {
    return messages
  }

  // Un salto de secuencia implica pérdida de fragmentos.
  // Esperar un session_snapshot en vez de reconstruir
  // incorrectamente el mensaje.
  if (sequence !== last.sequence + 1) {
    return messages
  }

  return [
    ...messages.slice(0, -1),
    {
      ...last,
      content: last.content + token,
      sequence,
    },
  ]
}
