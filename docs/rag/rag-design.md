# TrackFlow — Diseño RAG y Base de Conocimiento

## 1. Objetivo

Implementar un asistente de consulta sobre documentación oficial
de TrackFlow, mediante Retrieval-Augmented Generation (RAG).

El asistente debe:
- Responder preguntas utilizando documentación recuperada.
- Identificar las fuentes de sus respuestas.
- Abstenerse cuando no exista respaldo suficiente.
- Respetar las restricciones comerciales documentadas.

## 2. Base de conocimiento

Ubicación: `docs/company-knowledge-base/`

Documentos fuente:

1. `trackflow-sla-delivery.es.md`
2. `trackflow-returns-policy.es.md`
3. `trackflow-carrier-coverage.es.md`
4. `trackflow-storage-pricing.es.md`

La indexación realizada contiene 16 fragmentos, distribuidos
en cuatro fragmentos por documento.

Metadatos del payload:

- `company`
- `source_document`
- `section`
- `language`
- `chunk_index`
- `text`

## 3. Arquitectura

Flujo general:

Usuario
  → React Backoffice
  → FastAPI protegido mediante JWT
  → Recuperador semántico
  → Qdrant
  → Fragmentos documentales
  → Gemini
  → Verificación de respuesta y citas
  → Respuesta o abstención

Componentes:

- Frontend: React, TypeScript y Vite.
- API: FastAPI.
- Base vectorial: Qdrant.
- Colección: `trackflow_knowledge`.
- Embeddings:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Generación: Gemini, modelo `gemini-3.5-flash-lite`.

Los modelos de embeddings y generación son distintos.

## 4. Pipeline RAG

Código principal: `scripts/rag/`

Operaciones implementadas:

1. Setup: preparar la colección vectorial.
2. Embed: fragmentar e indexar los documentos.
3. Retrieve: recuperar los fragmentos relevantes.
4. Query: generar y verificar una respuesta.

Configuración de recuperación evaluada:

- Top K: 3.
- Umbral de similitud: 0.54.

El umbral se conserva sin modificaciones tras la evaluación.

## 5. Integración API y frontend

Endpoint FastAPI:

`POST /rag/query`

El endpoint requiere autenticación JWT.

Acceso desde el frontend:

`POST /api/rag/query`

Vite utiliza un proxy que elimina el prefijo `/api`.

Ruta protegida en React:

`/rag`

El asistente muestra:

- Campo de consulta.
- Preguntas de ejemplo.
- Estado de carga.
- Respuesta generada.
- Fuentes documentales.
- Mensajes de abstención o error.

## 6. Seguridad y fidelidad

Las respuestas se validan mediante:

- Comprobación de citas.
- Comprobación de afirmaciones cuantitativas.
- Restricciones comerciales conocidas.
- Abstención cuando no hay fragmentos sobre el umbral.
- Protección específica de direccionalidad para rutas
  de entrada a Los Ángeles no documentadas.

Reglas comerciales relevantes:

- No prometer SLA garantizados durante alta demanda.
- Devoluciones internacionales sujetas a gestión manual.
- Descuentos de almacenamiento requieren aprobación
  de Miguel Torres.
- Excepciones de transportistas requieren intervención
  de Carlos Vega.

Las reglas deterministas no sustituyen una validación
semántica universal.

## 7. Evaluación de recuperación

Evaluación inicial:

- 12 preguntas sobre los cuatro documentos.
- Recall@3 exploratorio inicial: 91.7% con umbral 0.54.

Evaluación adicional con paráfrasis:

- 12 preguntas reformuladas.
- Primera medición: 75.0% con umbral 0.54.

Se identificó una pregunta con direccionalidad incorrecta:
"envíos a Los Ángeles" frente a la política documentada
sobre envíos "desde Los Ángeles".

Evaluación corregida:

- Preguntas: 12.
- Recuperaciones relevantes: 10.
- Recall@3: 83.3%.
- Objetivo académico: al menos 80%.
- Resultado: objetivo alcanzado.

Reporte:

`data/eval/rag_directionality_diagnostics.json`

Limitación metodológica:

Las paráfrasis evalúan hechos conocidos del conjunto de
calibración. No constituyen un holdout factual totalmente
independiente.

## 8. Preguntas sin respaldo

Se comprobaron preguntas sobre:

- Entregas garantizadas en Chile en dos horas.
- Devoluciones mediante criptomonedas.
- Teléfono del call center.
- Cobertura exclusiva hacia Los Ángeles.

Un resultado vectorial con similitud suficiente no
demuestra por sí solo que respalde la afirmación solicitada.

Por ese motivo se añadió una protección específica
para la direccionalidad de rutas hacia Los Ángeles.

## 9. Pruebas verificadas

Resultados observados durante el desarrollo:

- Suite RAG: 41/41 tests aprobados, incluidas 9 pruebas de autorizacion de transportistas.
- Seguridad comercial: se verificaron respuestas permitidas y prohibidas sobre aprobacion de Carlos Vega. La proteccion cubre los patrones probados, no todas las posibles parafrasis.
- Tests del cliente frontend RAG: 4/4.
- Tests API con mocks: 6/6.
- E2E de grounding: 3/3.
- Build React y TypeScript: PASS.
- Proxy de desarrollo: funcional.
- Acceso al endpoint sin JWT: rechazado.

Prueba visual:

Consulta realizada desde React sobre cobertura rural
de Aragón.

Resultado: SEUR, con cita al documento oficial
`trackflow-carrier-coverage.es.md`, fragmento 1.

## 10. Ejecución y dependencias

Para el entorno de Codespaces:

- Qdrant debe estar disponible en el puerto 6333.
- FastAPI utiliza el puerto 8000.
- Vite utiliza el puerto 3001.
- El frontend reenvía las consultas al backend.
- Los secretos deben configurarse como variables
  de entorno, nunca en el repositorio.

Variables relevantes:

- `QDRANT_URL`
- `GEMINI_API_KEY`
- `SECRET_KEY`
- `VITE_API_PROXY_TARGET` para desarrollo local.

El archivo `services/api/.env` debe permanecer
excluido de Git.

Los servicios iniciados manualmente pueden detenerse
al reiniciar Codespaces y necesitar un nuevo arranque.

## 11. Limitaciones conocidas

- El umbral vectorial no garantiza fidelidad semántica.
- Las protecciones comerciales cubren riesgos identificados,
  no todas las posibles contradicciones.
- Las métricas disponibles corresponden a conjuntos
  pequeños de evaluación.
- La prueba visual confirma una consulta positiva,
  no todas las rutas posibles del asistente.
- Debe completarse una auditoría final de regresiones,
  integración y seguridad antes de la entrega.

## 12. Estado de entrega

Implementación y pruebas funcionales principales
completadas.

Pendiente al redactar este documento:

- Auditoría final.
- Revisión de requisitos académicos.
- Validación final de Git y secretos.
- Commit, push, pull request y entrega autorizada.

## 13. Inicialización reproducible

### 13.1. Requisitos

- Repositorio completo, incluidos los cuatro documentos
  de `docs/company-knowledge-base/`.
- Python 3.12 y gestor `uv`.
- Docker y Docker Compose.
- Conectividad para descargar las dependencias y el
  modelo de embeddings durante la primera ejecución.

Ejecutar los siguientes comandos desde la raíz
del repositorio.

### 13.2. Iniciar Qdrant

```bash
docker compose up -d --no-deps qdrant
curl -fsS http://127.0.0.1:6333/healthz
```

La segunda instrucción debe confirmar que Qdrant
está disponible.

### 13.3. Preparar e indexar la base documental

```bash
export QDRANT_URL=http://127.0.0.1:6333

uv run --project scripts/rag --frozen \
  python scripts/rag/index.py
```

El indexador realiza las siguientes operaciones:

1. Lee los documentos originales del repositorio.
2. Genera los fragmentos.
3. Prepara la colección `trackflow_knowledge`.
4. Calcula embeddings de 384 dimensiones.
5. Inserta los vectores y sus metadatos.
6. Comprueba los resultados de la indexación.

Para el corpus utilizado en esta entrega se esperan
16 fragmentos, cuatro por documento.

Los identificadores de puntos son determinísticos.
La indexación incluye controles para detectar cantidades
de puntos inesperadas antes de actualizar el corpus.

**Importante:** Qdrant no se indexa automáticamente
por el simple hecho de iniciar Docker Compose.

### 13.4. Variables de entorno

Para ejecutar la API deben estar disponibles en el
proceso correspondiente:

- `QDRANT_URL`: dirección de Qdrant.
- `GEMINI_API_KEY`: credencial para generación.
- `SECRET_KEY`: clave para autenticación JWT.

Direcciones de Qdrant según el entorno:

- Python ejecutado en Codespaces:
  `http://127.0.0.1:6333`
- Backend dentro de Docker Compose:
  `http://qdrant:6333`

Para el servidor Vite ejecutado directamente en
Codespaces, configurar:

`VITE_API_PROXY_TARGET=http://127.0.0.1:8000`

El archivo `services/api/.env` debe permanecer excluido
del repositorio. Guardar una variable en ese archivo
no garantiza que un proceso la cargue automáticamente:
debe suministrarse mediante el mecanismo de configuración
utilizado para iniciar dicho proceso.

Nunca incorporar credenciales reales en documentos,
commits o imágenes Docker.

### 13.5. Consideraciones de Docker

El Dockerfile del backend incluye el código Python
del motor RAG, pero no incorpora los documentos
oficiales al contexto de ejecución de la imagen.

Por ello, la inicialización documentada utiliza
los archivos originales disponibles en el repositorio
para cargar Qdrant desde el entorno anfitrión.

Los datos vectoriales persisten en el volumen
Docker `qdrant-data`.

### 13.6. Reinicios de Codespaces

Después de reiniciar Codespaces, comprobar nuevamente
el estado de Qdrant, FastAPI y Vite.

Los procesos iniciados manualmente pueden detenerse
durante el reinicio. La persistencia de datos no implica
que todos los servicios vuelvan a estar ejecutándose.

### 13.7. Validación

El sistema debe comprobarse mediante:

- Conteo y distribución de fragmentos de Qdrant.
- Tests unitarios del motor RAG.
- Tests de FastAPI.
- Tests y build de React.
- Consultas con citas documentales.
- Pruebas de abstención ante información no respaldada.

La ejecución comprobada durante este desarrollo
no sustituye una prueba independiente en una instalación
completamente nueva.
