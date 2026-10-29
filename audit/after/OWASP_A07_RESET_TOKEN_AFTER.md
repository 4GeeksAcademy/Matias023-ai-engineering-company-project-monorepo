# OWASP A07 — Recuperación de contraseñas: evidencia DESPUÉS

## Hallazgo

El token de recuperación se persistía en texto original
en TinyDB.

## Evidencia ANTES

Archivo:
`audit/before/OWASP_A07_RESET_TOKEN_BEFORE.md`

Resultado:
`1 failed`, mostrando que el valor generado era igual
al valor almacenado.

## Corrección aplicada

Archivo:
`services/api/security.py`

- Generación criptográfica del token original.
- Persistencia de su digest SHA-256.
- Búsqueda mediante digest para validación y consumo.
- Contraseñas de usuarios protegidas mediante bcrypt.

## Verificaciones realizadas

GO F5U-B:
- 2 pruebas específicas aprobadas.
- 44 pruebas de autenticación aprobadas.

GO F5W-B:
- 2 pruebas específicas aprobadas.
- 44 pruebas de autenticación aprobadas.

Cobertura:
- Almacenamiento sin token original.
- Recuperación con token válido.
- Rechazo de reutilización secuencial.
- Rechazo por expiración.
- Rechazo de usuario desactivado.

## Compatibilidad

Los tokens emitidos antes de la corrección no pueden
validarse mediante el nuevo digest. Se requiere emitir
un nuevo token de recuperación.

## Limitaciones pendientes

- No se ha verificado la atomicidad del consumo ante
  solicitudes simultáneas.
- TinyDB no garantiza por sí sola una transacción que
  abarque validar, cambiar contraseña y consumir token.
- No se ha probado despliegue ni correo real.
- La revisión de limitación de intentos sigue pendiente.
- Los JWT ya emitidos no se invalidan necesariamente
  al cambiar la contraseña.

## Estado

Corrección de almacenamiento **verificada localmente**.

**A07 no está completamente cerrada.**
