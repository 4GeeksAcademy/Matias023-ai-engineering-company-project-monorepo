# Frontend Performance Audit

## Scope

Corporate website y backoffice TrackFlow. Fuente de requisitos: rubrica 4Geeks suministrada por el usuario en el adjunto **GO FIX - COMPLETE VERIFIED 4GEEKS FRONTEND PERFORMANCE RUBRIC**. Exige medicion BEFORE/AFTER en ambos frontends, capturas, problemas con razonamiento causal, dos candidatos de extraccion y al menos un componente React o Custom Hook extraido e integrado. No se afirma haber consultado una URL externa del curso.

Website es un placeholder de una sola pantalla: [App.tsx](uis/website/src/App.tsx). Se reviso su HTML, CSS, dependencias y configuracion; no tiene duplicacion significativa ni segunda vista compleja. **WEBSITE_SECOND_COMPLEX_VIEW_NOT_AVAILABLE**. No se creo una pagina artificial. Backoffice `/suppliers` fue la vista elegida por su tabla editable, filtros, formulario y estados de carga/autenticacion.

## Lighthouse BEFORE

Lighthouse 12.8.2, Chrome for Testing 154.0.8037.57, throttling simulado, Vite dev en localhost. Desktop 1350x940; Mobile 412x823. Backoffice autenticado, 15 proveedores, cache de navegador vaciada. Una corrida por celda. LCP/CLS son datos de laboratorio; INP y datos de campo: **NOT VERIFIED**.

| Target                          | Performance | Accessibility | Best Practices | SEO |    FCP |    LCP |   TBT |   CLS | Speed Index |
| ------------------------------- | ----------: | ------------: | -------------: | --: | -----: | -----: | ----: | ----: | ----------: |
| Website Desktop `/`             |          69 |           100 |             96 |  82 |  2.0 s |  3.5 s |  0 ms |     0 |       2.1 s |
| Website Mobile `/`              |          56 |           100 |             96 |  82 | 10.9 s | 19.7 s | 10 ms |     0 |      10.9 s |
| Backoffice Desktop `/suppliers` |          61 |            86 |            100 |  82 |  2.6 s |  4.8 s | 40 ms | 0.002 |       2.9 s |

Website: 13 requests / 3,691,114 bytes en ambas modalidades. Backoffice: 39 requests / 5,278,677 bytes. Datos originales: [baseline](audit/before/BASELINE_REPORT.md), [website Desktop JSON](audit/before/website-desktop.report.json), [website Mobile JSON](audit/before/website-mobile.report.json), [backoffice JSON](audit/before/backoffice-suppliers-desktop.report.json).

### Screenshot correspondence

Las capturas `*-lighthouse.png` muestran los cuatro scores del informe HTML correspondiente. Fueron capturadas a partir de los informes reales existentes, sin inventar ni ejecutar de nuevo las mediciones historicas. Las PNG originales sin ese sufijo muestran la aplicacion y se conservaron.

| Measurement                                 | Screenshot del informe                                                 | Scores P/A/BP/SEO |
| ------------------------------------------- | ---------------------------------------------------------------------- | ----------------- |
| BEFORE website Desktop                      | [Screenshot](audit/before/website-desktop-lighthouse.png)              | 69/100/96/82      |
| BEFORE website Mobile                       | [Screenshot](audit/before/website-mobile-lighthouse.png)               | 56/100/96/82      |
| BEFORE backoffice Desktop                   | [Screenshot](audit/before/backoffice-suppliers-desktop-lighthouse.png) | 61/86/100/82      |
| AFTER oficial website Desktop               | [Screenshot](audit/after/website-desktop-lighthouse.png)               | 71/100/96/100     |
| AFTER oficial website Mobile                | [Screenshot](audit/after/website-mobile-lighthouse.png)                | 56/100/96/100     |
| AFTER oficial backoffice, antes de fix CLS  | [Screenshot](audit/after/backoffice-suppliers-desktop-lighthouse.png)  | 59/100/100/63     |
| FINAL backoffice post-fix CLS               | [Screenshot](audit/after/backoffice-final-lighthouse.png)              | 63/100/100/63     |
| Validacion backoffice despues de PageHeader | [Screenshot](audit/after/backoffice-delivery-lighthouse.png)           | 61/100/100/63     |

El screenshot FINAL deriva del [HTML FINAL](audit/final/backoffice-suppliers-desktop.report.html), no del AFTER previo al fix; el de validacion PageHeader deriva del [HTML focalizado](audit/delivery-validation/suppliers.report.html). [Mapa de fuentes y scores visibles](audit/delivery-validation/screenshots.json). Estos archivos forman parte del commit de entrega junto con los informes y el codigo validado.

## Problems identified

### 1. Descripcion y robots en website

- Sintoma: SEO 82, Lighthouse falla `meta-description` y `robots-txt`.
- Evidencia: ambos LHR BEFORE website; el HTML carecia de descripcion y no habia robots.txt en public.
- Causa: metadato ausente; Vite devolvia HTML de la SPA ante una ruta robots inexistente, no un archivo robots valido. Esto no prueba como se comportaria otro servidor de produccion.
- Afecta: website. Correccion: descripcion coherente con TrackFlow y archivo public/robots.txt que permite crawling. No se invento contenido de una nueva vista.

### 2. SEO/documento del backoffice

- Sintoma: faltaban descripcion y robots valido; titulo generico `backoffice`.
- Evidencia: LHR BEFORE y [index.html](uis/backoffice/index.html).
- Causa: mismas omisiones de HTML/public y fallback SPA.
- Correccion: titulo y descripcion internos, robots valido, noindex/nofollow apropiado para herramienta autenticada. La disminucion de SEO por bloqueo de indexacion es intencional y se reporta; robots no reemplaza autenticacion.

### 3. Tarifa editable sin nombre accesible

- Sintoma: Accessibility 86; Lighthouse `label` identifica los 15 inputs `.rate-editor`.
- Evidencia: [SuppliersPage.tsx](uis/backoffice/src/pages/SuppliersPage.tsx) y LHR BEFORE.
- Causa: el encabezado de columna no establece automaticamente un nombre accesible individual al input; no habia label ni aria-label.
- Correccion: nombre `Rate per shipment for <supplier>` por campo, sin modificar su valor, eventos o teclado.

### 4. Contraste del boton primario

- Sintoma: Lighthouse `color-contrast` identifica New supplier.
- Causa: texto blanco sobre #4d73ff: ratio calculado 4.03:1, insuficiente para este texto.
- Afecta: boton compartido del backoffice, [App.css](uis/backoffice/src/App.css).
- Correccion: #3559d8, ratio 5.88:1; hover #2d4cbd, 7.29:1. El LHR posterior pasa contraste.

### 5. Carga eager de rutas

- Sintoma: el router importaba las 14 paginas upfront; build con entry JS unico de 287,739 bytes.
- Causa comprobada: importaciones estaticas desde App.tsx, sin React.lazy/import dinamico. Esto es una oportunidad real de reducir el entry, no prueba de que todo el score de Performance dependiera de esas paginas.
- Correccion: route-level React.lazy/Suspense, conservando paths, ProtectedRoute y redirecciones. El build verifica chunks por pagina y entry menor.

### 6. Payload excesivo observado en Vite dev

- Sintoma: JS no minificado/no usado y compresion; transferencias de varios MB y LCP lento, particularmente Mobile.
- Evidencia: recursos `react-dom_client.js`, router, `@vite/client` y `@react-refresh` en LHR. Website estimaba 2,746 KiB minificables, 564 KiB no usados y 2,835 KiB de compresion.
- Causa comprobada: runtime de desarrollo con tooling y modulos no minificados; no equivale a bundles publicados. Production builds eran sustancialmente menores.
- Enfoque: verificar minificacion normal y ausencia de HMR en dist; no eliminar dependencias ni tratar el overhead dev como defecto de produccion. Impacto real en deploy y cache de produccion: **NOT VERIFIED**.

### 7. Regresion CLS detectada despues de Pass 1

- Sintoma: AFTER backoffice CLS 0.108621294 frente a BEFORE 0.001558852.
- Evidencia: tres repeticiones dev y una produccion reproducen el salto; [investigacion](audit/diagnostics/cls/CLS_INVESTIGATION_REPORT.md), trazas y observacion DOM.
- Causa verificada: App.css estaba en el grafo de paginas lazy. MAIN.page de sesion se pintaba sin estilos, con 19 px de altura, y pasaba a 229 px al llegar el CSS; aportaba 0.107062443 de CLS.
- Correccion minima: import App.css desde App.tsx raiz. Se mantuvo code splitting. Tres corridas post-fix y produccion bajaron a 0.001558852; el FINAL y la validacion del refactor mantienen ese valor.
- Queda un salto pequeno por ancho/scrollbar al insertar la tabla; no se afirma CLS cero.

## Code analysis / refactoring

Se revisaron BOTH frontends. La web no aporta un segundo caso real; los dos candidatos siguientes provienen de duplicacion concreta del backoffice, sin fabricar un hook de calculo puro.

### Candidate 1: page headers - IMPLEMENTED

- Archivos integrados: [SuppliersPage.tsx](uis/backoffice/src/pages/SuppliersPage.tsx), [InventoryProductsPage.tsx](uis/backoffice/src/pages/InventoryProductsPage.tsx), [InboundOrderPage.tsx](uis/backoffice/src/pages/InboundOrderPage.tsx), [OutboundOrderPage.tsx](uis/backoffice/src/pages/OutboundOrderPage.tsx).
- Duplicacion: section.header; div con eyebrow, h1 y subtitle; div.header-actions con links/botones/recuentos. Inicialmente el mismo patron aparecia en diez paginas operativas; se extrajeron cuatro usos. Los otros seis no se refactorizaron para limitar alcance.
- Abstraccion: [PageHeader.tsx](uis/backoffice/src/components/PageHeader.tsx), props `title: string`, `subtitle: string`, `children: ReactNode`. Los children son las acciones originales, sin handlers dentro del componente.
- Justificacion: estructura identica con textos/acciones variables. Centraliza markup, no estado ni APIs.
- Beneficio: menos JSX repetido y un unico lugar para mantener semantica. No se atribuye una mejora de score a la extraccion.
- Riesgo: wrappers/clases adicionales podrian cambiar layout. Se conserva exactamente section/div/p/h1/div, clases y orden; SSR, browser y CLS focalizado validaron el contrato.

### Candidate 2: inventory fetch lifecycle - NOT IMPLEMENTED

- Archivos: InventoryProductsPage.tsx, InboundOrderPage.tsx y OutboundOrderPage.tsx, enlazados arriba.
- Duplicacion: array de productos, loading/error, callback getInventoryProducts y efecto .then/.catch/.finally; las tres paginas cargan el mismo recurso al montar.
- Propuesta legitima: `useInventoryProducts()` con `{ products, loading, error, reload }`, encapsulando efectos y lifecycle reales, no calculos puros.
- Beneficio: consistencia de lifecycle/error/retry y menos codigo repetido; ninguna mejora runtime garantizada sin medicion.
- Riesgo: outbound debe refrescar stock tras una mutacion y tiene estado adicional refreshedProducts; mensajes de error y retry actuales difieren. Una extraccion apresurada podria cambiar esos comportamientos. No se implemento porque PageHeader satisface el minimo requerido con menor riesgo.

## Evidence and limits

No se alteraron BEFORE/AFTER/CLS/FINAL existentes. La validacion adicional esta en [audit/delivery-validation](audit/delivery-validation/functional-results.json). El informe de resultados y las regresiones historicas se explican en [REPORT.md](REPORT.md). Datos de campo, indexacion real y causalidad de pequenas variaciones Lighthouse: **NOT VERIFIED**.

AGENT_SKILLS_USED: NO
