# FRONTEND PERFORMANCE — AFTER AUDIT REPORT

Fecha: 2026-10-03  
Rama: `feat/frontend-performance-audit`  
Código de aplicación modificado durante esta medición: no.

## Entorno y metodología

- Lighthouse 12.8.2, Chrome for Testing 154.0.8037.57, `throttling-method=simulate`.
- Se conservaron localhost, servidores Vite dev, ruta, viewport y perfiles del BEFORE: website Desktop 1350×940; website Mobile 412×823; backoffice `/suppliers` Desktop 1350×940.
- Website usó Chrome headless con perfil nuevo por ejecución. Para el backoffice se creó una cuenta temporal por la API normal, se confirmó autenticación y título `Supplier Directory` con 15 filas, se capturó la página y se limpió la caché de Chrome antes del Lighthouse. `--disable-storage-reset` preservó solo la sesión para que Lighthouse no midiera el login.
- Se hizo una ejecución por celda con throttling simulado. Los resultados no son datos de campo. El backoffice se midió cold-cache, como el baseline final.
- JSON/HTML de las tres celdas, trazas disponibles y capturas separadas están en esta carpeta. No se generó traza/DevTools log autenticado para no guardar cabeceras de autorización. Los 14 archivos bajo `audit/before/` conservaron sus SHA-256.

## Website `/` — Desktop

| Métrica        |      BEFORE |       AFTER | Delta / lectura                                   |
| -------------- | ----------: | ----------: | ------------------------------------------------- |
| Performance    |          69 |          71 | +2, mejora observada                              |
| Accessibility  |         100 |         100 | 0, sin cambio                                     |
| Best Practices |          96 |          96 | 0, sin cambio                                     |
| SEO            |          82 |         100 | +18, mejora observada                             |
| FCP            |       2.0 s |       2.0 s | sin cambio mostrado                               |
| LCP            |       3.5 s |       3.4 s | −0.1 s, mejora pequeña; variabilidad NOT VERIFIED |
| TBT            |        0 ms |        0 ms | sin cambio                                        |
| CLS            |           0 |           0 | sin cambio                                        |
| Speed Index    |       2.1 s |       2.0 s | −0.1 s, diferencia pequeña                        |
| Request count  |          13 |          13 | sin cambio                                        |
| Transferidos   | 3,691,114 B | 3,691,274 B | +160 B, diferencia compatible con variación       |

## Website `/` — Mobile

| Métrica        |      BEFORE |       AFTER | Delta / lectura                                       |
| -------------- | ----------: | ----------: | ----------------------------------------------------- |
| Performance    |          56 |          56 | 0, sin cambio                                         |
| Accessibility  |         100 |         100 | 0, sin cambio                                         |
| Best Practices |          96 |          96 | 0, sin cambio                                         |
| SEO            |          82 |         100 | +18, mejora observada                                 |
| FCP            |      10.9 s |      10.8 s | −0.1 s, diferencia pequeña; variabilidad NOT VERIFIED |
| LCP            |      19.7 s |      19.6 s | −0.1 s, diferencia pequeña; variabilidad NOT VERIFIED |
| TBT            |       10 ms |       10 ms | sin cambio mostrado                                   |
| CLS            |           0 |           0 | sin cambio                                            |
| Speed Index    |      10.9 s |      10.8 s | −0.1 s, diferencia pequeña                            |
| Request count  |          13 |          13 | sin cambio                                            |
| Transferidos   | 3,691,114 B | 3,691,274 B | +160 B, diferencia compatible con variación           |

## Backoffice `/suppliers` — Desktop

| Métrica        |      BEFORE |       AFTER | Delta / lectura                                                        |
| -------------- | ----------: | ----------: | ---------------------------------------------------------------------- |
| Performance    |          61 |          59 | −2, regresión medida; variabilidad con una ejecución NOT VERIFIED      |
| Accessibility  |          86 |         100 | +14, mejora observada                                                  |
| Best Practices |         100 |         100 | 0, sin cambio                                                          |
| SEO            |          82 |          63 | −19; consecuencia intencional del `noindex` de una herramienta interna |
| FCP            |       2.6 s |       2.4 s | −0.2 s, mejora observada en este run                                   |
| LCP            |       4.8 s |       4.7 s | −0.1 s, diferencia pequeña                                             |
| TBT            |       40 ms |       60 ms | +20 ms, regresión medida; variabilidad NOT VERIFIED                    |
| CLS            |       0.002 |       0.109 | +0.107, regresión medida; causa exacta NOT VERIFIED                    |
| Speed Index    |       2.9 s |       2.8 s | −0.1 s, diferencia pequeña                                             |
| Request count  |          39 |          25 | −14 requests                                                           |
| Transferidos   | 5,278,677 B | 4,973,519 B | −305,158 B (−5.8%)                                                     |

## Evaluación de Pass 1

- **Performance: MIXED.** Website Desktop subió 2 puntos; Website Mobile no cambió; Backoffice bajó 2 puntos. Los tiempos FCP/LCP/Speed Index variaron poco; cada celda tiene una única ejecución y la repetibilidad queda **NOT VERIFIED**. Backoffice mostró CLS 0.109 y TBT 60 ms; son regresiones medidas y deben revisarse antes de declarar el ciclo completo exitoso. Lighthouse no identificó un nodo causante de CLS en los datos accesibles; atribución a lazy loading, contenido o variación queda **NOT VERIFIED**.
- **Accessibility: mejoró en backoffice.** Color contrast y label pasan; el score pasó 86→100. Website permaneció en 100.
- **SEO: mejoró para website.** Ambos informes website pasan `meta-description` y `robots-txt`, con SEO 82→100. El backoffice pasa metadatos y robots, pero Lighthouse marca `is-crawlable=0` por `noindex,nofollow`; el score 63 es intencional para el panel interno y no equivale a un fallo de seguridad.
- **Payload/code splitting:** en Lighthouse dev, website conserva las oportunidades estimadas de 564 KiB JS no usado, 2,746 KiB JS no minificado y 2,835 KiB de compresión; no cambian en el run mobile/desktop. Backoffice aún muestra 681 KiB, 3,671 KiB y 3,761 KiB respectivamente. Son diagnósticos dominados por el runtime Vite dev, no tamaños del bundle publicado.
- **Requests/transferencia:** website queda prácticamente igual. Backoffice baja 14 requests y 305,158 B. La compilación de Pass 1 había confirmado chunks por vista y entry JS de 238,415 B / 75.98 KiB gzip frente a 287,739 B / 83.76 KiB antes; esto es evidencia de build, no un score Lighthouse.
- No se hizo una nueva compilación ni se alteró la aplicación durante la medición AFTER. No se retiraron dependencias.

## Hallazgos solicitados

| Hallazgo BEFORE               | Resultado AFTER                                                          |
| ----------------------------- | ------------------------------------------------------------------------ |
| Meta description ausente      | Corregido; Lighthouse pasa en las tres vistas                            |
| `robots.txt` inválido/ausente | Corregido; Lighthouse pasa. Backoffice además declara `noindex,nofollow` |
| Color contrast                | Pasa en backoffice                                                       |
| Labels de tarifas             | Pasa en backoffice                                                       |
| JavaScript no usado           | Sigue apareciendo en Vite dev; no se trata como bundle de producción     |
| JavaScript no minificado      | Sigue apareciendo por Vite dev                                           |
| Compresión de texto           | Sigue apareciendo por Vite dev                                           |
| Code splitting                | Verificado en build; 17 JS files en el artefacto backoffice, entry menor |

## Runtime, autenticación y seguridad

Backend, website, backoffice, `/suppliers` y proxy `/api/health` respondieron HTTP 200 al cierre. Backoffice se midió autenticado, con 15 proveedores cargados. Login, `/auth/me`, proveedores e inventario habían respondido correctamente por el proxy durante el smoke test; inventory conserva 6 productos. La cuenta temporal se eliminó; el conteo final fue cero. SQLite continuó en `/tmp/trackflow-performance-audit.db`; la base PostgreSQL remota no se usó.

## Limitaciones y estado Git

- Una sola ejecución por celda: la varianza de Lighthouse, sobre todo de laboratorio simulado, queda **NOT VERIFIED**.
- El runtime es Vite dev, no servidor de producción; sus oportunidades de minificación, JS sin usar y compresión no cuantifican la experiencia publicada.
- CLS regresó en backoffice y no se aisló una causa concreta. Debe investigarse antes de corregir.
- No se ejecutó una cuarta repetición ni pruebas de campo/INP.
- No hubo cambios de código de aplicación durante AFTER. La rama sigue `feat/frontend-performance-audit`, alineada con `origin/main` (`0 0`); `git diff --check` pasó. Permanecen los cambios de Pass 1 y artefactos nuevos en `audit/`; no se hizo commit, push ni merge.

AFTER_AUDIT_STATUS: READY
PERFORMANCE_IMPROVED: MIXED
ACCESSIBILITY_IMPROVED: YES
SEO_IMPROVED: YES
REGRESSIONS_FOUND: YES
CODE_MODIFIED_DURING_AFTER: NO
NEXT_RECOMMENDED_STEP: Investigar el CLS 0.109 y repetir backoffice Lighthouse cold-cache antes de cualquier corrección.
