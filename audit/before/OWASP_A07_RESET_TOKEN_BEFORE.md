# OWASP A07 — Token de recuperación persistido en texto original

## Estado

Hallazgo reproducido mediante prueba unitaria con almacenamiento simulado.

## Archivo afectado

`services/api/security.py`

## Prueba ANTES

`services/api/tests/test_owasp_reset_token_storage.py`

## Comportamiento observado

`store_reset_token()` devuelve un token de recuperación
y almacena ese mismo valor en el registro de persistencia.

La prueba exige que el token original no aparezca entre los
valores persistidos.

**Resultado esperado ANTES: 1 prueba fallida.**

## Riesgo

La lectura no autorizada del almacenamiento podría exponer
tokens de recuperación que todavía sean válidos.

La explotación depende de conseguir acceso a ese almacenamiento.

## Límites de la evidencia

- Se utilizó almacenamiento simulado.
- No se accedió a TinyDB real.
- No se utilizaron credenciales ni cuentas reales.
- No se demuestra acceso no autorizado a la base de datos.
- No se ha probado todavía la concurrencia del consumo.
- La corrección y las pruebas DESPUÉS están pendientes.

## Corrección candidata

Persistir un digest criptográfico del token en lugar
del valor original, manteniendo su caducidad y uso único.

La implementación debe preservar los contratos existentes.
