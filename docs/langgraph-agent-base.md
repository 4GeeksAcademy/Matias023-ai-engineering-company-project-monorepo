# TrackFlow — Agente de Soporte con LangGraph

## Alcance

Proyecto 4Geeks: Agente de Soporte con LangGraph,
Parte 1 de 2 — Migración y Flujo del Agente.

Implementa un grafo explícito sobre el RAG existente,
sin modificar sus funciones de indexación ni recuperación.

## Arquitectura

El estado `AgentState` contiene la pregunta, fragmentos
recuperados, respuesta, abstención, motivo, fuentes y umbral.

Flujo:

START → receive → retrieve → generate → END

Rutas condicionales:

- Pregunta inválida → invalid → END.
- Evidencia insuficiente o ruta no respaldada → abstain → END.
- Evidencia disponible → generate → END.

Los nodos reutilizan `Retriever.retrieve()`,
`GeminiGenerator`, `verify_answer()` y las guardias
documentales existentes.

## Persistencia

`agent_persistence.py` utiliza SQLite mediante
`SqliteSaver` y checkpoints asociados a `thread_id`.

Existe una prueba automatizada de interrupción
controlada antes de `generate`, cierre de SQLite
y continuación de la ejecución sin repetir `retrieve`.

No se ha demostrado recuperación de un nodo que
falla a mitad de su ejecución.

## Tracing

`agent_tracing.py` registra eventos JSONL:

- run_started
- node_completed
- run_completed
- run_failed

Los eventos contienen identificadores, marcas de tiempo,
nodos, orden y motivos, sin preguntas ni respuestas completas.

## API

`POST /agent/query` reutiliza autenticación y esquemas
del endpoint RAG anterior.

`POST /rag/query` se conserva.

## Evaluaciones

Las evaluaciones se encuentran en:

`tests/pipelines/test_agent_evals.py`

Cubren orden de recuperación y generación, abstención
sin evidencia y respuesta anclada a una política
documentada de TrackFlow.

Comando:

```bash
uv run --project services/api --frozen python -m pytest tests/pipelines/test_agent_evals.py -v
```

## Evidencia

`docs/langgraph-trace-evidence.json`

La evidencia utiliza recuperador y generador simulados.
No representa una ejecución real con Qdrant o Gemini.

La traza incluye orden de nodos y un resumen seguro de
sus resultados: validación de pregunta, cantidad de
fragmentos recuperados, fuentes, longitud de respuesta
y abstención.

## Verificaciones realizadas

- Regresión automatizada: 67 pruebas aprobadas.
- Reanudación desde checkpoint SQLite: prueba automatizada aprobada.
- Distribución Wheel: construcción y contenido verificados.
- Docker: imagen backend construida e importaciones del agente aprobadas.
- FastAPI: endpoints `/agent/query` y `/rag/query` registrados en OpenAPI.
- Evidencia JSON: recorrido simulado de cinco eventos exportado.

## Limitaciones y verificaciones pendientes

- No se ha probado una consulta HTTP integral con Qdrant y Gemini reales.
- No se han comprobado permisos de un archivo SQLite creado en producción.
- No se ha realizado prueba de concurrencia.
- No se ha confirmado individualmente todo el checklist académico.
