# F4-STREAM-001 — Exposición de contenido provisional

## Componente

TrackFlow — Agente LangGraph / WebSocket.

## Evidencia ANTES

### GO F4N

Prueba:

`test_chat_agent_rejected_answer_is_reconciled`

Resultado:

- 1 failed.
- 1 deselected.

El WebSocket transmitía contenido provisional que
posteriormente era rechazado por el agente.

La prueba utilizó un agente simulado.

### GO F4Q

Prueba:

`test_no_publica_tokens_distintos_de_respuesta_validada`

Resultado:

- 1 failed.
- 2 deselected.

Se demostró que el puente podía liberar tokens
diferentes del contenido final aprobado.

## Impacto demostrado

Exposición sintética de contenido no validado
a través del contrato de streaming.

No se demostró filtración de datos reales,
credenciales ni acceso a sistemas externos.

## Limitaciones

La reproducción se realizó mediante pruebas
automatizadas locales, no en producción.
