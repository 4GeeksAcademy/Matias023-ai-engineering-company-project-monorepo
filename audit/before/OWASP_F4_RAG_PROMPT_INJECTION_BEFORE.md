# F4-RAG-001 — Prompt injection indirecta

## Evidencia ANTES

Prueba:
`scripts/rag/tests/test_owasp_prompt_injection.py`

Resultado observado en GO F4J:

- `1 failed`
- Un fragmento sintético contenía instrucciones dirigidas al asistente.
- Un generador simulado produjo una respuesta contaminada.
- `RAGService.query()` aceptó dicha respuesta.

## Alcance demostrado

Debilidad reproducible del flujo RAG frente a una
respuesta simulada contaminada por un documento.

No se ejecutó Gemini real.
No se demostró exfiltración.
No se ejecutaron herramientas externas.

## Riesgos adicionales

- Otras formas de prompt injection no están evaluadas.
- El streaming publica tokens provisionales antes de validar.
