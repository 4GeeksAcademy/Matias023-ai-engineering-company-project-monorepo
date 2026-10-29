# TrackFlow — OWASP A01: evidencia previa a corrección

## Identificación

- Hallazgo: A01-RFP-001.
- Categoría: Broken Access Control.
- Componente: API FastAPI / módulo RFP.
- Estado: comportamiento inseguro reproducido en entorno simulado.
- Prioridad de investigación: alta.
- Severidad definitiva: pendiente de evaluación.

## Descripción

Dos identidades autenticadas diferentes pueden consultar
el mismo ticket RFP y descargar su documento final.

El modelo RFPTicket no contiene actualmente un
identificador explícito del propietario o ámbito autorizado.

## Endpoints evaluados

- GET /rfp/tickets/{ticket_id}
- GET /rfp/tickets/{ticket_id}/final/download

## Metodología

Pruebas HTTP mediante FastAPI TestClient.

Identidades sintéticas:
- Usuario A: ID 101.
- Usuario B: ID 202.

Persistencia:
- FakeSession.
- Datos completamente sintéticos.
- Sin conexión a PostgreSQL real.

## Resultado ANTES

| Escenario | Esperado | Obtenido |
|---|---|---|
| Usuario B consulta ticket de A | 403/404 | 200 |
| Usuario B descarga documento de A | 403/404 | 200 |

Ejecución automatizada:

`services/api/tests/test_owasp_rfp_access.py`

Resultado registrado:

`2 failed in 2.39s`

Ambos fallos corresponden a:

`AssertionError: OWASP A01: un segundo usuario autenticado accedio al recurso: HTTP 200`

## Interpretación

La prueba demuestra ausencia de diferenciación
por identidad en los endpoints evaluados.

No demuestra una filtración real de producción,
porque utiliza persistencia e identidades simuladas.

La política definitiva deberá definir:
- Acceso del creador.
- Acceso de operadores autorizados.
- Acceso de aprobadores departamentales.
- Tratamiento seguro de tickets históricos.
- Restricciones sobre generación, cierre y descarga.

## Criterios de corrección

1. Registrar un ámbito de autorización verificable.
2. Rechazar acceso no autorizado.
3. Preservar flujos legítimos de aprobación.
4. No asignar propietarios ficticios a tickets históricos.
5. Ejecutar las mismas pruebas después de corregir.
6. Verificar migración y compatibilidad con PostgreSQL.

## Estado

Evidencia ANTES registrada.

Corrección pendiente.
