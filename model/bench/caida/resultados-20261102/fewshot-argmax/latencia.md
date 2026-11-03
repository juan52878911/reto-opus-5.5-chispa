# Chispa: Caída — latencia por petición de 3 preguntas (100 decisiones por serie, 2 peticiones cada una)

Servidor: `http://127.0.0.1:8090` (modo de decisión `argmax`: no cambia lo que se pide, solo se anota)

| caché de torres | p50 ms | p95 ms | p99 ms | ms servidor (media) | decisiones/s | con escalada | errores |
|---|---|---|---|---|---|---|---|
| fria | 294.06 | 384.37 | 453.275 | 299.957 | 3.3 | 100 | 0 |
| caliente | 58.736 | 64.889 | 66.144 | 58.25 | 16.8 | 100 | 0 |

Cliente único y en serie: `decisiones/s` = decisiones/segundo. Fría = descripciones nunca vistas (torres al vuelo); caliente = la misma petición repetida.
