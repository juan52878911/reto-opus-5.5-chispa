# Documentación de Chispa

Chispa decide preguntas tipadas sobre un texto, en CPU, con una cascada de capas. Escala a otra capa o a una persona
cuando no está segura.

Esta documentación es para quien integra Chispa. El detalle de desarrollo está en los README de cada carpeta.

| Documento | Qué cuenta |
|---|---|
| [01-que-es.md](01-que-es.md) | Preguntas `choice`, `noul` y `score`; la cascada; cuándo escala |
| [02-inicio-rapido.md](02-inicio-rapido.md) | De 50 ejemplos por clase a una petición `curl` |
| [03-api.md](03-api.md) | `/v1/decide`, `/healthz`, `/metrics` y sus límites |
| [04-formato-chispa.md](04-formato-chispa.md) | El fichero `.chispa` v3 y sus secciones |
| [05-sdks.md](05-sdks.md) | Python, Android, iOS y WASM |
| [06-despliegue.md](06-despliegue.md) | Imagen OCI, ONNX Runtime, tokenizador y AWS |
| [07-rendimiento-y-limites.md](07-rendimiento-y-limites.md) | Cifras medidas y excepciones de G2 |
| [08-esquemas-nuevos.md](08-esquemas-nuevos.md) | Qué pasa con un esquema sin `.chispa` y qué falta para L2 zero-shot |

Convención: cada cifra lleva enlace a su fuente. Si no hay enlace, no es una cifra medida.
