# Chispa: Caída — latencia por petición de 3 preguntas (100 por serie)

Servidor: `http://127.0.0.1:8090`

| caché de torres | p50 ms | p95 ms | p99 ms | ms servidor (media) | decisiones/s | con escalada | errores |
|---|---|---|---|---|---|---|---|
| fria | 315.944 | 371.464 | 406.988 | 318.749 | 3.1 | 100 | 0 |
| caliente | 63.256 | 70.314 | 79.349 | 64.246 | 15.4 | 100 | 0 |

Cliente único y en serie: `decisiones/s` = peticiones/segundo. Fría = descripciones nunca vistas (torres al vuelo); caliente = la misma petición repetida.
