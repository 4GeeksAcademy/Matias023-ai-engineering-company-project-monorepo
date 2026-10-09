# FRONTEND PERFORMANCE OPTIMIZATION PASS 1 REPORT

Fecha: 2026-10-03  
Rama: `feat/frontend-performance-audit`  
Lighthouse AFTER: no ejecutado, según instrucción.

## Cambios

- `uis/backoffice/src/App.tsx`: reemplazó imports eager de las 14 páginas por `React.lazy` y añadió un fallback semántico `role="status"`. Se conservaron paths, wrappers de autenticación, redirecciones y comportamiento de rutas.
- `uis/backoffice/src/pages/SuppliersPage.tsx`: añadió un nombre accesible por proveedor a cada campo numérico de tarifa usando `aria-label`; los controles y valores visibles no cambiaron.
- `uis/backoffice/src/App.css`: oscureció el color del botón primario y su hover para cumplir contraste con texto blanco.
- `uis/website/index.html`: añadió una descripción que resume la actividad pública y geografía de TrackFlow; conservó el título.
- `uis/website/public/robots.txt`: permite indexar el sitio público.
- `uis/backoffice/index.html`: añadió descripción interna, título claro y `noindex,nofollow`.
- `uis/backoffice/public/robots.txt`: prohíbe crawling del backoffice. Esto no sustituye la autenticación ni protege endpoints.
- `audit/OPTIMIZATION_PASS_1_REPORT.md`: este informe. El `audit/before/BASELINE_REPORT.md` del usuario se dejó intacto.

## Hallazgos abordados

- SEO: la descripción faltaba en ambos documentos; ahora existe. Website permite crawling. Backoffice queda marcado no indexable, apropiado para una herramienta autenticada. Los archivos `robots.txt` se sirven en desarrollo y aparecen en ambos `dist/`.
- Accesibilidad: Lighthouse había señalado los campos de tarifa no etiquetados (15 elementos) y contraste del botón `New supplier`. Los campos ahora anuncian `Rate per shipment for <supplier>`; el color primario pasó a `#3559d8` y hover a `#2d4cbd`. Contraste WCAG calculado con texto blanco: **5.88:1** y **7.29:1**.
- Carga/render: la importación eager de páginas era verificable en `App.tsx`; el build previo tenía un entry JS único de 287,739 B (83.76 KiB gzip). Las rutas ahora cargan sus módulos al acceder a ellas, con fallback durante la descarga. No se modificaron efectos, cachés ni llamadas API duplicadas: la duplicación se observó en Vite dev con React StrictMode y su comportamiento en producción no está verificado.

## Builds de producción

Los scripts existentes ejecutan `tsc -b && vite build`. No hay configuración Vite de producción personalizada; se conservan minificación y optimizaciones estándar. Los builds finales no contienen referencias a `@vite/client`; el backoffice emite chunks por página. No se quitaron dependencias.

| Salida              |                      Antes |                     Pass 1 |                              Cambio medido |
| ------------------- | -------------------------: | -------------------------: | -----------------------------------------: |
| Website entry JS    | 219,864 B / 68.72 KiB gzip | 219,864 B / 68.72 KiB gzip |                           Sin cambio de JS |
| Backoffice entry JS | 287,739 B / 83.76 KiB gzip | 238,415 B / 75.98 KiB gzip | −49,324 B (−17.1%); gzip −7.78 KiB (−9.3%) |

El backoffice genera además chunks de página; `SuppliersPage` es 7.89 kB (2.32 KiB gzip), y las otras páginas están divididas. La tabla compara solo el entry inicial, no el total de bytes descargados al completar una sesión ni un score Lighthouse.

## Validación

- `npm --prefix uis/website run build`: PASS; TypeScript y Vite.
- `npm --prefix uis/backoffice run build`: PASS; TypeScript y Vite, chunks emitidos.
- `npm --prefix uis/backoffice test -- --runInBand`: PASS; 2 suites, 37 tests.
- `npm --prefix uis/backoffice run lint`: FAIL; 4 errores y 3 warnings. Errores existentes en lógica no modificada de `src/auth/AuthContext.tsx` (setState en effect y regla `react-refresh/only-export-components`), `src/pages/ProfilePage.tsx` (setState en effect) y `src/pages/SuppliersPage.tsx` (`useEffect` llama a `refreshSuppliers`, que comienza con setState). Los warnings son directivas eslint sin uso en artefactos de `coverage/lcov-report`. No se amplió este pass a refactorizar los efectos o el contexto.
- `get_errors` sobre `App.tsx` y `SuppliersPage.tsx`: sin errores de lenguaje/editor.
- Smoke test vía Chrome/proxy: website renderizó `TrackFlow`; `/suppliers` renderizó sus 15 filas; inventory renderizó sus 6 productos mediante ruta lazy. Registro/login/auth/me: 201/200/200; APIs suppliers/inventory: 200, con 15/6 filas. Cuenta temporal eliminada.
- Salud backend, website, backoffice, `/suppliers` y `/api/health`: HTTP 200. Backend siguió en SQLite local `/tmp/trackflow-performance-audit.db`; cero usuarios temporales al finalizar.
- `robots.txt` y metadatos confirmados en respuestas dev y artefactos de producción.

## Pendiente y límites

- No se ejecutó Lighthouse AFTER ni se afirma una mejora de score. El efecto en Performance/Accessibility/SEO queda **NOT VERIFIED** hasta la medición posterior en las mismas condiciones.
- Las mejoras de chunks se midieron en el build de producción; los 3.6–5.3 MB del baseline Lighthouse procedían de Vite dev y no se trataron como bundle de producción.
- No se hicieron cambios a código de website para crear una segunda vista; continúa el placeholder `WEBSITE_SECOND_COMPLEX_VIEW_NOT_AVAILABLE`.
- La duplicación de requests observada en dev queda pendiente de confirmar en producción antes de optimizarla.
- La extracción del `PageHeader` reutilizable identificada en el descubrimiento sigue pendiente para un pass mantenible separado; no se presentó como mejora de rendimiento.
- El lint completo queda FAIL por los errores preexistentes descritos, aunque builds, suite y smoke tests pasaron.

## Git

Sin commits, push ni merge. Rama conservada: `feat/frontend-performance-audit`, divergencia con `origin/main`: `0 0`. `git diff --check` limpio. Cambios de aplicación limitados a cinco archivos existentes más los dos nuevos `robots.txt`; evidencia `audit/` permanece sin rastrear hasta que se decida su commit.

OPTIMIZATION_PASS_1_STATUS: READY
TESTS_STATUS: PARTIAL
CODE_MODIFIED: YES
AFTER_LIGHTHOUSE_RUN: NO
NEXT_RECOMMENDED_STEP: Resolver o documentar el lint preexistente y luego ejecutar Lighthouse AFTER con la misma matriz y runtime.
