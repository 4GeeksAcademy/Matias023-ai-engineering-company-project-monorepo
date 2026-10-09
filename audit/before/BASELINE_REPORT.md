# FRONTEND PERFORMANCE — BEFORE BASELINE REPORT

Fecha: 2026-10-03  
Rama: `feat/frontend-performance-audit`  
Estado Git inicial: limpio; `HEAD` alineado con `origin/main` (`0 0`).  
Estado al cerrar la medición: únicamente `audit/` nuevo; sin cambios rastreados; `git diff --check` limpio.

## Método y URLs

| Aplicación | URL auditada                      | Perfil Lighthouse | Estado                                         |
| ---------- | --------------------------------- | ----------------- | ---------------------------------------------- |
| Website    | `http://localhost:3000/`          | Desktop, 1350×940 | Medido                                         |
| Website    | `http://localhost:3000/`          | Mobile, 412×823   | Medido                                         |
| Backoffice | `http://localhost:3001/suppliers` | Desktop, 1350×940 | Medido con sesión autenticada y 15 proveedores |

Se usó Lighthouse 12.8.2, Chrome for Testing 154.0.8037.57, `throttling-method=simulate`, una ejecución por celda. Website y backoffice se sirvieron desde los Vite dev servers existentes en los contenedores. El backoffice se auditó a través del proxy normal `/api`; una cuenta efímera validó la vista y se eliminó al terminar. Las capturas se guardaron a 1350×900 y 390×844 respectivamente.

## Resultados

| Celda                           | Performance | Accessibility | Best Practices | SEO |    FCP |    LCP |   TBT |   CLS | Speed Index | Requests | Transferidos |
| ------------------------------- | ----------: | ------------: | -------------: | --: | -----: | -----: | ----: | ----: | ----------: | -------: | -----------: |
| Website Desktop                 |          69 |           100 |             96 |  82 |  2.0 s |  3.5 s |  0 ms |     0 |       2.1 s |       13 |  3,691,114 B |
| Website Mobile                  |          56 |           100 |             96 |  82 | 10.9 s | 19.7 s | 10 ms |     0 |      10.9 s |       13 |  3,691,114 B |
| Backoffice `/suppliers` Desktop |          61 |            86 |            100 |  82 |  2.6 s |  4.8 s | 40 ms | 0.002 |       2.9 s |       39 |  5,278,677 B |

Son métricas Lighthouse de laboratorio; no son datos de campo. INP y Core Web Vitals de usuarios reales: **NOT VERIFIED**. La matriz solicitada quedó cubierta; no se midieron rutas adicionales.

## Evidencia

- Website Desktop: [captura](website-desktop.png), [reporte HTML](website-desktop.report.html), [JSON](website-desktop.report.json), [traza](website-desktop-0.trace.json), [DevTools log](website-desktop-0.devtoolslog.json).
- Website Mobile: [captura](website-mobile.png), [reporte HTML](website-mobile.report.html), [JSON](website-mobile.report.json), [traza](website-mobile-0.trace.json), [DevTools log](website-mobile-0.devtoolslog.json).
- Backoffice Desktop: [captura](backoffice-suppliers-desktop.png), [reporte HTML](backoffice-suppliers-desktop.report.html), [JSON](backoffice-suppliers-desktop.report.json).

## Hallazgos medidos

- En ambos perfiles de website, Lighthouse lista como oportunidades 2,746 KiB de JavaScript no minificado, 564 KiB de JavaScript no usado y 2,835 KiB por compresión de texto. El mayor recurso observado es el prebundle de desarrollo `react-dom_client.js` (~3.13 MB), seguido por Vite client y React Refresh. El total transferido es ~3.60 MiB.
- En el backoffice cold-cache, Lighthouse lista 3,864 KiB de JavaScript no minificado, 726 KiB no usado y 3,968 KiB de ahorro estimado por compresión. Los recursos más grandes son `react-dom_client.js` (~2.82 MB), `react-router-dom.js` (~1.43 MB), Vite client y el módulo de `SuppliersPage`. El total transferido es ~5.04 MiB.
- Los ahorros anteriores son estimaciones del dev server, no reducciones comprobadas en producción. Los artefactos de build ya existentes miden 219,864 B de JS en website y 287,739 B en backoffice; sus gzip fueron 68.72 KiB y 83.76 KiB en el build previamente verificado. No se ejecutó Lighthouse contra esos bundles de producción.
- LCP excede 2.5 s en las tres celdas, especialmente Website Mobile (19.7 s). CLS queda en 0–0.002 y TBT en 0–40 ms. Main-thread work informado: 0.4 s Website Desktop, 1.1 s Website Mobile y 0.8 s Backoffice Desktop.
- No hay recursos render-blocking listados, imágenes o fuentes descargadas en las páginas medidas. No se comprobó un problema de imágenes; tampoco se informó una oportunidad ponderada de CSS no usado. La ausencia de un hallazgo no demuestra una mejora potencial nula.
- Website puntúa 100 en Accessibility. Backoffice puntúa 86; fallan contraste de color y asociación de etiquetas en formularios. En SEO ambos informes marcan meta description ausente y respuesta `robots.txt` inválida; la respuesta de robots se obtuvo desde el runtime Vite, por lo que no se extrapola a un despliegue de producción.
- El build actual no muestra división por rutas y [uis/backoffice/src/App.tsx](../../uis/backoffice/src/App.tsx) importa páginas eager. Es oportunidad estática de code splitting, no una mejora de score demostrada todavía.
- Website sigue siendo el placeholder descrito en [uis/website/src/App.tsx](../../uis/website/src/App.tsx); no hay una vista corporativa compleja ni assets de imagen que analizar. `WEBSITE_SECOND_COMPLEX_VIEW_NOT_AVAILABLE`.
- Se observaron dos solicitudes de `/api/auth/me` y dos de `/api/suppliers` en el contexto de desarrollo. `StrictMode` está activo en [uis/backoffice/src/main.tsx](../../uis/backoffice/src/main.tsx); si el doble efecto es exclusivo del modo desarrollo o afecta producción queda **NOT VERIFIED**.

## Interpretación y límites

El perfil medido es el runtime de desarrollo pedido, no una medición de producción: HMR, React Refresh, módulos sin minificar, compresión y caché del dev server dominan el payload y hacen que los ahorros Lighthouse de JS/compresión no representen el bundle publicado. Esto también afecta el tiempo simulado y la comparación. Los informes usaron una sola ejecución por celda; la variabilidad y una mediana de ejecuciones repetidas quedan **NOT VERIFIED**. El uso de localhost evita el túnel en la navegación de Lighthouse, pero la máquina Codespaces y la latencia compartida todavía pueden influir.

Antes/después se debe conservar el mismo modo de servidor, versión Lighthouse/Chrome, presets, throttling, datos (15 proveedores), estado autenticado y ruta. No se cambió código ni configuración, no se ejecutó Lighthouse sobre otra página y no se hizo optimización en esta fase.
