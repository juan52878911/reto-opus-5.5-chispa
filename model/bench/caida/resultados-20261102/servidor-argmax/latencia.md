# Chispa: Caída — latencia por petición de 3 preguntas (100 decisiones por serie, 2 peticiones cada una)

Servidor: `http://127.0.0.1:8090` (modo de decisión `argmax`: no cambia lo que se pide, solo se anota)

| caché de torres | p50 ms | p95 ms | p99 ms | ms servidor (media) | decisiones/s | con escalada | errores |
|---|---|---|---|---|---|---|---|
| fria | 390.179 | 456.743 | 466.588 | 391.847 | 2.5 | 100 | 0 |
| caliente | 86.523 | 102.803 | 146.442 | 88.602 | 11.1 | 100 | 0 |

Cliente único y en serie: `decisiones/s` = decisiones/segundo. Fría = descripciones nunca vistas (torres al vuelo); caliente = la misma petición repetida.
