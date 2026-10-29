# TrackFlow — Inventario de sistemas de IA

## 1. Contexto

Proyecto: Auditoría y Corrección de Vulnerabilidades Web.

Organización: TrackFlow Tech.

Entorno inspeccionado: GitHub Codespaces.

Rama: `feature/owasp-top10-audit`.

Referencia: briefing oficial TrackFlow.

Este inventario representa el estado previo a las
correcciones de seguridad.

## 2. Sistemas de IA

| ID | Sistema | Función | Implementación identificada | Responsable | Riesgo |
|---|---|---|---|---|---|
| AI-01 | Agente CX 24/7 | Consultas de tracking y devoluciones | `services/api/agent_graph.py`, `agent_tools.py`, `routers/agent.py` | Por asignar | Prompt injection y acceso indebido |
| AI-02 | Motor de selección de carriers | Recomendar transportista | Existe `scripts/rag/tests/test_carrier_approval_guard.py`; implementación completa por verificar | Por asignar | Excessive agency |
| AI-03 | RAG de políticas y SLA | Respuestas documentales | `services/api/routers/rag.py`, `scripts/rag/` | Por asignar | Filtración entre clientes |
| AI-04 | Motor de aprobación de devoluciones | Aprobar o rechazar devoluciones | Implementación específica no confirmada | Por asignar | Acción económica no autorizada |

Los cuatro sistemas proceden del briefing oficial.

No se asume que todos estén implementados completamente
solo porque aparezcan en el briefing.

## 3. Componentes adicionales relacionados

| Componente | Ubicación principal | Riesgo |
|---|---|---|
| API FastAPI | `services/api/routers/` | Control de acceso |
| Autenticación | `services/api/routers/auth.py` | Gestión de credenciales |
| Usuarios | `services/api/routers/users.py` | Escalada de privilegios |
| Inventario | `services/api/routers/inventory.py` | Acceso por recurso |
| Proveedores | `services/api/routers/suppliers.py` | Datos comerciales |
| Incidentes | `services/api/routers/incidents.py` | Información operativa |
| Chat WebSocket | `services/api/routers/chat_websocket.py` | Credenciales y sesiones |
| Notificaciones SSE | `services/api/routers/rfp_intake.py` | Acceso a eventos |
| Backoffice | `uis/backoffice/` | Sesiones y datos |
| Web pública | `uis/website/` | Configuración y exposición |

## 4. Controles identificados

Durante el inventario se localizaron:

- Autenticación mediante `get_current_user`.
- Autenticación JWT local.
- Integración de autenticación federada.
- Controles específicos de aprobación departamental RFP.
- Aislamiento de sesiones WebSocket.
- Pruebas automatizadas relacionadas con autorización.
- Exclusión de archivos `.env` y SQLite en Git.

La existencia de estos controles no demuestra que
todos los endpoints sean seguros.

## 5. Riesgos prioritarios

### A01 — Broken Access Control

Verificar que un cliente no pueda consultar pedidos,
direcciones o información de otra marca.

### A02 — Cryptographic Failures

Revisar protección de tokens, secretos e integraciones.

### A05 — Security Misconfiguration

Revisar permisos de herramientas, infraestructura
y acciones automatizadas.

## 6. Pruebas específicas del agente

- Prompt injection desde mensajes del cliente.
- Prompt injection desde documentos o notas externas.
- Intentos de acceso a recursos ajenos.
- Intentos de ejecutar acciones fuera de las reglas.
- Confirmación humana para operaciones irreversibles.

Todas las pruebas deberán ejecutarse en un entorno
controlado, utilizando datos sintéticos.

## 7. Responsables

El repositorio inspeccionado no permitió identificar
responsables individuales verificables por sistema.

**Estado:** pendiente de asignación formal.

Esta asignación deberá resolverse antes de considerar
completado el requisito de responsables del informe NIST.

## 8. Marco regulatorio

- RGPD: España y Unión Europea.
- CCPA/CPRA: California, Estados Unidos.

La evaluación de cumplimiento normativo requiere
analizar tratamientos de datos, roles y obligaciones
concretas; esta sección identifica únicamente
los marcos aplicables según el briefing.

## 9. Estado

Inventario inicial documentado.

Pendiente: confirmar implementación de carriers
y aprobaciones automáticas de devoluciones.

Pendiente: asignación formal de responsables.
