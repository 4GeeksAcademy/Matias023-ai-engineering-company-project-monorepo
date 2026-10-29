# TrackFlow — Baseline inicial de seguridad OWASP

## 1. Información general

- Proyecto: Auditoría y Corrección de Vulnerabilidades Web.
- Marco de referencia: OWASP Top 10.
- Organización: TrackFlow Tech.
- Entorno examinado: GitHub Codespaces.
- Rama: `feature/owasp-top10-audit`.
- Commit base: `dc5ab21`.
- Fecha de referencia: 2026-10-29.
- Estado: diagnóstico inicial anterior a las correcciones.

## 2. Alcance

La auditoría contempla:

- API FastAPI y sus endpoints.
- Frontend React y portales B2B.
- Agente de soporte CX.
- LangGraph y herramientas del agente.
- RAG y recuperación documental.
- Motor de selección de carriers.
- Motor de aprobación de devoluciones.
- API de tracking.
- Dashboard de operaciones.
- Notificaciones SSE y chat WebSocket.
- Configuración Docker y controles de infraestructura.

## 3. Entorno y servicios

El diagnóstico inicial se realizó en GitHub Codespaces.

Usuario operativo observado:

- Usuario: `vscode`.
- UID: `1000`.
- Usuario no-root.

Servicios y puertos declarados en Docker Compose:

| Servicio | Puerto declarado | Observación |
|---|---|---|
| Frontend | 3000 y 3001 | Revisar exposición |
| API | 8000 | Revisar exposición |
| Redis | 6379 | Revisar publicación |
| Flower | 5555 | Revisar publicación |
| Qdrant | 6333 | Vinculado a 127.0.0.1 |

Los puertos declarados no equivalen necesariamente a
exposición pública desde Internet.

## 4. Hallazgos iniciales

| ID | Área | Evidencia inicial | Estado |
|---|---|---|---|
| SEC-001 | SSH | PermitRootLogin yes; puerto 2222 | Pendiente de evaluación |
| SEC-002 | Permisos | Directorios principales con modo 777 | Pendiente de evaluación |
| SEC-003 | Firewall | UFW y firewalld no encontrados | Control no verificado |
| SEC-004 | Redis | Publicación 6379:6379 en Compose | Exposición potencial |
| SEC-005 | API | Publicación 8000:8000 en Compose | Revisar necesidad |
| SEC-006 | Flower | Publicación 5555:5555 en Compose | Exposición potencial |
| SEC-007 | Qdrant | Puerto 6333 vinculado a localhost | Restricción favorable |
| SEC-008 | Git | Archivos .env y SQLite ignorados | Control existente |
| SEC-009 | Usuario | Ejecución bajo vscode, UID 1000 | Control existente |

Estos resultados no constituyen automáticamente
vulnerabilidades explotables.

## 5. Limitaciones de la evidencia

La inspección corresponde al entorno Codespaces.

No demuestra por sí sola la configuración de un
servidor productivo de TrackFlow.

No se han ejecutado pruebas de explotación
ni cambios de configuración.

La clasificación definitiva de riesgos dependerá
de controles compensatorios, exposición real,
impacto y pruebas reproducibles.

## 6. Categorías prioritarias

Según el briefing de TrackFlow:

- A01: Broken Access Control.
- A02: Cryptographic Failures.
- A05: Security Misconfiguration.

Se evaluarán las diez categorías OWASP Top 10
y se mantendrá un análisis separado del sistema agéntico.

## 7. Requisitos adicionales del briefing

El informe final deberá contemplar:

- Protección de información personal B2C.
- Aislamiento de información contractual B2B.
- Prompt injection contra el agente CX.
- Acciones irreversibles con confirmación humana.
- RGPD para España y la Unión Europea.
- CCPA/CPRA para California.
- Evidencias de vulnerabilidades y correcciones.

## 8. Próximos pasos

1. Completar el inventario de componentes y responsables.
2. Revisar los controles de infraestructura aplicables.
3. Auditar backend, frontend y APIs.
4. Auditar agente, herramientas y RAG.
5. Corregir vulnerabilidades críticas confirmadas.
6. Ejecutar pruebas de regresión.
7. Elaborar informe OWASP y evidencias finales.
8. Preparar Pull Request.
