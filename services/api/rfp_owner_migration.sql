-- TrackFlow — OWASP A01-RFP-001
-- Migración PostgreSQL para propiedad de tickets RFP.
-- NO ejecutar sin respaldo y revisión del responsable de datos.
--
-- PRECONDICIONES:
-- 1. Aplicar en mantenimiento, antes de iniciar el backend actualizado.
-- 2. Realizar respaldo verificado.
-- 3. Probar primero en una base PostgreSQL aislada.
-- 4. Confirmar que el esquema public contiene rfp_tickets.
--
-- Los tickets históricos quedan con owner_uuid NULL.
-- NULL implica acceso denegado por la autorización implementada.

BEGIN;

ALTER TABLE public.rfp_tickets
    ADD COLUMN IF NOT EXISTS owner_uuid VARCHAR;

CREATE INDEX IF NOT EXISTS ix_rfp_tickets_owner_uuid
    ON public.rfp_tickets (owner_uuid);

COMMIT;

-- Verificación manual posterior (solo lectura):
-- SELECT column_name, data_type
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND table_name = 'rfp_tickets'
--   AND column_name = 'owner_uuid';
--
-- SELECT COUNT(*) AS historical_unowned
-- FROM public.rfp_tickets
-- WHERE owner_uuid IS NULL;
--
-- Los registros históricos requieren reclamación administrativa
-- verificada mediante un procedimiento separado.
-- No asignar automáticamente propietarios.
