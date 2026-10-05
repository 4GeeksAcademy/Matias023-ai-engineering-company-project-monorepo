# BACKOFFICE CLS INVESTIGATION REPORT

Fecha: 2026-10-05. Rama: `feat/frontend-performance-audit`.

## Entorno y metodologia

Lighthouse 12.8.2, Chrome for Testing 154.0.8037.57, Desktop 1350x940 y throttling simulado. Tres repeticiones previas al fix y tres posteriores en el mismo Vite dev de `http://localhost:3001/suppliers`. Cada corrida utilizo una pestaña nueva y cache de navegador vaciada antes de Lighthouse; se preservo localStorage mediante `--disable-storage-reset` para mantener autenticacion, igual al protocolo oficial. Se verificaron el titulo Supplier Directory y 15 filas antes de cada medicion. No se cargaron rutas extra durante las corridas.

Produccion: `npm --prefix uis/backoffice run build`, seguido de Vite preview programatico en `http://127.0.0.1:3101/suppliers`. El proxy `/api` se dirigio a localhost:8000 mediante opciones runtime, sin archivos de configuracion permanentes. Ambas mediciones de produccion son **PRODUCTION_DIAGNOSTIC_ONLY**: no sustituyen los numeros oficiales. No se instalaron paquetes ni se recrearon bases de datos.

Cada nombre de corrida tiene `.report.json`, `.report.html`, `.png`, `-0.trace.json` y `-0.devtoolslog.json` en esta carpeta. Los logs se sanearon para retirar Authorization, cookies, postData y credenciales. Las cuentas fueron temporales, creadas por POST /api/users y eliminadas por su ID exacto mediante la API autenticada.

## Mediciones anteriores al fix

Valores de tiempos mostrados por Lighthouse; CLS numerico con mayor precision para identificar su repetibilidad.

| Medicion              | Performance |         CLS |   FCP |   LCP |   TBT | Speed Index | Requests | Bytes transferidos |
| --------------------- | ----------: | ----------: | ----: | ----: | ----: | ----------: | -------: | -----------------: |
| BEFORE oficial        |          61 | 0.001558852 | 2.6 s | 4.8 s | 40 ms |       2.9 s |       39 |          5,278,677 |
| AFTER oficial         |          59 | 0.108621294 | 2.4 s | 4.7 s | 60 ms |       2.8 s |       25 |          4,973,519 |
| dev-run-1             |          59 | 0.108621294 | 2.4 s | 4.6 s | 20 ms |       2.8 s |       25 |          4,973,273 |
| dev-run-2             |          60 | 0.108621294 | 2.4 s | 4.6 s | 60 ms |       2.7 s |       25 |          4,973,273 |
| dev-run-3             |          60 | 0.108621294 | 2.4 s | 4.6 s | 30 ms |       2.7 s |       25 |          4,973,273 |
| production-diagnostic |          97 | 0.108621294 | 0.4 s | 0.5 s |  0 ms |       0.5 s |        9 |             91,280 |

Produccion previa al fix: Accessibility 100, SEO 63. Los tres diagnosticos dev tambien obtuvieron Accessibility 100 y SEO 63. Best Practices 100 en las mediciones oficiales; el score SEO sigue condicionado por el noindex intencional del backoffice.

## Varianza

Las tres repeticiones dev dieron exactamente el mismo CLS: minimo = mediana = maximo = 0.10862129435032485; rango 0. Tambien lo reprodujo el Lighthouse de produccion. Performance vario entre 59 y 60 y TBT entre 20 y 60 ms, pero esa variacion no explica el evento CLS principal: sus rectangulos y valor fueron identicos en las cuatro trazas.

Una observacion DOM independiente sin Lighthouse en produccion solo contabilizo el salto residual de 0.001558852, aunque vio el estado inicial sin CSS. Por tanto el momento del pintado puede determinar si el salto grande se contabiliza; no se afirma que todo navegador o navegacion lo produzca. Bajo las condiciones Lighthouse solicitadas la regresion si fue reproducible, y no es exclusiva de Vite ni meramente ruido del score.

## Evidencia de DOM y traza

Los JSON oficiales no incluyen `layout-shift-elements` ni traza autenticada separada. `layout-shifts` del BEFORE identifica `.header-actions` y score 0.001558851810267049. El AFTER añade otro evento de 0.1070624425400578 sin nodo identificado; las capturas finales oficiales no permiten por si solas atribuir ese evento.

Las cuatro trazas diagnosticas anteriores al fix registran:

1. Un nodo con rectangulo anterior `[0,0,1350,19]` y posterior `[24,0,1302,229]`, score 0.1070624425400578, sin input reciente.
2. Un salto menor de 0.001558851810267049: `.header-actions`, el label de filtro y el boton Clear filters se desplazan horizontalmente cuando aparece la tabla y el scrollbar reduce el ancho disponible unos 15 px.

La instrumentacion temporal con PerformanceObserver/MutationObserver, guardada en [dev-dom-observation.json](dev-dom-observation.json), identifica el nodo grande como `MAIN.page`. Su primer estado era **Loading session**, width 1350 px, height 19 px, padding 0 y `hasPageCSS=false`. Al llegar App.css aparecen padding `48px 0px 80px` y las dimensiones del contenedor estilizado; PerformanceObserver registra el mismo salto 0.10706244254005778 con `MAIN.page` y los mismos rectangulos. No se guardaron textos de registros ni credenciales.

La observacion de produccion se conserva en [production-dom-observation.json](production-dom-observation.json). No tuvo el evento grande en esa navegacion directa, pero confirma el estado inicial Loading session sin CSS y la llegada posterior de estilos. El Lighthouse de produccion si produjo el evento, confirmado en su traza.

## Orden de red y fuente

Antes del fix, dev-run-1 obtiene `App.tsx`, inicia `/api/auth/me` alrededor de 643 ms, obtiene `SuppliersPage.tsx` alrededor de 681 ms y pide `App.css` alrededor de 708 ms (fin ~714 ms). El estilo llega despues de comenzar el render de sesion. En produccion previa, index CSS termina ~71 ms, `/auth/me` empieza ~167 ms y el CSS compartido diferido `App-DQn1pk0P.css` llega entre ~199 y ~215 ms.

La fuente explica esta dependencia: `App.tsx` mantiene paginas React.lazy y Suspense; el fallback y ProtectedRoute usan `.page`/`.state-card`. Antes del fix, App.css se importaba desde las paginas lazy, no desde el entry/router. index.css solamente define base y fuentes; no define esas clases. Por ello el primer fallback/session podia pintarse sin los estilos compartidos. No se encontraron descargas de fuentes: Inter es un nombre de fallback, no un webfont solicitado. No existe un PageHeader extraido; el encabezado es JSX dentro de SuppliersPage.

SuppliersPage obtiene datos asincronos, muestra loading, luego inserta una tabla sin altura reservada. Ese comportamiento y la aparicion del scrollbar explican el desplazamiento horizontal pequeno observado tambien BEFORE; no son la causa demostrada del evento grande de esta regresion. No se modifico la tabla ni sus datos.

## Causa y decision

Clasificacion: **VERIFIED_APPLICATION_REGRESSION / OTHER_VERIFIED_CAUSE**.

Causa comprobada: los estilos compartidos de los contenedores de sesion/fallback estaban en el grafo de una pagina lazy y llegaban despues del primer pintado. No se atribuye el problema a React.lazy en general ni se elimina code splitting. Los rectangulos, el estado sin estilos observado y la desaparicion del evento al cambiar solo la disponibilidad del CSS sustentan la atribucion.

## Fix minimo y validacion

Se anadio exactamente `import './App.css'` en [App.tsx](../../../uis/backoffice/src/App.tsx). Las paginas continuan lazy; no se editaron backend, autenticacion, tablas, datos, estilos, config Vite o Docker. Los imports existentes en paginas se deduplican por Vite.

Build y TypeScript: PASS. Jest: 2 suites, 37 tests PASS. `git diff --check`: PASS. El build ahora coloca el CSS compartido en el entry (8.21 kB, gzip 2.23 kB), mantiene chunks por pagina y entry JS 238.37 kB (gzip 75.96 kB). No se cambio la politica noindex.

En post-fix-dev-run-1 App.css termina ~263 ms, antes de `/auth/me` (~508 ms). En produccion post-fix index CSS termina ~58 ms, antes de `/auth/me` (~179 ms); ya no existe un CSS de pagina compartido solicitado despues del estado de sesion.

| Post-fix                       | Performance | A11y | SEO |         CLS |   FCP |   LCP |   TBT | Speed Index | Requests |     Bytes |
| ------------------------------ | ----------: | ---: | --: | ----------: | ----: | ----: | ----: | ----------: | -------: | --------: |
| post-fix-dev-run-1             |          63 |  100 |  63 | 0.001558852 | 2.4 s | 4.6 s | 10 ms |       2.7 s |       25 | 4,973,407 |
| post-fix-dev-run-2             |          62 |  100 |  63 | 0.001558852 | 2.4 s | 4.7 s | 70 ms |       2.8 s |       25 | 4,973,407 |
| post-fix-dev-run-3             |          62 |  100 |  63 | 0.001558852 | 2.5 s | 4.7 s | 30 ms |       2.8 s |       25 | 4,973,407 |
| post-fix-production-diagnostic |         100 |  100 |  63 | 0.001558852 | 0.4 s | 0.5 s |  0 ms |       0.5 s |        8 |    90,792 |

Las cuatro trazas post-fix contienen solamente score 0.001558851810267049; el evento 0.1070624425400578 desaparecio. Minimo = mediana = maximo de CLS post-fix dev = 0.001558851810267049. La reduccion se midio, no se estimo. Los diagnosticos no reemplazan los resultados oficiales y no equivalen a una auditoria final completa de los dos frontends.

## Seguridad y limites

Backend, website, backoffice, `/suppliers` y proxy saludables; 15 proveedores siguen disponibles. Las cuentas creadas para diagnosticos se borraron con su identidad exacta; verificacion de prefijos de auditoria arrojo cero usuarios temporales. SQLite sigue en `/tmp/trackflow-performance-audit.db`; PostgreSQL remoto no se utilizo. El preview utilizo el mismo backend local y no recreo su base.

Los hashes de todos los archivos BEFORE y AFTER oficiales coinciden con los guardados al inicio. No se editaron sus reportes. Los logs nuevos fueron saneados y el escaneo JWT no encontro tokens. Los perfiles y procesos temporales de Chrome/preview se cerraron al finalizar; los contenedores normales se conservaron.

Git sigue en `feat/frontend-performance-audit`, divergencia con origin/main `0 0`. Conserva los cambios previos Pass 1 y agrega un unico import de aplicacion, mas evidencia bajo `audit/diagnostics/cls/`. No hubo commit, push ni merge.

Limitaciones: datos de laboratorio, un solo entorno/viewport y una sola corrida Lighthouse de produccion por version. No se demuestra ausencia universal de CLS; el residual de scrollbar permanece y las puntuaciones de Performance pueden variar por CPU/red. El lint preexistente documentado en Pass 1 no se amplio ni se corrigio. La extraccion reusable y documentos finales del proyecto siguen siendo tareas separadas.

CLS_INVESTIGATION_STATUS: READY
CLS_REGRESSION_REPRODUCIBLE: YES
ROOT_CAUSE: Carga tardia de App.css deja MAIN.page de sesion/fallback sin estilos en el primer pintado
FIX_REQUIRED: YES
FIX_APPLIED: YES
POST_FIX_CLS: 0.001558851810267049
READY_FOR_FINAL_AUDIT: YES
NEXT_RECOMMENDED_STEP: Ejecutar la matriz final Lighthouse preservando los informes oficiales anteriores.
