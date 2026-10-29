# OWASP — F3-AUTH-001 — AFTER

## Corrección 1: JWT fuera de URL WebSocket
El frontend envía el JWT mediante un mensaje inicial authenticate, no como parámetro de URL.
El backend rechaza conexiones que incluyan token en la URL.

## Corrección 2: Validación de Origin
El backend comprueba Origin antes de aceptar la conexión.
Los orígenes autorizados se configuran mediante FRONTEND_URL y WS_ALLOWED_ORIGINS.
Las conexiones con Origin externo no autorizado se rechazan.

## Evidencia AFTER — GO F3V
Pruebas negativas y Origin: 9 passed in 5.18s.
Regresión WebSocket completa: 26 passed in 11.72s.
Total: 35 pruebas aprobadas, cero fallidas, en dos ejecuciones de pytest.

## Limitaciones pendientes
La validación se realizó localmente, no en producción.
Los dominios legítimos deben configurarse explícitamente.
Las conexiones sin Origin siguen permitidas, pero requieren JWT válido.
El límite de 4096 caracteres se comprueba después de recibir el mensaje; falta verificar el límite ASGI.
Debe utilizarse WSS/HTTPS en entornos no locales.

## Estado
Corrección local verificada. Validaciones complementarias y entrega final pendientes.
