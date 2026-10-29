# TrackFlow — OWASP A01: evidencias DESPUÉS

## Estado

Correcciones implementadas y verificadas parcialmente.

**No se declara A01 completamente corregida.**

## A01-RFP-001 — Control de acceso a tickets

### Antes

- Dos identidades autenticadas podían consultar el mismo ticket
  sintético sin una restricción por propietario.
- Ambas podían obtener el documento final sintético.
- Resultado: 2 pruebas fallidas.

### Después

Se incorporaron:

- `RFPTicket.owner_uuid`.
- Registro del creador del ticket.
- Filtro de propietario en el listado.
- Autorización para consultar tickets.
- Autorización para descargar documentos.
- Autorización para generar respuestas.
- Autorización para finalizar propuestas.
- Rechazo por defecto de identidades sin UUID.
- Rechazo de tickets sin propietario verificable.

Pruebas relevantes:

`services/api/tests/test_owasp_rfp_access.py`

Las pruebas aisladas de autorización fueron aprobadas.

### Limitaciones

- La migración PostgreSQL está preparada, pero no ejecutada.
- No se ha validado el flujo completo contra PostgreSQL.
- La política de acceso compartido requiere confirmación.
- Se necesitan pruebas HTTP adicionales para otras operaciones.

## A01-RFP-002 — Aislamiento SSE

### Antes

El generador publicaba eventos sintéticos sin comprobar
la identidad del destinatario.

Resultado: 1 prueba fallida.

### Después

- Los eventos Redis incorporan `owner_uuid` internamente.
- El generador SSE filtra por UUID.
- Los eventos antiguos sin propietario se descartan.
- El formato público conserva `ticket_id` y `status`.

Pruebas relevantes:

- `test_owasp_rfp_sse_isolation.py`
- `test_rfp_sse_contract.py`
- `test_rfp_sse_http.py`

Resultado previo confirmado:

**21 pruebas aprobadas en la regresión SSE + A01.**

### Limitaciones

- Las pruebas utilizan datos sintéticos.
- Se necesitan pruebas HTTP de dos usuarios sobre el stream.
- No se ha verificado comportamiento en Redis real.

## Autorización departamental

Los controles existentes validan:

- Identidad del aprobador por departamento.
- Existencia del ticket.
- Departamento activo en el RFP.
- Sección departamental disponible.

Resultados GO F5Q:

- 9 pruebas departamentales aprobadas.
- 16 pruebas RFP + SSE aprobadas.

No se ha demostrado una asignación individual
de aprobadores a tickets.

## Migración

Archivo preparado:

`services/api/rfp_owner_migration.sql`

**Estado: NO EJECUTADA.**

Pendientes:

1. Prueba PostgreSQL aislada.
2. Revisión de tickets históricos.
3. Confirmación de política de acceso compartido.
4. Pruebas HTTP adicionales.
5. Revisión del responsable técnico.

## Conclusión

Los cambios reducen la exposición A01 observada
en las pruebas sintéticas.

No deben considerarse una certificación completa
de seguridad ni autorizar un despliegue.
