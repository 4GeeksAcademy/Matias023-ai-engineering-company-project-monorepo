# Frontend Performance Audit Report

## Scope and source

Entrega conforme a la rubrica 4Geeks suministrada por el usuario. [AUDIT.md](AUDIT.md) contiene la medicion inicial, problemas/causas y dos candidatos de refactor; este documento describe lo realizado, sus resultados y limitaciones. El historial BEFORE, AFTER oficial previo al fix CLS y FINAL post-fix se mantiene separado y sin sobrescritura.

## Corrections applied

1. **Route-level code splitting:** paginas del backoffice con React.lazy/import dinamico y Suspense accesible en [App.tsx](uis/backoffice/src/App.tsx). Se preservaron rutas, wrappers de autenticacion y redirects.
2. **Accessible names:** `aria-label` especifico por proveedor en los campos de tarifa de [SuppliersPage.tsx](uis/backoffice/src/pages/SuppliersPage.tsx). No se modifico logica de edicion.
3. **Contrast:** boton primario mas oscuro en [App.css](uis/backoffice/src/App.css), 5.88:1 con texto blanco y 7.29:1 en hover.
4. **Meta descriptions:** descripcion de actividad en [website HTML](uis/website/index.html); descripcion interna y titulo claro en [backoffice HTML](uis/backoffice/index.html).
5. **Robots handling:** [website robots](uis/website/public/robots.txt) permite crawling; [backoffice robots](uis/backoffice/public/robots.txt) y meta noindex/nofollow evitan indexar el panel interno. No es una medida sustitutiva de autenticacion.
6. **Shared CSS CLS fix:** import temprano App.css en App.tsx para evitar el primer layout de sesion sin estilos. La causa se comprobo mediante DOM/trazas y corridas repetidas. No se elimino React.lazy.
7. **Reusable extraction:** [PageHeader.tsx](uis/backoffice/src/components/PageHeader.tsx), integrado en suppliers, inventory products, inbound y outbound. Mantiene las mismas clases/elementos y recibe acciones como children; no altera APIs, estado ni datos. Es refactor de mantenibilidad, no una mejora Lighthouse reclamada.

Estas correcciones estan presentes en el diff; no se cambio backend, DB, config Vite/Docker, dependencias o lockfiles.

## BEFORE vs FINAL

Lighthouse 12.8.2 y Chrome 154.0.8037.57, mismos perfiles y throttling simulado en Vite dev/localhost. Estas tablas comparan las matrices historicas validadas BEFORE y FINAL, anteriores a la extraccion PageHeader. La comprobacion posterior al refactor se reporta aparte, sin reemplazar sus cifras.

### Website Desktop

| Metric         |    BEFORE |     FINAL |      Delta |
| -------------- | --------: | --------: | ---------: |
| Performance    |        69 |        70 |         +1 |
| Accessibility  |       100 |       100 |          0 |
| Best Practices |        96 |        96 |          0 |
| SEO            |        82 |       100 |        +18 |
| FCP            |     2.0 s |     2.0 s | 0 mostrado |
| LCP            |     3.5 s |     3.5 s | 0 mostrado |
| TBT            |      0 ms |      0 ms |          0 |
| CLS            |         0 |         0 |          0 |
| Speed Index    |     2.1 s |     2.0 s |     -0.1 s |
| Requests       |        13 |        13 |          0 |
| Transfer bytes | 3,691,114 | 3,691,262 |       +148 |

### Website Mobile

| Metric         |    BEFORE |     FINAL |      Delta |
| -------------- | --------: | --------: | ---------: |
| Performance    |        56 |        56 |          0 |
| Accessibility  |       100 |       100 |          0 |
| Best Practices |        96 |        96 |          0 |
| SEO            |        82 |       100 |        +18 |
| FCP            |    10.9 s |    10.8 s |     -0.1 s |
| LCP            |    19.7 s |    19.5 s |     -0.2 s |
| TBT            |     10 ms |     10 ms | 0 mostrado |
| CLS            |         0 |         0 |          0 |
| Speed Index    |    10.9 s |    10.8 s |     -0.1 s |
| Requests       |        13 |        13 |          0 |
| Transfer bytes | 3,691,114 | 3,691,262 |       +148 |

**Mejora medible corporate website: SEO 82 -> 100 en ambos perfiles. No se afirma mejora de Performance Mobile: 56 -> 56.**

### Backoffice Desktop `/suppliers`

| Metric         |      BEFORE |       FINAL |                       Delta |
| -------------- | ----------: | ----------: | --------------------------: |
| Performance    |          61 |          63 |                          +2 |
| Accessibility  |          86 |         100 |                         +14 |
| Best Practices |         100 |         100 |                           0 |
| SEO            |          82 |          63 | -19 intencional por noindex |
| FCP            |       2.6 s |       2.4 s |                      -0.2 s |
| LCP            |       4.8 s |       4.7 s |                      -0.1 s |
| TBT            |       40 ms |       60 ms |                      +20 ms |
| CLS            | 0.001558852 | 0.001558852 |                           0 |
| Speed Index    |       2.9 s |       2.7 s |                      -0.2 s |
| Requests       |          39 |          25 |                         -14 |
| Transfer bytes |   5,278,677 |   4,973,389 |                    -305,288 |

**Mejora medible backoffice: Accessibility 86 -> 100; Performance 61 -> 63 en la matriz FINAL equivalente.** No se oculta el TBT mayor ni el SEO menor. La significancia de pequenas variaciones de tiempo/score con una corrida por celda es **NOT VERIFIED**.

Datos fuente: [BEFORE](audit/before/BASELINE_REPORT.md), [AFTER oficial](audit/after/AFTER_REPORT.md), [FINAL](audit/final/FINAL_AUDIT_REPORT.md). Los reportes anteriores con estado de entrega incompleta son historicos; este documento agrega los entregables y la extraccion que faltaban, no reescribe esos registros.

## CLS regression history

AFTER oficial antes del fix: backoffice Performance 59 y CLS 0.108621294. Tres repeticiones dev y una produccion confirmaron un evento 0.107062443 en MAIN.page causado por llegada tardia del CSS. La correccion de un import lo elimino; tres dev post-fix, produccion diagnostica, FINAL y validacion del refactor mantuvieron 0.001558852.

Produccion post-fix Performance 100 es **PRODUCTION_DIAGNOSTIC_ONLY**, no reemplaza el FINAL dev. [Investigacion](audit/diagnostics/cls/CLS_INVESTIGATION_REPORT.md). El pequeno CLS por cambio de ancho al aparecer scrollbar permanece; no se reclama CLS cero.

## Highest-impact correction

- **Score impact:** website SEO +18 es el mayor cambio de categoria observado, con descripcion y robots pasando en Lighthouse. Backoffice Accessibility +14 valida labels/contraste. Son conjuntos de correcciones; no se hizo un experimento que aisle cuantos puntos aporta cada metadato o cada label.
- **Stability/Core Web Vitals:** la carga temprana de CSS tiene la evidencia causal mas fuerte: elimina el evento reproducible y reduce CLS de 0.108621294 a 0.001558852 (aproximadamente 98.6%). Importa porque corrige una regresion real introducida durante el ciclo, manteniendo code splitting.
- **Bundle:** entry backoffice BEFORE 287,739 B frente al actual aproximadamente 238.41 kB, con rutas divididas. No se adjudican los MB de React/Vite dev al bundle de produccion.
- **Refactor:** PageHeader centraliza markup en cuatro paginas; su beneficio es mantenibilidad/consistencia. No se usa como supuesto beneficio de Performance.

## Validation after reusable extraction

- Backoffice `tsc -b && vite build`: PASS. Entry JS 238.41 kB / 75.99 kB gzip; CSS 8.21 kB / 2.23 kB gzip; PageHeader chunk 0.40 kB / 0.23 kB gzip. Code splitting y CSS raiz permanecen activos.
- Jest: 2 suites / 37 tests PASS. No se removieron tests.
- SSR del componente via Vite/React: HTML exacto section/div/p/h1/div, children y escapado de texto PASS, sin crear nueva configuracion de tests.
- Lint: **PREEXISTING_FAILURES_ONLY**. Las mismas cuatro reglas/fallos de HEAD: AuthContext, ProfilePage y efecto SuppliersPage; este ultimo cambia de linea 103 a 104 por el import. Ningun error en PageHeader o las paginas inventory. Tres warnings de coverage previos. No se deshabilitaron reglas.
- Website no cambio durante esta extraccion; su build/types PASS registrado en FINAL se conserva. No se recompilo ni repitio su Lighthouse sin necesidad.
- Smoke actual: register 201, login/me 200, suppliers 15 filas, inventory 6 productos; inbound/outbound conservaron preseleccion desde botones Inventory; website renderiza. Cuenta temporal eliminada. No se enviaron mutaciones de inventario o tarifas.
- Evidencia separada: [functional-results.json](audit/delivery-validation/functional-results.json), [LHR suppliers JSON](audit/delivery-validation/suppliers.report.json), [HTML](audit/delivery-validation/suppliers.report.html), [screenshot](audit/delivery-validation/suppliers.png).

### Targeted Lighthouse after extraction

Solo se midio suppliers Desktop, mismo Lighthouse/throttling/cache/session que antes: Performance **61**, Accessibility **100**, Best Practices **100**, SEO **63**, FCP **2.5 s**, LCP **4.7 s**, TBT **100 ms**, CLS **0.001558852**, Speed Index **2.9 s**, **26 requests / 4,976,386 B**.

Performance es dos puntos menor al 63 historico y TBT mayor; se reportan, no se reemplazan ni se presentan como mejoras. La causalidad de esa variacion con un unico run es **NOT VERIFIED**. El import compartido agrega una solicitud de modulo en Vite dev; no se promete ahorro de red por este refactor. El HTML/acciones se preservaron y el fix CLS/A11y se mantiene empiricamente. No se demostro una nueva regresion funcional o de layout.

## Screenshot evidence and integrity

Tres screenshots Lighthouse BEFORE en audit/before y tres oficiales AFTER en audit/after, mas los screenshots FINAL post-fix y posterior a PageHeader del backoffice en audit/after. Cada fuente y score se detalla en [AUDIT.md](AUDIT.md) y [screenshots.json](audit/delivery-validation/screenshots.json). Las capturas originales de aplicacion, JSON, HTML y trazas fueron preservadas; se agregaron archivos nuevos con nombres distintos. Los hashes de todos los archivos previos coinciden. Los logs nuevos autenticados se sanearon; no se imprimen credenciales.

El backend permanece SQLite local; 15 proveedores/6 productos, sin acceso a DB remota. Datos de campo/INP, teclado exhaustivo e indexacion real: **NOT VERIFIED**. Website sigue placeholder; no hay segunda vista compleja aplicable.

AGENT_SKILLS_USED: NO

## 4Geeks checklist

- [x] Lighthouse BEFORE corporate website Desktop/Mobile home; segunda vista no disponible y documentada.
- [x] Lighthouse BEFORE backoffice de mayor densidad funcional.
- [x] Screenshots de informes BEFORE bajo audit/before.
- [x] Lighthouse AFTER ambos frontends y validacion FINAL post-fix separada.
- [x] Screenshots AFTER bajo audit/after, diferenciando oficial y post-fix.
- [x] AUDIT.md en raiz con scores, problemas y causas.
- [x] Dos candidatos reales documentados.
- [x] Componente reutilizable extraido e integrado en cuatro paginas.
- [x] REPORT.md en raiz con correcciones, comparaciones e impacto.
- [x] Mejora medible de al menos un score por frontend: Website SEO y Backoffice A11y.
- [x] Build/types, 37 tests y smoke sin regresiones funcionales/CLS detectadas; diferencias de timing reportadas.
- [x] Sin nuevos errores lint; fallos previos documentados.
- [x] Evidencia anterior preservada y credenciales saneadas.
- [x] No skills instaladas para fabricar evidencia; AGENT_SKILLS_USED: NO.
- [x] Screenshots y entregables incluidos en el commit de entrega autorizado.

## Delivery status

El commit de entrega que incorpora esta revision incluye codigo, documentos y capturas, completando el criterio de versionado de la rubrica. Los informes previos conservan su estado historico anterior al commit; no se reescribieron. El PR se propone hacia main sin merge automatico. No se requieren mas refactors para el minimo de extraccion. Una reevaluacion estadistica del Performance focalizado seria evidencia adicional, no una mejora ficticia ni sustitucion de numeros existentes.
