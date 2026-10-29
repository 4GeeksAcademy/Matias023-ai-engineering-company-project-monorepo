# F4 — Seguridad de agentes, MCP, memoria y RAG

## Resumen

Auditoría local de seguridad de los componentes
de inteligencia artificial de TrackFlow.

## 1. MCP y herramientas

GO F4E:

- 45 pruebas aprobadas.
- Identidades MCP.
- Autorización federada.
- Scopes.
- Herramientas del agente.
- Endpoint del agente.

## 2. Memoria y RAG

GO F4F:

- 8 pruebas de memoria aprobadas.
- 16 pruebas adversariales y de fundamentación aprobadas.
- 10 pruebas de generación RAG aprobadas.

Total GO F4F: 34 pruebas aprobadas.

## 3. F4-RAG-001

Problema reproducido:

Un documento sintético contenía instrucciones
dirigidas al asistente y un generador simulado
producía una respuesta contaminada.

GO F4J:

- 1 prueba fallida ANTES.

Corrección:

- Detección conservadora de un patrón explícito
  de instrucciones no confiables.
- Abstención antes de generar contenido.
- Protección aplicada a RAGService y LangGraph.

GO F4K:

- 1 prueba adversarial aprobada.
- 26 pruebas RAG aprobadas.
- 6 pruebas LangGraph aprobadas.

Estado: mitigación parcial verificada localmente.

## 4. F4-STREAM-001

Problemas reproducidos:

- Publicación de contenido antes de validar.
- Posibilidad de liberar tokens diferentes de
  la respuesta final aprobada.

Evidencias ANTES:

- GO F4N: 1 failed.
- GO F4Q: 1 failed.

Correcciones:

- Retención de tokens provisionales.
- Liberación únicamente después de aprobación.
- Comparación exacta entre tokens acumulados
  y respuesta final aprobada.
- Descarte de tokens no coincidentes.

GO F4P:

- 8 pruebas aprobadas.

GO F4R:

- 3 pruebas del puente aprobadas.
- 6 pruebas WebSocket/LangGraph aprobadas.
- 27 pruebas RAG aprobadas.

GO F4T:

- Prueba integrada WebSocket + puente real aprobada.
- Regresión de 9 casos aprobada.

La prueba integrada utilizó LangGraph simulado,
el puente real y el WebSocket de FastAPI.

Estado: mitigación verificada en pruebas locales.

## 5. Limitaciones y pendientes

- No se ejecutaron pruebas con Gemini real.
- No se comprobó el comportamiento en producción.
- La detección de prompt injection cubre
  patrones específicos y no todos los ataques.
- Es necesario evaluar posibles falsos positivos
  del detector de instrucciones.
- El streaming retiene tokens hasta la validación,
  con impacto en la entrega progresiva.
- No se ha demostrado una filtración real de datos.
- Correcciones incluidas en el commit `61cb5ee` y publicadas en el Pull Request #31.
- Las restantes categorías OWASP deben revisarse
  en el contexto de la auditoría general.

## 6. Conclusión

Las pruebas locales previstas para F4 finalizaron
satisfactoriamente, con mitigaciones específicas
y limitaciones explícitamente documentadas.

La evidencia no equivale a una certificación
general de seguridad de TrackFlow.
