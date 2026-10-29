# TrackFlow — Endurecimiento inicial de infraestructura

## Alcance

Proyecto OWASP Top 10.

Entorno de referencia: GitHub Codespaces.

Rama: `feature/owasp-top10-audit`.

Este informe distingue las configuraciones del repositorio
de los controles propios del entorno administrado.

## Hallazgo SEC-004 — Redis

Antes:

`6379:6379`

Después:

`127.0.0.1:6379:6379`

Resultado: exposición del puerto restringida a localhost
en la configuración Docker Compose.

Estado: corrección aplicada y validada estáticamente.

Pendiente: validación dinámica del servicio recreado.

## Hallazgo SEC-006 — Flower

Antes:

`5555:5555`

Después:

`127.0.0.1:5555:5555`

Resultado: exposición del puerto restringida a localhost.

Estado: corrección aplicada y validada estáticamente.

Pendiente: validación dinámica del servicio recreado.

## Servicios conservados

- Backend FastAPI: puerto 8000.
- Interfaces: puertos 3000 y 3001.
- Qdrant: vinculado a localhost en puerto 6333.

## Hallazgo SEC-001 — SSH

Codespaces utiliza SSH en el puerto 2222.

Se observó `PermitRootLogin yes` en la configuración.

No se ha demostrado inicio de sesión root.

No se modificó SSH para evitar afectar el entorno
administrado.

Recomendación para despliegues administrados:
restringir login root y utilizar autenticación por claves.

## Hallazgo SEC-002 — Permisos

Se identificaron directorios con permisos 777 y
`docker-compose.yml` con permisos 666.

Las bases SQLite y `.env` presentan permisos 600.

Estado: pendiente de corrección o justificación
según el modelo de despliegue.

No se aplicaron cambios globales de permisos.

## Hallazgo SEC-003 — Firewall

No se encontraron las herramientas locales habituales.

Esto no demuestra ausencia de filtrado de red.

Estado: verificación pendiente en infraestructura
administrada de despliegue.

## Clasificación

Los cambios en Redis y Flower corresponden al
endurecimiento de configuración (OWASP A05).

No se declara vulnerabilidad explotada ni exposición
pública demostrada.

## Verificación

- `docker compose config --quiet`: PASS.
- Redis restringido a 127.0.0.1:6379: PASS.
- Flower restringido a 127.0.0.1:5555: PASS.
- Integridad Git: `git diff --cached --check` aprobado antes del commit `61cb5ee`; publicación realizada mediante PR #31.

## Pendientes

- Validar comportamiento dinámico al recrear servicios.
- Evaluar permisos del workspace.
- Documentar política de puertos del servidor objetivo.
- Continuar auditoría OWASP de aplicaciones.

## Verificación posterior de permisos — GO F2F

Se aplicaron permisos restrictivos a recursos seleccionados
del Codespace, sin utilizar `sudo` ni modificar SSH.

| Recurso | Antes | Después | Estado |
|---|---|---|---|
| `docker-compose.yml` | 666 | 644 | Verificado |
| `services/api/` | 777 | 755 | Verificado |
| `services/api/data/` | 777 | 755 | Verificado |
| `audit/` | 777 | 755 | Verificado |
| `audit/before/` | 777 | 755 | Verificado |
| `audit/after/` | 777 | 755 | Verificado |
| `docs/` | 777 | 755 | Verificado |
| `infra/` | 777 | 755 | Verificado |

Los archivos `.env`, `chat_sessions.sqlite3`,
`agent_checkpoints.sqlite3` y `agent_memory.sqlite3`
conservaron permisos `600`.

**Alcance:** corrección local en GitHub Codespaces.

Los permisos Unix de directorios no quedan reproducidos
automáticamente al clonar el repositorio mediante Git.
Se requiere aplicar una política equivalente en el
entorno de despliegue correspondiente.

## Estado de cierre de infraestructura

- Redis: restricción a localhost validada en Compose.
- Flower: restricción a localhost validada en Compose.
- Usuario operativo no-root: verificado.
- Archivos sensibles: permisos restrictivos verificados.
- Directorios seleccionados: permisos corregidos localmente.
- SSH: configuración efectiva y bloqueo de root no verificados.
- Firewall: política del entorno de despliegue no verificada.
- Redis/Flower: validación dinámica tras recreación pendiente.

**Conclusión:** endurecimiento parcial aplicado y
documentado; no equivale a certificación de seguridad
de un servidor de producción.
