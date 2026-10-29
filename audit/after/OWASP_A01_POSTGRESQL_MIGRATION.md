# OWASP A01 — Migración PostgreSQL de propiedad RFP

## Objetivo

Habilitar `RFPTicket.owner_uuid` en tablas PostgreSQL existentes.

## Artefacto

`services/api/rfp_owner_migration.sql`

## Estado

**Preparada. NO ejecutada ni validada contra PostgreSQL.**

El entorno de Codespaces inspeccionado utiliza SQLite.
No se verificó una conexión PostgreSQL activa.

## Política de seguridad

- Nuevos tickets: creador autenticado identificado por UUID.
- Tickets históricos: `owner_uuid = NULL`.
- Sin propietario verificable: acceso denegado.
- No se realiza asignación automática de registros históricos.
- No se conceden excepciones generales a usuarios `admin` o `manager`.

## Procedimiento previo a implementación

1. Obtener aprobación del responsable técnico y de datos.
2. Identificar la instancia PostgreSQL correcta.
3. Crear y verificar un respaldo.
4. Probar la migración sobre una copia aislada.
5. Verificar columnas, índice y tickets históricos.
6. Planificar el despliegue del backend junto con la migración.
7. Confirmar los accesos legítimos y las reglas de colaboración.

## Limitaciones y pendientes

La migración SQL no se ejecuta automáticamente con
`SQLModel.metadata.create_all()`.

Falta probar la migración en PostgreSQL real y validar el
comportamiento completo de la aplicación.

Las operaciones departamentales y el flujo de notificaciones
deben conservar sus autorizaciones explícitas.

**No declarar el hallazgo cerrado ni desplegar hasta verificarlo.**
