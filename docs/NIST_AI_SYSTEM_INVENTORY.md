# TrackFlow — Inventario de sistemas de inteligencia artificial

## Alcance

Proyecto: Prácticas Seguras en la Integración de IA en Sistemas.

Referencia empresarial: briefing TrackFlow proporcionado para el ejercicio.

Este inventario diferencia los sistemas descritos en el briefing
de los componentes identificados en el código del monorepo.

Los responsables indicados por rol son propuestas para revisión
empresarial; no constituyen asignaciones oficiales confirmadas.

## 1. Inventario

| Sistema | Finalidad | Evidencia técnica | Riesgo principal | Responsable propuesto | Estado |
|---|---|---|---|---|---|
| Agente CX 24/7 | Consultas de soporte y seguimiento | services/api/agent_graph.py; services/api/routers/agent.py | Acceso indebido a datos de otros clientes; prompt injection | Responsable de Soporte CX + CTO | Implementación identificada |
| RAG de políticas y SLA | Responder consultas documentales fundamentadas | scripts/rag/generate.py; services/api/routers/rag.py | Inyección desde documentos; filtración de información B2B | Responsable de IA/RAG + CTO | Implementación identificada; pruebas locales satisfactorias |
| Selección de carriers | Recomendar transportista según reglas operativas | Política y pruebas en scripts/rag/tests/test_carrier_approval_guard.py | Recomendaciones no autorizadas; acciones excesivas | Responsable de Operaciones Logísticas | Motor operativo no confirmado |
| Aprobación automática de devoluciones | Evaluar devoluciones mediante reglas | Referencias documentales en scripts/rag/generate.py | Aprobación indebida con impacto económico | Responsable de Devoluciones + Finanzas | Motor operativo no confirmado |
| Herramientas de consulta de incidentes | Consultar tickets mediante API o MCP | services/api/agent_tools.py; services/api/agent_mcp.py | Acceso no autorizado a incidentes | Responsable de API/Seguridad | Implementación identificada |
| Aprobación humana RFP | Revisar decisiones de departamentos | services/api/rfp_approval_service.py | Aprobaciones sin control humano | Responsable del proceso RFP | Flujo identificado; distinto de devoluciones logísticas |

## 2. Controles observados

- Autenticación en el endpoint /agent/query.
- Validación de longitud y tipo de preguntas en el agente.
- Herramienta de consulta de incidentes de solo lectura.
- Integración de trazabilidad mediante run_traced().
- Validaciones de respuestas RAG y política de carriers.
- Flujo de aprobación humana en el proceso RFP.

Estos hallazgos son observaciones de código.
No equivalen a una certificación integral de seguridad.

## 3. Evidencia de pruebas

Ejecutadas en la rama feature/nist-security-practices:

- scripts/rag/tests/test_carrier_approval_guard.py
- scripts/rag/tests/test_owasp_prompt_injection.py
- scripts/rag/tests/test_safety_adversarial.py
- scripts/rag/tests/test_directional_grounding.py

Resultado conjunto: 26 passed in 11.71s.

## 4. Brechas pendientes de verificación

1. Rate limiting efectivo en un endpoint que invoque modelos.
2. Evidencia reproducible de registros de decisiones del agente.
3. Confirmación humana obligatoria para devoluciones de alto valor.
4. Confirmación humana para despachos de alto valor.
5. Control de cambios de carrier en tránsito.
6. Aislamiento B2B/B2C en todas las herramientas aplicables.
7. Inventario de proveedores/modelos externos y sus credenciales.
8. Aprobación empresarial de los responsables propuestos.

## 5. Contexto normativo

El briefing identifica operaciones en Zaragoza (España)
y Los Ángeles (California, Estados Unidos).

Marcos relevantes a evaluar:
- RGPD (Unión Europea / España).
- CCPA/CPRA (California).

La aplicabilidad específica y las obligaciones de cada
tratamiento deberán confirmarse con responsables legales.

## 6. Próximo paso

Relacionar estos activos y brechas con las seis funciones del
NIST Cybersecurity Framework:

Govern, Identify, Protect, Detect, Respond y Recover.
