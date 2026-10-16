import { authFetch } from '../api'
import { askRagQuestion } from './ragApi'

jest.mock('../api', () => ({
  authFetch: jest.fn(),
}))

const mockedAuthFetch =
  authFetch as jest.MockedFunction<typeof authFetch>

beforeEach(() => {
  jest.clearAllMocks()
})

test('envia pregunta mediante authFetch protegido', async () => {
  const answer = {
    answer: 'SEUR ofrece cobertura en Aragón [1].',
    abstained: false,
    reason: 'ok',
    sources: [],
    threshold: 0.54,
  }

  mockedAuthFetch.mockResolvedValue({
    ok: true,
    json: async () => answer,
  } as Response)

  const result = await askRagQuestion(
    '  ¿Qué transportista cubre Aragón?  ',
  )

  expect(result).toEqual(answer)

  expect(mockedAuthFetch).toHaveBeenCalledWith(
    '/api/rag/query',
    expect.objectContaining({
      method: 'POST',
      requireAuth: true,
      body: JSON.stringify({
        question: '¿Qué transportista cubre Aragón?',
      }),
    }),
  )
})

test('rechaza preguntas vacias sin llamar a la API', async () => {
  await expect(
    askRagQuestion('   '),
  ).rejects.toThrow('La pregunta debe tener')

  expect(mockedAuthFetch).not.toHaveBeenCalled()
})

test('rechaza preguntas demasiado largas', async () => {
  await expect(
    askRagQuestion('x'.repeat(1001)),
  ).rejects.toThrow('La pregunta debe tener')

  expect(mockedAuthFetch).not.toHaveBeenCalled()
})

test('informa cuando Gemini no esta disponible', async () => {
  mockedAuthFetch.mockResolvedValue({
    ok: false,
    status: 503,
  } as Response)

  await expect(
    askRagQuestion('¿Cuál es el SLA?'),
  ).rejects.toThrow('El asistente no está disponible')
})
