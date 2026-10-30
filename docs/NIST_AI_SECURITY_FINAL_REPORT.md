# TrackFlow — Informe de Seguridad en Sistemas de Inteligencia Artificial

## 1. Resumen ejecutivo

Proyecto académico: Prácticas Seguras en la Integración de IA en Sistemas.

Marco de referencia: NIST Cybersecurity Framework 2.0.

El objetivo de este trabajo es identificar los riesgos asociados a
los componentes de inteligencia artificial de TrackFlow, verificar
controles existentes e implementar mejoras de seguridad comprobables.

Se trabajó sobre el monorepo existente, sin reconstruir los sistemas.

Este informe refleja controles locales y evidencias reproducibles.
No constituye una certificación de seguridad ni una validación
integral de producción.

## 2. Contexto empresarial y regulatorio

El briefing empresarial describe operaciones en Zaragoza, España,
y Los Ángeles, California, Estados Unidos.

Los marcos regulatorios relevantes son:

- RGPD: protección de datos personales en España y la Unión Europea.
- CCPA/CPRA: derechos de privacidad y protección de información
  personal de consumidores de California.

Para incidentes sujetos al RGPD, debe evaluarse la obligación
de notificación a la autoridad de control competente, incluido
el plazo de 72 horas cuando corresponda.

La aplicación concreta de obligaciones legales requiere
evaluación del equipo jurídico.

## 3. Inventario de sistemas de IA

El inventario completo se encuentra en:

docs/NIST_AI_SYSTEM_INVENTORY.md

| Sistema | Riesgo principal | Responsable propuesto | Estado |
|---|---|---|---|
| Agente CX 24/7 | Acceso indebido y prompt injection | Soporte CX + CTO | Implementación identificada |
| RAG de políticas y SLA | Inyección y filtración documental | IA/RAG + CTO | Implementado; pruebas locales |
| Selección de carriers | Recomendaciones o cambios no autorizados | Operaciones Logísticas | Política RAG comprobada; motor no confirmado |
| Aprobación de devoluciones | Decisiones económicas indebidas | Devoluciones + Finanzas | Motor operativo no confirmado |
| Herramientas API/MCP | Consultas no autorizadas | API + Seguridad | Implementación identificada |
| Aprobación RFP | Decisiones sin revisión humana | Responsable RFP | Flujo de revisión identificado |

Los responsables son propuestas por rol, pendientes de aprobación
empresarial. No son designaciones oficiales.

## 4. Evaluación NIST CSF 2.0

La matriz detallada se encuentra en:

docs/NIST_CSF_ACTION_PLAN.md

| Función | Acción concreta priorizada | Prioridad | Estado |
|---|---|---|---|
| GOVERN | Aprobar responsables y política de revisión humana | P0 | Pendiente de aprobación |
| IDENTIFY | Completar inventario de modelos, proveedores y datos | P1 | Inventario inicial disponible |
| PROTECT | Validar entradas y salidas, limitar consultas y controlar acciones críticas | P0 | Rate limiting RAG verificado; controles adicionales pendientes |
| DETECT | Registrar decisiones y establecer alertas de abuso | P1 | Trazabilidad local probada; alertas pendientes |
| RESPOND | Definir contención, revocación y escalamiento ante incidentes | P0 | Procedimiento pendiente |
| RECOVER | Definir restauración, rotación y regresión antes de reactivar servicios | P1 | Plan pendiente |

## 5. Controles técnicos implementados o verificados

### 5.1 Autenticación y validación

El endpoint RAG requiere autenticación y utiliza Pydantic
para validar la longitud de las preguntas.

El agente LangGraph exige autenticación para consultar tickets
mediante herramientas de solo lectura.

### 5.2 Protección frente a prompt injection

Se ejecutaron pruebas contra instrucciones maliciosas
introducidas en documentos recuperados por el RAG.

La prueba verificó que el asistente se abstiene y no publica
el marcador insertado por el documento malicioso.

Resultado conjunto:

18 pruebas adversariales y de políticas aprobadas.

Estas pruebas no garantizan defensa universal frente
a todas las variantes de prompt injection.

### 5.3 Rate limiting

Se implementó un control para:

POST /rag/query

Características:

- Redis con operación Lua mediante EVAL.
- Contador por identificador de usuario autenticado.
- Límite predeterminado: 10 solicitudes por 60 segundos.
- HTTP 429 cuando se supera el límite.
- Encabezado Retry-After.
- HTTP 503 si Redis no está disponible.
- Bloqueo antes de ejecutar el servicio RAG.

Pruebas automatizadas:

12 pruebas aprobadas, incluyendo regresión HTTP.

Prueba funcional con Redis real:

- Solicitud 1: permitida.
- Solicitud 2: permitida.
- Solicitud 3: bloqueada.
- Clave temporal eliminada.

La prueba Redis utilizó un límite temporal de
2 solicitudes en 30 segundos.

El control no protege automáticamente /agent/query
ni otros endpoints de Gemini.

No se realizó una prueba de concurrencia real.

### 5.4 Logging y trazabilidad

El endpoint /agent/query utiliza run_traced().

Una prueba con grafo simulado verificó:

- Evento run_started.
- Tres eventos node_completed.
- Evento run_completed.
- Registro de motivos de decisión.
- Ausencia del marcador sensible.
- Ausencia de respuesta completa en el archivo de trazas.

Resultado: PASS.

No se ejecutó Gemini real para esta comprobación.

### 5.5 Gestión de credenciales

Se documentaron GEMINI_API_KEY y GEMINI_MODEL
en services/api/.env.example sin incorporar claves reales.

También se documentaron REDIS_URL,
AI_RATE_LIMIT_REQUESTS y AI_RATE_LIMIT_WINDOW.

Una búsqueda preventiva examinó 501 archivos versionados
y no encontró coincidencias con los patrones configurados
de credenciales Google, OpenAI, GitHub y AWS.

Limitación: la búsqueda no fue una auditoría integral de
secretos, archivos no versionados ni historial Git.

## 6. Aprobación humana y acciones irreversibles

El briefing exige confirmación humana para:

1. Devoluciones por encima de un umbral monetario.
2. Despachos de alto valor.
3. Cambios de carrier en tránsito.
4. Compartir información confidencial B2B entre marcas.

TrackFlow dispone de un flujo de aprobación humana RFP,
pero este corresponde a documentos y departamentos RFP.

También existen pruebas que rechazan recomendaciones
de cambios de carrier sin aprobación.

Ninguna de estas evidencias demuestra que las cuatro
operaciones logísticas anteriores estén protegidas
mediante confirmación humana en una implementación operativa.

Por tanto, estos controles permanecen pendientes de
implementación o verificación y no se declaran cumplidos.

## 7. Riesgos residuales y acciones prioritarias

| Prioridad | Riesgo pendiente | Acción recomendada |
|---|---|---|
| P0 | Acceso entre clientes B2B/B2C | Validar autorización y aislamiento en cada herramienta |
| P0 | Acciones logísticas irreversibles | Exigir confirmación humana antes de ejecutar |
| P0 | Incidentes de IA | Aprobar procedimiento de respuesta y escalamiento |
| P1 | Endpoints IA adicionales | Evaluar ampliación del rate limiting |
| P1 | Registro de anomalías | Definir alertas y retención de trazas |
| P1 | Dependencias externas | Completar inventario y revisión de proveedores |
| P1 | Recuperación | Establecer plan y pruebas de restauración |

## 8. Conclusión

TrackFlow cuenta con controles de autenticación,
validación de entradas, trazabilidad y revisión de
respuestas documentales.

Durante este ejercicio se añadió rate limiting distribuido
a POST /rag/query y se verificó su comportamiento mediante
pruebas automatizadas y una ejecución contra Redis real.

También se demostraron casos de prompt injection neutralizado
y registros estructurados del agente con componentes simulados.

Los riesgos residuales deben resolverse antes de afirmar
seguridad integral en producción.

## 9. Evidencias y archivos de referencia

- docs/NIST_AI_SYSTEM_INVENTORY.md
- docs/NIST_CSF_ACTION_PLAN.md
- services/api/ai_rate_limit.py
- services/api/routers/rag.py
- services/api/tests/test_ai_rate_limit.py
- services/api/tests/test_rag_api.py
- services/api/agent_tracing.py
- scripts/rag/tests/test_owasp_prompt_injection.py
- scripts/rag/tests/test_safety_adversarial.py
- scripts/rag/tests/test_carrier_approval_guard.py
