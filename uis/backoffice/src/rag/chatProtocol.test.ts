import {
  appendStreamingToken,
  reconcileSnapshot,
  storageScope,
  type ProtocolMessage,
} from './chatProtocol'

const streaming: ProtocolMessage = {
  message_id: 'msg_1',
  role: 'assistant',
  content: 'Hola',
  status: 'streaming',
  sequence: 1,
}

describe('TrackFlow WebSocket chat protocol', () => {
  test('un snapshot reemplaza mensajes locales pendientes', () => {
    const local: ProtocolMessage[] = [{
      message_id: 'pending_1',
      role: 'user',
      content: 'Consulta',
      status: 'pending',
      sequence: 0,
    }]

    const server: ProtocolMessage[] = [{
      message_id: 'msg_real',
      role: 'user',
      content: 'Consulta',
      status: 'completed',
      sequence: 0,
    }]

    expect(reconcileSnapshot(local, server)).toEqual(server)
    expect(reconcileSnapshot(local, server)).not.toBe(server)
  })

  test('incorpora un fragmento siguiente al mensaje streaming', () => {
    expect(
      appendStreamingToken([streaming], ' mundo', 2),
    ).toEqual([{
      ...streaming,
      content: 'Hola mundo',
      sequence: 2,
    }])
  })

  test('ignora un fragmento duplicado o antiguo', () => {
    const messages = [streaming]

    expect(appendStreamingToken(messages, ' repetido', 1))
      .toBe(messages)

    expect(appendStreamingToken(messages, ' antiguo', 0))
      .toBe(messages)
  })

  test('no inventa texto cuando faltan fragmentos', () => {
    const messages = [streaming]

    expect(appendStreamingToken(messages, ' salto', 4))
      .toBe(messages)
  })

  test('no añade tokens a mensajes completados', () => {
    const completed = {
      ...streaming,
      status: 'completed',
    }

    expect(appendStreamingToken([completed], ' extra', 2))
      .toEqual([completed])
  })

  test('separa el almacenamiento por credencial', () => {
    const first = storageScope('token-usuario-a')
    const second = storageScope('token-usuario-b')

    expect(first).not.toBe(second)
    expect(storageScope('token-usuario-a')).toBe(first)
    expect(first).not.toContain('token-usuario-a')
  })
})
