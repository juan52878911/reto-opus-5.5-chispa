# Kit de piloto de Chispa para una empresa colombiana

Este kit sirve para que una empresa (una EPS, una ferretería, una tienda en línea…) pruebe Chispa con sus propios mensajes
en 2 a 4 semanas y decida con números si le sirve. Chispa es un clasificador tipado (`choice`, `score`, `noul`) de bajo coste:
recibe un texto y una pregunta con opciones, y devuelve la opción, sus probabilidades y si conviene pasar el caso a una persona
([`docs/01-que-es.md`](../docs/01-que-es.md)).

## Contenido
| Fichero | Para qué |
|---|---|
| [`guia-integracion.md`](guia-integracion.md) | Paso a paso desde cero hasta `/v1/decide` en su sistema (on-prem o nube); los tres modos |
| [`esquemas/`](esquemas) | Plantillas YAML de PQRS, soporte y ventas, con ejemplos de few-shot |
| [`datos-y-consentimiento.md`](datos-y-consentimiento.md) | Checklist de datos y de consentimiento (habeas data) |
| [`metrica.md`](metrica.md) | Cómo se mide el piloto y plantilla del informe final |
| [`operacion.md`](operacion.md) | Runbook: desplegar, configurar, vigilar, actualizar y recuperar `chispa-server` |
| [`checklist-despliegue.md`](checklist-despliegue.md) | Lista de verificación de una página para el despliegue |

## Duración: 4 semanas (2 si ya hay datos etiquetados y un servidor listo)
| Semana | Qué pasa | Entrega |
|---|---|---|
| 0 (antes de empezar) | Acuerdo de datos y consentimiento; se elige 1 o 2 esquemas; el cliente nombra a sus roles | checklist de [`datos-y-consentimiento.md`](datos-y-consentimiento.md) firmado |
| 1 | Servidor levantado, esquema ajustado, modo **zero-shot** sobre mensajes de prueba | `/v1/decide` respondiendo en el entorno del cliente |
| 2 | El cliente etiqueta la muestra (≥ 300 mensajes, ver [`metrica.md`](metrica.md)); modo **few-shot** | muestra etiquetada y primera medición |
| 3 | Segunda medición; si hay ≥ 20 ejemplos por opción, prueba del modo **con datos del cliente** (ver pendientes) | mediciones comparadas por modo |
| 4 | Latencia y coste en su infraestructura; informe final y decisión | informe final ([plantilla](metrica.md#plantilla-de-informe-final)) |

Con 2 semanas se hacen las semanas 1 y 2 y se decide con zero-shot y few-shot.

## Roles
| Rol | Quién | Qué hace |
|---|---|---|
| Patrocinador | Dirección del cliente | Fija el objetivo y decide al final |
| Responsable de datos | Cliente (jurídica o seguridad de la información) | Autorización de tratamiento, anonimización, retención |
| Etiquetador(es) | Cliente (gente que conoce los casos) | Etiqueta la muestra de evaluación; mínimo 2 para medir acuerdo en una parte |
| Integrador | TI del cliente | Despliega el servidor y conecta su sistema |
| Responsable técnico de Chispa | SDK | Arma los `.chispa`, mide y escribe el informe |

## Entregables
1. Un servidor `chispa-server` corriendo en el entorno del cliente, con 1 o 2 esquemas.
2. La muestra etiquetada (queda en el cliente) y el informe de medición por modo.
3. El informe final con la plantilla de [`metrica.md`](metrica.md) y una recomendación: seguir, seguir con cambios o no seguir.

## Criterios de éxito (a acordar antes de empezar)
Los umbrales son del cliente; el repo no trae umbrales de éxito para tareas de empresas colombianas. Sugerencia de punto de partida,
que se fija por escrito en la semana 0:

- **Exactitud / macro-F1** sobre la muestra etiquetada ≥ un valor que el cliente fija. Referencia: lo medido en benchmarks (inglés y español, no es del cliente)
  va de 0,455 en zero-shot a 0,814–0,887 con datos del cliente ([`docs/07-rendimiento-y-limites.md`](../docs/07-rendimiento-y-limites.md#por-modo)).
- **Cobertura** a una precisión objetivo (0,95 por defecto en `chispa train`) ≥ un valor del cliente. Referencia: 0,72–0,80 en massive y clinc150 con la cabeza conjunta (mismo fichero).
- **Tasa de escalado** ≤ 20 % con tráfico normal: objetivo vigente del producto ([`docs/07`](../docs/07-rendimiento-y-limites.md#excepción-2-la-abstención)), **no cumplido** con el τ medido antes de T4.6b.
- **Latencia p99** y **coste por 1.000 decisiones** en la infraestructura del cliente: sin medir en ese entorno. Se miden en la semana 4.

## Pendiente de producto
Se marcan aquí y **no se prometen** al cliente (cada punto se explica donde aparece):

1. **`score` (urgencia) en zero-shot y con k = 5.** L1 sí opina (nivel mediano de la distribución coseno/T, `server/decide/l1.go`), pero su confianza
   baja si la masa se reparte entre niveles lejanos y entonces escala; sin L0 no hay cifra medida
   ([`docs/07`](../docs/07-rendimiento-y-limites.md#zero-shot)). La plantilla trae una variante `choice` (alta/media/baja) que sí funciona.
2. **L2 en esquemas nuevos.** Falta el ONNX real de la torre; sin paridad ni cifra ([`docs/08`](../docs/08-esquemas-nuevos.md#qué-falta)).
3. **Modo con datos del cliente (`--conjunta`).** Necesita un checkpoint de L2 que el repositorio no trae; solo para `choice`
   ([`docs/02`](../docs/02-inicio-rapido.md#4-con-datos-del-cliente---conjunta-modo-avanzado)). Se ofrece solo si SDK lo entrega.
4. **Evaluación sobre datos del cliente con una sola orden.** Lo que hay (`e2e_util.py cliente` + `medir.py`) está escrito para los benchmarks:
   el cliente HTTP de `e2e_util.py` solo manda `choice` y `medir.py` espera un formato propio ([`metrica.md`](metrica.md#cómo-se-mide)). Para `noul` y `score` no hay medición lista.
5. **Coste por 1.000 decisiones y latencia con el modelo y el hardware del cliente:** sin medir.
6. **Español de Colombia, PQRS, EPS, ferretería:** sin medir; las cifras del repo son de benchmarks ([`docs/07`](../docs/07-rendimiento-y-limites.md)).
7. **Salvaguardas de datos en el producto** (enmascarar datos personales, registro de decisiones): el producto no las trae; las hace el cliente antes de llamar a `/v1/decide`.
8. **Operación** (detalle en [`operacion.md`](operacion.md)): recarga del modelo en caliente, apagado ordenado, TLS y autenticación, log de acceso, `/readyz` y métricas de memoria. No existen; el cliente reinicia y pone un proxy delante.
