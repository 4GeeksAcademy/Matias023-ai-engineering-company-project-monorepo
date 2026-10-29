# OWASP A01-RFP-002 — SSE: evidencia ANTES

## Hallazgo

El generador SSE emitía identificadores de tickets sin comprobar el propietario.

## Prueba previa

`services/api/tests/test_owasp_rfp_sse_isolation.py`

Resultado: **1 failed in 0.21s**.

## Alcance

Prueba completamente sintética. No demuestra exposición real en producción.

## Corrección

Publicar propietario interno y filtrar eventos por UUID del usuario autenticado.
