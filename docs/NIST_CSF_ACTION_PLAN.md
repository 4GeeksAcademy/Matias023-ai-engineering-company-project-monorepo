# TrackFlow — Plan de acciones NIST Cybersecurity Framework 2.0

## 1. Objetivo y alcance

Este documento relaciona las seis funciones del NIST CSF 2.0
con los riesgos de los componentes de inteligencia artificial
de TrackFlow.

Referencia: briefing del proyecto y
docs/NIST_AI_SYSTEM_INVENTORY.md.

Las acciones se priorizan según riesgo.
Los responsables indicados son propuestas por rol y
requieren validación empresarial.

Los estados no deben interpretarse como certificaciones
de seguridad ni como pruebas de despliegue productivo.

## 2. Matriz de acciones priorizadas

| Función NIST | Riesgo TrackFlow | Acción concreta | Prioridad | Responsable propuesto | Estado |
|---|---|---|---|---|---|
| GOVERN | Decisiones de IA sin responsabilidad definida | Aprobar inventario, responsables y política de confirmación humana para acciones logísticas de alto impacto | P0 | CTO + responsables de Operaciones y CX | Pendiente de aprobación |
| IDENTIFY | Activos, modelos y proveedores externos no inventariados completamente | Completar inventario de modelos, servicios externos, datos B2B/B2C, credenciales y flujos entre sistemas | P1 | Responsable de IA + Seguridad | Inventario técnico inicial disponible; ampliación pendiente |
| PROTECT | Prompt injection, abuso de modelos y acciones no autorizadas | Verificar controles de entrada y salida, aplicar rate limiting y exigir autorización antes de acciones irreversibles | P0 | Backend + Seguridad + Operaciones | Controles RAG parciales comprobados; brechas pendientes |
| DETECT | Abusos de agentes no detectados oportunamente | Probar el registro estructurado del agente y definir alertas por intentos de acceso indebido y errores repetidos | P1 | Backend + Seguridad | Trazabilidad integrada; prueba y alertas pendientes |
| RESPOND | Falta de respuesta coordinada ante filtración o uso indebido de IA | Definir procedimiento de contención, revocación de credenciales, escalamiento y evaluación de notificaciones legales | P0 | Seguridad + CTO + Legal | Procedimiento específico pendiente |
| RECOVER | Recuperación incompleta tras un incidente del agente o RAG | Documentar restauración de servicios, revisión de trazas, rotación de secretos y pruebas de regresión previas a reactivar operaciones | P1 | Infraestructura + Backend + Seguridad | Plan de recuperación pendiente |

## 3. Criterios de prioridad

- P0: acción crítica para reducir riesgos relevantes de
  acceso indebido, decisiones económicas o respuesta a incidentes.
- P1: acción importante de cobertura, detección o resiliencia.
- P2: optimización posterior a los controles prioritarios.

La prioridad refleja una propuesta de tratamiento de riesgos;
no sustituye una evaluación formal aprobada por la empresa.

## 4. Evidencia técnica disponible

### Agente y autenticación

- services/api/agent_graph.py
- services/api/agent_tools.py
- services/api/routers/agent.py
- services/api/agent_mcp.py

### Trazabilidad

- services/api/agent_tracing.py
- Integración localizada en services/api/routers/agent.py

### RAG y validaciones

- scripts/rag/generate.py
- scripts/rag/tests/test_carrier_approval_guard.py
- scripts/rag/tests/test_owasp_prompt_injection.py
- scripts/rag/tests/test_safety_adversarial.py
- scripts/rag/tests/test_directional_grounding.py

Resultado registrado: 26 pruebas aprobadas en ejecución local.
No demuestra cobertura total contra prompt injection.

### Aprobación humana

- services/api/rfp_approval_service.py

Este control corresponde al proceso RFP.
No demuestra aprobación humana en operaciones logísticas.

## 5. Regulación y protección de datos

### España y Unión Europea

Considerar RGPD para el tratamiento de datos personales.
Ante una brecha, evaluar los criterios legales de notificación
a la autoridad de control y los plazos aplicables, incluido
el límite de 72 horas cuando corresponda.

### California, Estados Unidos

Considerar CCPA/CPRA y las obligaciones aplicables sobre
derechos de consumidores y protección de información personal.

Las obligaciones concretas, excepciones y procedimientos
de notificación requieren revisión del equipo legal.

## 6. Riesgos que requieren evidencia adicional

1. Autorización B2C/B2B para acceso a datos de otros clientes.
2. Rate limiting efectivo en un endpoint de IA.
3. Registro verificable de decisiones de agentes.
4. Confirmación humana en devoluciones de alto valor.
5. Confirmación humana en despachos de alto valor.
6. Autorización para cambios de carrier en tránsito.
7. Secretos de proveedores y modelos fuera del código.
8. Procedimientos de respuesta y recuperación.

## 7. Criterio de cierre

Cada acción solo puede marcarse como implementada cuando
exista evidencia técnica o documental apropiada.

No confundir una recomendación de RAG con una autorización
operativa para ejecutar cambios reales.

## 8. Próxima fase

F3: verificar controles de seguridad existentes,
implementar las correcciones necesarias dentro del alcance
del ejercicio y añadir pruebas reproducibles.
