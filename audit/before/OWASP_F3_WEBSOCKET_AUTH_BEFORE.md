# OWASP — F3-AUTH-001 — BEFORE

## JWT en URL WebSocket
El frontend incluía un JWT en la URL de conexión, con riesgo potencial de exposición en registros y trazas.

## Ausencia de validación Origin
GO F3T reprodujo la aceptación de un origen externo con JWT válido.

## Evidencia BEFORE
GO F3H: 2 pruebas fallidas antes de corregir el transporte JWT.
GO F3T: 7 pruebas aprobadas y 1 fallida por ausencia de rechazo de Origin.

## Alcance
Evidencia obtenida en pruebas locales. No se demostró explotación ni filtración de credenciales en producción.
