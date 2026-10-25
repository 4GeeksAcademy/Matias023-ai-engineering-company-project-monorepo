# TrackFlow MCP

Servidor MCP independiente para conectar agentes de IA con las
herramientas empresariales existentes de TrackFlow.

## Funcionalidades implementadas

Seis herramientas FastMCP:

| Herramienta | Scope requerido |
|---|---|
| `get_incident` | `incidents:read` |
| `list_incidents` | `incidents:read` |
| `create_incident` | `incidents:write` |
| `update_incident_status` | `incidents:write` |
| `list_products` | `inventory:read` |
| `get_product` | `inventory:read` |

## Seguridad

El servidor MCP utiliza autenticación OAuth basada en JWT RS256.

Se verifican la firma criptográfica, el issuer, la audiencia,
la expiración y los scopes requeridos.

El backend TrackFlow verifica independientemente los JWT externos
y exige una vinculación explícita entre el subject de Keycloak
y un usuario empresarial activo.

Los permisos efectivos se limitan mediante `granted_scopes`.
La escritura de incidentes exige además un rol `admin` o `manager`.

La configuración OAuth requiere:

- `MCP_OAUTH_ISSUER`
- `MCP_OAUTH_AUDIENCE`
- `MCP_OAUTH_JWKS_URI`
- `MCP_PUBLIC_BASE_URL`

La configuración pública requiere HTTPS. El HTTP local para issuer
y JWKS solo está permitido en desarrollo con
`APP_ENV=development` y `MCP_ALLOW_LOCAL_HTTP_OIDC=1`.

No publicar el servidor sin configurar y verificar su autenticación.

## Integración con LangGraph

La API incorpora un adaptador MCP opcional.

Para seleccionar este transporte:

`TRACKFLOW_AGENT_TOOL_TRANSPORT=mcp`

La integración conserva el transporte original cuando no se
habilita explícitamente MCP.

## Pruebas verificadas

- Backend MCP: 22 pruebas aprobadas.
- LangGraph: 23 pruebas aprobadas.
- Seguridad FastMCP: 6 pruebas aprobadas.
- Total de estos conjuntos: 51 pruebas aprobadas.
- OAuth Authorization Code con PKCE: validado con Keycloak.
- Firma RS256, issuer, audiencia y scope: validados.
- GET /api/incidents con JWT OAuth real: HTTP 200.
- POST /api/incidents sin scope de escritura: HTTP 401.

Las pruebas automatizadas incluyen mocks y datos aislados.
No equivalen a una validación de producción ni demuestran un flujo
completo de conversación con un servidor MCP remoto desplegado.

## Estado

Implementación y pruebas descritas anteriormente completadas.
Despliegue productivo y validación integral remota no acreditados.
