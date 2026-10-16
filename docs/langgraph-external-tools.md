# TrackFlow — LangGraph Parte 2: Herramientas externas

## Alcance

Se extiende el agente de la Parte 1 para distinguir
consultas documentales RAG y consultas de tickets TrackFlow.

## Herramienta real

`services/api/agent_tools.py` consulta mediante HTTP
`GET /api/incidents/{id}`.

La herramienta utiliza JWT Bearer, timeout de 5 segundos,
entrada y salida tipadas, validación de `IncidentResponse`
y manejo de respuestas 404, 401, 403, errores de conexión
y respuestas inválidas.

La herramienta es de solo lectura.

## Enrutamiento

- Ticket: receive → route → ticket_lookup → END.
- RAG: receive → route → retrieve → generate → END.
- El grafo conserva las ramas de abstención y pregunta inválida.

## Trazabilidad y seguridad

Las trazas JSONL registran nodos, orden y metadatos.
El JWT circula mediante contexto de ejecución, sin
incorporarse al estado persistido.

Una prueba automatizada comprueba que el JWT no aparezca
en checkpoints SQLite ni en trazas JSONL.

## Pruebas

El GO AUDIT seleccionado terminó con 34 pruebas aprobadas.

La integración HTTP autenticada verificó:
- Login HTTP 200.
- Listado de incidentes HTTP 200.
- Cero incidentes registrados.
- Consulta del agente HTTP 200.
- Motivo ticket_not_found y abstención correcta.

## Evidencia

`docs/langgraph-external-tools-evidence.json`

Contiene los eventos recuperados del backend Docker.
Las observaciones HTTP provienen del RTER anterior y se
identifican separadamente; no proceden del archivo JSONL.

## Limitaciones

- No se probó por HTTP la recuperación de un ticket existente.
- Las evaluaciones RAG usaron componentes simulados.
- No se confirmó ejecución integral con Qdrant y Gemini.
- Las 34 pruebas corresponden a la selección GO AUDIT,
  no a toda la suite del monorepo.
