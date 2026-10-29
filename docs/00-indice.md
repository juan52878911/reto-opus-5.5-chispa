# Documentación de Chispa

Chispa es un clasificador tipado (`choice`, `score`, `noul`) de bajo coste y de propósito general. Decide sobre un esquema
que no ha visto, en zero-shot o con pocos ejemplos, en CPU (x86, ARM y móvil), con una cascada de capas. Escala a otra capa o a
una persona cuando no está segura. massive, clinc150 y las demás tareas son benchmarks, no el objetivo.

Esta documentación es para quien integra Chispa. El detalle de desarrollo está en los README de cada carpeta.

| Documento | Qué cuenta |
|---|---|
| [01-que-es.md](01-que-es.md) | Propósito general; preguntas `choice`, `noul` y `score`; los tres modos; la cascada; cuándo escala |
| [02-inicio-rapido.md](02-inicio-rapido.md) | Un esquema nuevo: zero-shot, few-shot (k = 5, con soporte opcional `--shrinkage-lambda`), `--torre` y `--conjunta`, hasta una petición `curl` |
| [03-api.md](03-api.md) | `/v1/decide`, `/healthz`, `/metrics` y sus límites |
| [04-formato-chispa.md](04-formato-chispa.md) | El fichero `.chispa` v3 y sus diez secciones, con `TORR` y `SOPL1` |
| [05-sdks.md](05-sdks.md) | Python (wheel y extras), Android e iOS (proveedores de ORT, torre al vuelo), núcleo móvil, WASM |
| [06-despliegue.md](06-despliegue.md) | Compilar con ORT, flags, imagen OCI, imagen de kindling, arnés de carga y AWS |
| [07-rendimiento-y-limites.md](07-rendimiento-y-limites.md) | Benchmarks por modo, límites del zero-shot, carga y excepciones de G2 |
| [08-esquemas-nuevos.md](08-esquemas-nuevos.md) | Esquema sin `.chispa`: zero-shot con torre al vuelo (`TORR`), few-shot con soporte opcional (`SOPL1`), τ y qué falta medir |

## Piezas del repo y su README
| Pieza | Qué es | README |
|---|---|---|
| Formato `.chispa` v3 | contenedor con L0, L1, L2, `ESQUEMAS`, `CALIB`, `CONJ`, `L0TF`, `TORR`, `SOPL1` | [`format/chispa3`](../format/chispa3/README.md) |
| Servidor | `chispa-server`, cascada, ORT, tokenizador | [`server`](../server/README.md) |
| Torre de L2 al vuelo | `server/torre`, ORT real sobre la sección `TORR` | [`server/torre`](../server/torre/README.md) |
| Especificación del API | `server/api/openapi.yaml` | [`openapi.yaml`](../server/api/openapi.yaml) |
| Arnés de carga | `server/carga`: `textos-es-co.txt`, `esquemas-carga.json`, `correr.sh` | [`server/carga`](../server/carga/README.md) |
| Imagen OCI con ORT | `server/deploy`, receta de AWS | [`server/deploy`](../server/deploy/README.md) |
| Imagen de kindling | `deploy/kindling`: `imagen-cpu` e `imagen-ort` | [`deploy/kindling`](../deploy/kindling/README.md) |
| SDK de Python | cliente, `chispa train`, wheel y extras | [`sdk/python`](../sdk/python/README.md) |
| Núcleo móvil | `chispamovil` (gomobile) | [`sdk/movil`](../sdk/movil/README.md) |
| SDK de Android | Kotlin, `ProveedorOrt`, demo con «Medir» | [`sdk/android`](../sdk/android/README.md) |
| SDK de iOS | Swift, sin compilar | [`sdk/ios`](../sdk/ios/README.md) |
| Demo WASM | L1 recortado en el navegador, arnés de latencia | [`demo/wasm`](../demo/wasm/README.md) |
| Kit de piloto | guía, plantillas, datos y consentimiento, métrica | [`pilotos`](../pilotos/README.md) |
| Audio | diseño de la fase 5, sin modelos ni medidas | [`audio/DISENO.md`](../audio/DISENO.md) |
| L1 y tokenizador | `runtime/l1`, `runtime/tok` | [`runtime/l1`](../runtime/l1/README.md), [`runtime/tok`](../runtime/tok/README.md) |
| Modelo L2 | entrenamiento, calibración, exportación | [`model/l2`](../model/l2/README.md) |

Convención: cada cifra lleva enlace a su fuente. Si no hay enlace, no es una cifra medida.
