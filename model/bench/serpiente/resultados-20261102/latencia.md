# Chispa: Serpiente — latencia por decisión (100 por serie, 1 petición cada una)

Servidor: `http://127.0.0.1:8090` (modo de decisión `argmax`: no cambia lo que se pide, solo se anota)

| caché de torres | p50 ms | p95 ms | p99 ms | ms servidor (media) | decisiones/s | con escalada | errores |
|---|---|---|---|---|---|---|---|
| fria | 177.413 | 234.504 | 250.127 | 184.894 | 5.4 | 100 | 0 |
| caliente | 28.734 | 34.655 | 55.652 | 29.165 | 33.4 | 100 | 0 |

Cliente único y en serie. Fría = descripciones nunca vistas; caliente = la misma petición repetida.
