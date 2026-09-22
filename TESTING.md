# Testing Plan — TrackFlow Authentication

> Documento generado como parte de la FASE 1 del ejercicio **Building Bullet-Proof Applications**.
> Este plan se crea ANTES de escribir nuevos tests y se actualizará a medida que se implementen.

---

## 1. Ejecución de pruebas backend

Todas las pruebas de backend se ejecutan desde la **raíz del monorepo** usando el siguiente comando:

```bash
uv run --directory services/api pytest
```

Para ejecutar un archivo específico (ej. el de autenticación):

```bash
uv run --directory services/api pytest tests/test_auth_users_profiles_api.py -v
```

Para ejecutar solo los tests de una clase:

```bash
uv run --directory services/api pytest tests/test_auth_users_profiles_api.py -v -k "TestAuth or TestPasswordReset"
```

> **Nota:** pytest está configurado únicamente como dependencia dev (`pytest>=9.1.1`) en `services/api/pyproject.toml`. No existe `pytest.ini` ni `conftest.py` en la raíz de `services/api/`. La fixture `client` (TestClient + TinyDB temporales) está definida inline en el propio archivo de tests.

---

## 2. Endpoints de autenticación

Los siguientes cinco endpoints están definidos en `services/api/routers/auth.py`:

| Método | Ruta                    | Función             | Descripción                                                                                |
| ------ | ----------------------- | ------------------- | ------------------------------------------------------------------------------------------ |
| POST   | `/auth/login`           | `login()`           | Autentica email+password, verifica `is_active`, devuelve JWT                               |
| GET    | `/auth/me`              | `me()`              | Devuelve `UserWithProfileResponse` del usuario autenticado (depende de `get_current_user`) |
| POST   | `/auth/forgot-password` | `forgot_password()` | Envía email con reset token; siempre 200 para evitar enumeración                           |
| POST   | `/auth/reset-password`  | `reset_password()`  | Valida token, verifica `is_active`, hashea nueva contraseña, marca token usado             |
| POST   | `/auth/change-password` | `change_password()` | Requiere autenticación; verifica contraseña actual, actualiza a nueva                      |

---

## 3. Cobertura actual por endpoint

Estado basado en la auditoría de los tests reales en `services/api/tests/test_auth_users_profiles_api.py`.

### POST `/auth/login`

| Tipo             | Escenario                            | Estado actual |
| ---------------- | ------------------------------------ | ------------- |
| **Happy path**   | Credenciales correctas → `200` + JWT | `COVERED`     |
| **Edge case**    | Usuario inactivo intenta login       | `COVERED`     |
| **Failure mode** | Contraseña incorrecta → `401`        | `COVERED`     |
| **Failure mode** | Email inexistente → `401`            | `COVERED`     |

### GET `/auth/me`

| Tipo             | Escenario                                | Estado actual |
| ---------------- | ---------------------------------------- | ------------- |
| **Happy path**   | Token válido → `200` + perfil (opcional) | `COVERED`     |
| **Edge case**    | Token expirado → `401`                   | `COVERED`     |
| **Failure mode** | Sin token → `401`                        | `COVERED`     |
| **Failure mode** | Token inválido/malformado → `401`        | `COVERED`     |

### POST `/auth/forgot-password`

| Tipo             | Escenario                                                                                   | Estado actual |
| ---------------- | ------------------------------------------------------------------------------------------- | ------------- |
| **Happy path**   | Email existente y activo → `200` + token creado                                             | `COVERED`     |
| **Edge case**    | Email inexistente → `200` (sin token, sin email)                                            | `COVERED`     |
| **Edge case**    | Usuario inactivo → `200` (no se crea token ni se envía email)                               | `COVERED`     |
| **Failure mode** | El servicio de email falla al enviar → `200` genérica + token marcado como usado/invalidado | `COVERED`     |

### POST `/auth/reset-password`

| Tipo             | Escenario                                     | Estado actual |
| ---------------- | --------------------------------------------- | ------------- |
| **Happy path**   | Token válido → `200` + contraseña actualizada | `COVERED`     |
| **Edge case**    | Token de un solo uso (reutilizado) → `400`    | `COVERED`     |
| **Edge case**    | Token expirado → `400`                        | `COVERED`     |
| **Edge case**    | Usuario inactivo con token válido → `400`     | `COVERED`     |
| **Failure mode** | Token inválido/inexistente → `400`            | `COVERED`     |

### POST `/auth/change-password`

| Tipo             | Escenario                                                           | Estado actual |
| ---------------- | ------------------------------------------------------------------- | ------------- |
| **Happy path**   | Contraseña actual correcta → `200` + nueva funciona, anterior falla | `COVERED`     |
| **Edge case**    | Nueva contraseña vacía (`""`) → `422`                               | `COVERED`     |
| **Edge case**    | Nueva contraseña solo espacios (`"   "`) → `422`                    | `COVERED`     |
| **Edge case**    | Payload sin `new_password` → `422`                                  | `COVERED`     |
| **Failure mode** | Contraseña actual incorrecta → `400`                                | `COVERED`     |
| **Failure mode** | Sin token de autenticación → `401`                                  | `COVERED`     |

> El gap de contraseña vacía/whitespace se resolvió mediante un `field_validator` en el modelo `ChangePasswordRequest` (Pydantic). Los tres casos producen `422` automático antes de llegar al endpoint.

---

## 4. Gaps detectados durante la auditoría (historial)

Los siguientes casos fueron detectados como `MISSING` durante la auditoría inicial (FASE 1).
Posteriormente se implementaron y todos han sido resueltos:

| #   | Gap                                                              | Endpoint                     | Tipo         | Estado actual |
| --- | ---------------------------------------------------------------- | ---------------------------- | ------------ | :-----------: |
| 1   | Login de usuario inactivo                                        | `POST /auth/login`           | Edge case    |  `RESUELTO`   |
| 2   | `/auth/me` con access token expirado                             | `GET /auth/me`               | Edge case    |  `RESUELTO`   |
| 3   | Reset-password para usuario inactivo                             | `POST /auth/reset-password`  | Edge case    |  `RESUELTO`   |
| 4   | Change-password con nueva contraseña vacía/inválida              | `POST /auth/change-password` | Edge case    |  `RESUELTO`   |
| 5   | El servicio de email falla al enviar el reset en forgot-password | `POST /auth/forgot-password` | Failure mode |  `RESUELTO`   |

A fecha actual no quedan gaps backend obligatorios pendientes de autenticación.

---

## 5. Lógica de seguridad a cubrir

Funciones en `services/api/security.py` que deben tener cobertura de pruebas, ya sea directa (unit tests) o indirecta (tests de integración vía endpoints):

| Función / Concepto                  | Propósito                                                | Tipo de test esperado                |
| ----------------------------------- | -------------------------------------------------------- | ------------------------------------ |
| `create_access_token(user_id)`      | Generar JWT con `sub`, `exp`, `iat`                      | Indirecto (login) / Directo unitario |
| `decode_access_token(token)`        | Decodificar y extraer `user_id` del JWT                  | Indirecto (/me) / Directo unitario   |
| **JWT válido**                      | Token correctamente firmado → acceso concedido           | Indirecto (/me)                      |
| **JWT expirado**                    | Token con `exp` pasado → `401`                           | Indirecto (/me) — **gap actual**     |
| `hash_password(plain)`              | Bcrypt hash                                              | Indirecto (creación usuario)         |
| `verify_password(plain, hashed)`    | Verificación bcrypt                                      | Indirecto (login)                    |
| `_get_secret_key()`                 | Lectura de `SECRET_KEY` del entorno                      | Unitario directo                     |
| `_get_expire_minutes()`             | Lectura de `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30)    | Unitario directo                     |
| `create_reset_token()`              | Generar token criptográfico (`secrets.token_urlsafe`)    | Indirecto / Directo                  |
| `store_reset_token(user_id)`        | Almacenar token + expiración + `used=False`              | Indirecto (forgot-password)          |
| `validate_reset_token(token)`       | Validar existencia, no usado, no expirado                | Indirecto (reset-password)           |
| **Reset token válido**              | Token existente, no usado, no expirado → ok              | `COVERED`                            |
| **Reset token expirado**            | Token con fecha pasada → `None`                          | `COVERED`                            |
| **Reset token single-use**          | Token ya usado → `None`                                  | `COVERED`                            |
| `_get_reset_token_expire_minutes()` | Lectura de `RESET_TOKEN_EXPIRE_MINUTES` (default 30)     | Unitario directo                     |
| `mark_reset_token_used(token)`      | Marcar token como usado                                  | Indirecto (reset-password)           |
| `get_current_user(token)`           | Obtener `UserResponse` desde JWT + verificar `is_active` | Indirecto (/me, change-password)     |

> No se inventan resultados de cobertura donde no existen. Los casos con `COVERED` cuentan con tests reales ya implementados (ver sección 4).

---

## 6. AI-assisted test discovery

Durante la auditoría del código fuente asistida por inteligencia artificial (FASE 1, PASO 1), se inspeccionaron los archivos `routers/auth.py`, `security.py`, `models.py`, y `tests/test_auth_users_profiles_api.py` para identificar la cobertura real de pruebas frente a la lógica de negocio implementada.

El análisis reveló los siguientes casos omitidos que no estaban cubiertos por ningún test existente:

1. **Login de usuario inactivo** — `POST /auth/login`: el código verifica `is_active` y rechaza al usuario con `401`, pero no existe ningún test que ejercite este camino.
2. **Reset-password de usuario inactivo** — `POST /auth/reset-password`: el código verifica `is_active` antes de actualizar la contraseña y rechaza con `400`, pero no hay test que cubra este escenario.
3. **Token JWT expirado para `/auth/me`** — `GET /auth/me`: no existe un test que construya un JWT con `exp` en el pasado y verifique que el endpoint responde con `401`.
4. **Fallo del servicio de email en forgot-password** — `POST /auth/forgot-password`: el código contempla `EmailConfigurationError` y `EmailServiceError`, marcando el token como usado para evitar tokens huérfanos, pero no existe ningún test que simule la falla del envío y verifique que el endpoint responde con `200` genérica y que el token queda invalidado.

Estos gaps fueron identificados comparando la lógica condicional del código fuente (`is_active`, validación de fechas) contra la matriz de tests existentes. No se afirma que estos tests existan; al contrario, se marcan explícitamente como **MISSING** y forman parte de los objetivos de implementación. **Todos ellos han sido resueltos posteriormente** en la nueva batería de tests (ver sección 4).

---

## 7. Coverage target

- **Objetivo mínimo obligatorio:** 70 % de cobertura en los módulos de autenticación (`routers/auth.py` y `security.py`).
- **Cobertura real medida:**
  - `routers/auth.py`: **96 %**
  - `security.py`: **89 %**
  - **TOTAL combinado: 92 %**
  - ✅ Se supera ampliamente el mínimo obligatorio del 70 %.
- **Comando utilizado:**
  ```bash
  uv run pytest --cov=routers.auth --cov=security --cov-report=term-missing -q
  ```
  (ejecutado desde `services/api/`)

### Resultado completo de la suite backend

La suite completa de backend arroja actualmente:

`161 passed, 1 warning`

> La cobertura se midió después de implementar todos los gaps obligatorios de backend. No hay tests pendientes de autenticación en la capa Python/FastAPI.

---

## 8. TypeScript / Jest (COMPLETADA)

El frontend (`uis/backoffice/`) contiene lógica de autenticación en:

- `src/auth/authApi.ts` — funciones API asíncronas (`login`, `register`, `getMe`, `forgotPassword`, `resetPassword`, `changePassword`) y la función helper `safeDetail()`.
- `src/auth/AuthContext.tsx` — estado de autenticación con React context y localStorage.
- `src/auth/index.ts` — barrel export de tipos y funciones.

### Configuración

Jest se configuró con los siguientes paquetes:

- `jest`
- `ts-jest`
- `@types/jest`

Archivo de configuración: `uis/backoffice/jest.config.cjs`

- Entorno: `node` (sin jsdom / React Testing Library)
- Transform: `ts-jest` con inline tsconfig (CommonJS, ES2023)
- Test match: `**/*.test.ts`
- Coverage limitado a: `src/auth/authApi.ts`

Archivo de tests: `uis/backoffice/src/auth/authApi.test.ts`

### Funciones probadas

Se probaron todas las funciones públicas exportadas de `authApi.ts`:

| Función          | Happy path | Failure mode | Fallback validado |
| ---------------- | :--------: | :----------: | :---------------: |
| `login`          |     ✅     |      ✅      |        ✅         |
| `register`       |     ✅     |      ✅      |        ✅         |
| `getMe`          |     ✅     |      ✅      |        N/A        |
| `getProfile`     |     ✅     |      ✅      |        ✅         |
| `updateProfile`  |     ✅     |      ✅      |        ✅         |
| `forgotPassword` |     ✅     |      ✅      |        ✅         |
| `changePassword` |     ✅     |      ✅      |        ✅         |
| `resetPassword`  |     ✅     |      ✅      |        ✅         |

### Estrategia de testing

- `global.fetch` mockeado — sin requests reales
- Mock inline (`mockResponse`) sin depender de DOM types
- Cada función cubre: happy path (respuesta `ok: true`) + failure mode (respuesta `ok: false`)
- Validación de mensajes de error: mensaje `detail` del backend y fallbacks genéricos (`safeDetail`)
- Sin React Testing Library ni jsdom

### Resultados de cobertura

```
npm run test:coverage -- --runInBand

Test Suites: 1 passed, 1 total
Tests:       20 passed, 20 total
Snapshots:   0 total

File        | % Stmts | % Branch | % Funcs | % Lines | Uncovered Line #s
------------|---------|----------|---------|---------|-------------------
authApi.ts  |   87.71 |      100 |   56.25 |     100 | ninguna
```

- **Statements:** 87.71 %
- **Branches:** 100 %
- **Functions:** 56.25 % (la función privada `safeDetail` no se cuenta como exportada)
- **Lines:** 100 %
- **Líneas sin cubrir:** ninguna

### Instrucciones de ejecución

```bash
# Desde uis/backoffice/

# Ejecutar tests (sin cobertura)
npm test

# Ejecutar tests con cobertura
npm run test:coverage -- --runInBand
```

---

_Documento generado el 2026-09-09, rama `feature/auth-unit-tests`._
