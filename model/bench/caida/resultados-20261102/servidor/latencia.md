# Chispa: Caída — latencia por petición de 3 preguntas (100 por serie)

Servidor: `http://127.0.0.1:8090`

| caché de torres | p50 ms | p95 ms | p99 ms | ms servidor (media) | decisiones/s | con escalada | errores |
|---|---|---|---|---|---|---|---|
| fria | 290.267 | 340.202 | 386.184 | 295.706 | 3.4 | 100 | 0 |
| caliente | 57.868 | 65.675 | 129.165 | 60.165 | 16.4 | 100 | 0 |

Cliente único y en serie: `decisiones/s` = peticiones/segundo. Fría = descripciones nunca vistas (torres al vuelo); caliente = la misma petición repetida.
