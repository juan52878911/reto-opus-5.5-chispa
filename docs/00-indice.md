# Documentación de Chispa

Chispa es un clasificador tipado (`choice`, `score`, `noul`) de bajo coste y de propósito general. Decide sobre un esquema
que no ha visto, en zero-shot o con pocos ejemplos, en CPU (x86, ARM y móvil), con una cascada de capas. Escala a otra capa o a
una persona cuando no está segura. massive, clinc150 y las demás tareas son benchmarks, no el objetivo.

Esta documentación es para quien integra Chispa. El detalle de desarrollo está en los README de cada carpeta.

| Documento | Qué cuenta |
|---|---|
| [01-que-es.md](01-que-es.md) | Propósito general; preguntas `choice`, `noul` y `score`; los tres modos; la cascada; cuándo escala |
| [02-inicio-rapido.md](02-inicio-rapido.md) | Un esquema nuevo: zero-shot, few-shot (k = 5) y `--conjunta`, hasta una petición `curl` |
| [03-api.md](03-api.md) | `/v1/decide`, `/healthz`, `/metrics` y sus límites |
| [04-formato-chispa.md](04-formato-chispa.md) | El fichero `.chispa` v3 y sus secciones |
| [05-sdks.md](05-sdks.md) | Python, Android, iOS y WASM |
| [06-despliegue.md](06-despliegue.md) | Imagen OCI, ONNX Runtime, tokenizador y AWS |
| [07-rendimiento-y-limites.md](07-rendimiento-y-limites.md) | Benchmarks por modo, límites del zero-shot y excepciones de G2 |
| [08-esquemas-nuevos.md](08-esquemas-nuevos.md) | Qué pasa con un esquema sin `.chispa` y cómo funciona L2 al vuelo con `TORR` y qué falta medir |

Convención: cada cifra lleva enlace a su fuente. Si no hay enlace, no es una cifra medida.
