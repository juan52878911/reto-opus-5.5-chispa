# Batería de regresión: la puerta de cada cambio de modelo

`chispa evaluar --bateria MANIFIESTO` mide un `.chispa` (o un servidor ya en marcha) sobre varios conjuntos a la vez y **sale con código ≠ 0 si alguna métrica empeora más que su umbral** frente a una línea base. Úsala como puerta: ningún modelo nuevo (`.chispa`, calibración, τ) entra sin pasarla. Solo biblioteca estándar.

```
# contra un .chispa: arranca chispa-server en un puerto libre de loopback y lo apaga al acabar
python -m chispa evaluar --bateria ejemplos/bateria.json --modelo m.chispa --servidor ./chispa-server --linea-base base.json --salida informe
# contra un servidor que ya corre
python -m chispa evaluar --bateria ejemplos/bateria.json --url http://127.0.0.1:8090 --linea-base base.json
# fijar (o renovar) la línea base
python -m chispa evaluar --bateria ejemplos/bateria.json --modelo m.chispa --guardar-linea-base base.json
```

Códigos de salida: **0** bien (o sin `--linea-base`), **1** una métrica empeora más que su umbral o falta un conjunto de la línea base, **2** manifiesto, datos, umbrales o servidor mal puestos. Con `--linea-base` y `--guardar-linea-base` a la vez, la línea base nueva solo se escribe si la comparación pasa.

## Manifiesto
JSON. Las rutas aceptan `$VAR` y `${VAR}` y, si son relativas, cuelgan de la carpeta del manifiesto. Los datos no viajan en el repo: el manifiesto de ejemplo es `sdk/python/ejemplos/bateria.json` (usa `JEVBENCH_DIR`, `CHISPA_DATOS` y `CHISPA_REPO`).

```json
{"nombre": "bateria-chispa", "objetivo": 0.95,
 "umbrales": {"exactitud": 0.01, "p99_ms": 1.0, "por_conjunto": {"jevbench": {"exactitud": 0.02}}},
 "conjuntos": [
   {"nombre": "jevbench", "ruta": "${JEVBENCH_DIR}", "formato": "jevbench", "tipo": "mixto", "grupo": "jevbench"},
   {"nombre": "massive", "ruta": "${CHISPA_DATOS}/massive/test.jsonl", "tipo": "choice", "grupo": "prueba"},
   {"nombre": "massive-nv", "ruta": "${CHISPA_DATOS}/no_vistas/massive.jsonl", "grupo": "no_visto", "opcional": true}]}
```

Por conjunto: `nombre` (único) y `ruta` obligatorios; `formato` (`auto` por defecto, `filas` o `jevbench`), `tipo` (`choice|noul|score|multi|mixto`; si no es `mixto`, una fila de otro tipo es un error), `grupo` (etiqueta para agregar: `jevbench`, `prueba`, `no_visto`…), `split` (`test` por defecto; las filas con otro `split` se saltan, las que no lo traen, como JevBench, entran; `null` = todas), `limite` (primeras N filas, para pruebas de humo) y `opcional` (si falta la ruta o la variable, se omite con aviso; sin él, es un error).

- **Filas**: JSONL en el formato de `model/esquema.md` (`id`, `tipo`, `pregunta`, `texto`, `opciones`, `descripciones`, `etiqueta`). Cada fila lleva su pregunta y opciones, así que un conjunto puede mezclar esquemas. En `multi`, `etiqueta` es una lista (o `a|b`).
- **JevBench crudo**: el clon, su `datasets/public/` o un `.jsonl`; se convierte como en `model/evaluacion/jevbench.py` (noul no→false/yes→true; score nivel + 1). El SDK copia lo mínimo del formato del harness de JevBench (https://github.com/fstandhartinger/jevbench, licencia MIT) y no importa `model/`.
- Cada fila va a `/v1/decide` como una petición, con las descripciones de **todas** las opciones (también de `true/false` y de los niveles de score), como el arnés de `model/`.

## Métricas
Por conjunto, por tipo, por grupo y en global (`n` y las siguientes), todas en [0, 1] salvo la latencia:

| Métrica | Qué es |
|---|---|
| `exactitud` | **(1)** acierto del argmax de `probs` sobre todas las filas con probs, escaladas o no (lo mismo que mide `servidor.py`); en `multi`, subconjunto exacto de las opciones con p ≥ 0,5. Las filas sin probs (error, o escaló sin ellas) no entran: se cuentan aparte en `sin_probs`. Puerta de regresión |
| `exactitud_contestada` | **(2)** acierto de la respuesta sobre lo que la cascada contestó (sin escalar); vacía si todo escaló. Puerta de regresión |
| `exactitud_estricta` | **(4)** sobre todas las filas, con lo escalado y los errores como fallo. Informativa: no es puerta (un `tau_escalate_l2` alto la hunde sin que el modelo empeore) |
| `sin_probs` | fracción de filas sin error y sin `probs` (no se puede medir el argmax); si es alta, `exactitud` no representa al conjunto |
| `incompletas` | fracción de filas que escalaron porque una capa falló o se quedó sin presupuesto y ninguna otra opinó (`escalate_reason` `incompleta` o `sin_presupuesto_torres`; con un servidor que expone `capas` en `/healthz`, escalar sin motivo también cuenta aquí). No es «nadie opinó» y no dispara la alerta de torre; sí la de incompletas (abajo) |
| `sin_presupuesto_torres` | subconjunto de `incompletas`: filas con `escalate_reason` `sin_presupuesto_torres` (L2 agotó `max_torres_nuevas` o `torres_por_segundo`; si otra capa además falló por error o plazo, el motivo es `incompleta`) |
| `nadie_opino` | fracción de filas que escalaron porque **ninguna capa opinó** (`escalate_reason` `sin_opinion` o `score_ids_no_validos`; solo con un servidor antiguo —sin `capas` en `/healthz`— y sin `escalate_reason`, escalar sin probs). No es «confianza baja»: es que el modelo no puede decidir ese esquema |
| `baja_confianza` | fracción de filas que escalaron con alguna capa opinando pero sin llegar a su τ (traen probs y entran en `exactitud`) |
| `f1_macro` | F1 macro sobre las clases `(esquema, opción)` con soporte; en `multi`, cada opción es una clase |
| `ece` | error de calibración esperado, 10 cubos de igual ancho `(k/10, (k+1)/10]` sobre la confianza de la mejor respuesta (en `multi`, una decisión por opción: p si activa, 1−p si no) |
| `cobertura` | **(3)** fracción de decisiones que un umbral único sobre la confianza acepta con precisión ≥ `objetivo` (0,95); 0 si ninguno lo logra |
| `escalado` | fracción de filas con `escalate` |
| `errores` | fracción de peticiones fallidas (transporte, 4xx/5xx) |
| `p50_ms`, `p99_ms` | latencia de cliente, extremo a extremo |
| `mae` | solo conjuntos con `score`: error medio en niveles |
| `estabilidad`, `delta_conf`, `delta_conf_p95` | con `--robustez`: fracción de decisiones que no cambian con la variante, y media y p95 de \|Δ confianza\| (también por transformación, en `transformaciones`) |

## Línea base y umbrales
La línea base es el JSON del reporte sin filas (`--guardar-linea-base`); el `.json` de `--salida` sirve igual. Se compara cada métrica que la línea base trae, en `global`, `tipos`, `grupos` y `conjuntos`. El **umbral es el empeoramiento máximo tolerado**: absoluto (0,01 = un punto) salvo `p50_ms` y `p99_ms`, que son relativos (0,5 = +50 %) y además deben empeorar más de 5 ms, y solo se comparan con al menos 30 muestras (`n`) en la corrida y en la línea base (si no, avisa): el ruido de unos milisegundos en un servidor local no es una regresión. Mejora la exactitud, el F1 y la cobertura al subir; el resto, al bajar.

| Métrica | Umbral por defecto |
|---|---|
| exactitud, exactitud_contestada, f1_macro | 0,01 |
| cobertura, ece, estabilidad | 0,02 |
| escalado | 0,03 |
| errores | 0 |
| mae, delta_conf | 0,05 |
| p50_ms, p99_ms | 0,5 y 1,0 (relativos; además > 5 ms y n ≥ 30) |

Se pisan en el manifiesto (`umbrales`) y con `--umbrales FICHERO.json` (misma forma; `por_conjunto` fija umbrales de un conjunto; `null` desactiva una métrica). Una clave desconocida es un error: una errata no apaga la puerta. Falla también un conjunto de la línea base que no se mide; con `--solo NOMBRE` (repetible) la comparación es parcial (solo conjuntos medidos) y lo avisa.

**Opcionales ausentes y conjuntos distintos.** Un conjunto opcional sin datos no hace parcial la corrida: se mide lo que existe y el reporte lleva `opcionales_ausentes` (lista). Al comparar: un conjunto medido que no está en la base avisa «nuevo, sin base»; uno de la base que falta en la corrida *y* figura en sus `opcionales_ausentes` avisa y no falla (si falta sin estar declarado ausente, falla). Global, tipos y grupos solo se comparan cuando el conjunto de conjuntos medidos coincide con el de la base; si no, avisa y compara solo por conjunto, así un conjunto ausente nunca tapa una regresión de los presentes, que se comparan igual. Si `n` difiere de la línea base, avisa: no es la misma muestra.

**Línea base completa.** `--guardar-linea-base` se niega (código 2) con `--solo`: una base parcial dejaría pasar regresiones en lo que no midió. El reporte de una corrida `--solo` lleva `"parcial": true` y la comparación lo rechaza como línea base de la puerta completa. Con opcionales ausentes (sin `--solo`) sí guarda, y registra `opcionales_ausentes`. Una base antigua marcada `parcial` por opcionales omitidos se usa con aviso si sus conjuntos coinciden con los medidos. Al guardar con `--linea-base` (o sobre una ruta que ya existe) se conserva el `estabilidad_min` de la base anterior.

## Robustez
`--robustez` convierte cada fila en un caso completo (`{texto, pregunta, kind, opciones[{id, description}], etiqueta}`) y pide a `chispa.variantes.generar(caso, tipos, semilla=0)` una variante por transformación: `permutar` (orden de opciones), `renombrar` (ids opacos), `parafrasear` (la pregunta), `erratas`, `mayusculas`, `mezcla` (español/inglés) y `largo`. Manda cada variante con sus opciones y compara su decisión con la original usando `variantes.estabilidad`, que traduce los ids con el `mapa` de la variante (en `multi`, el conjunto de opciones activas, traducido igual). `renombrar` solo se aplica a `choice` y `multi`, y `permutar` a `choice`, `multi` y `score`: los ids de `noul` (`false`/`true`) y de `score` (niveles 1..K) significan algo, así que no se renombran. En `score`, `permutar` es segura con ids 1..K (el servidor lee los niveles por su valor); con otros ids el servidor no opina y la variante no aplica (identidad, no cuenta). Una variante que no cambia nada (p. ej. un texto ya en mayúsculas) no cuenta; una con error cuenta siempre como decisión cambiada.

El informe da, por conjunto, tipo, grupo y global, `estabilidad` (% de decisiones que no cambian), `delta_conf` (media de \|confianza variante − original\|) y `delta_conf_p95`; y una tabla «Robustez por transformación» (global y por conjunto). Se perturban hasta `--robustez-max` filas por conjunto (200, a paso fijo). Si el módulo no existe, avisa por stderr y sigue sin esas métricas.

**Mínimo de estabilidad (opcional).** Una línea base puede traer `estabilidad_min` (fracción, p. ej. `0.9`): arriba del todo vale para `global` y cada conjunto, y dentro de una entrada (`global`, un conjunto, tipo o grupo) vale solo para ella. Si la estabilidad medida baja de ese mínimo, o falta, la puerta falla, aunque la línea base no haya empeorado. Se añade a mano al JSON de la línea base y `--guardar-linea-base` lo conserva al regenerarla.

## Incompletas: alerta

Si `incompletas` supera el 20 % (global o por conjunto; `UMBRAL_INCOMPLETAS` en `bateria.py`) el informe añade una alerta en «Alertas» (y en `alertas` del JSON) con la causa probable: presupuesto de torres agotado si hay filas `sin_presupuesto_torres` (preguntas con más opciones nuevas que `max_torres_nuevas`, o `torres_por_segundo` bajo) o, si no, fallo/plazo de una capa. Mira `chispa_torres_presupuesto_agotado_total` y `chispa_capa_no_opina_total{capa,causa}` en `/metrics`. Como el servidor cachea las torres calculadas antes del corte, repetir la corrida suele avanzar. No cambia `ok`.

## Torre al vuelo desactivada: alerta

Si `/healthz` trae `torre_al_vuelo_motivo` (hoy `texto_torre_inconsistente`: `META.texto_torre` y `TORR` del `.chispa` no coinciden y el servidor cargó el modelo sin torre al vuelo), el informe añade en «Alertas» una línea `ALERTA: el servidor desactivó la torre al vuelo (…)` (y en `alertas` del JSON; `capacidades_servidor` lleva el motivo). No cambia `ok`. Reconstruye el `.chispa` con `chispa train`.

## «Nadie opinó»: aviso y alerta
Un `.chispa` construido sin `--torre` (y sin L0 ni L1) escala todo sin probs ante esquemas que no trae, y `exactitud` ignora esas filas (solo salen en `sin_probs`). Para que no pase en silencio:
- **Al arrancar** la batería lee `GET /healthz` (`capas` y `torre_al_vuelo`, ver [03-api.md](03-api.md#get-healthz)); si no hay torre al vuelo ni L1, avisa (stderr y `aviso`) de que los esquemas nuevos del manifiesto escalarán sin probs. **No** comprueba qué esquemas trae el `ESQUEMAS` del `.chispa` frente a los del manifiesto: es un aviso conservador. Con un servidor anterior (sin esos campos) no avisa.
- **En el informe**, `nadie_opino` y `baja_confianza` van en columnas aparte. Si `nadie_opino` supera el 50 % (global o por conjunto; `UMBRAL_SIN_OPINION` en `bateria.py`) el informe añade la sección «Alertas» con la causa probable (falta de torre, capas sin modelo, tipo no soportado o ids de score) y el reporte JSON la lleva en `alertas` (lista; vacía si no hay) junto con `capacidades_servidor`. La alerta **no** cambia `ok`: la puerta sigue siendo la línea base. La causa fina por capa está en `chispa_capa_no_opina_total{capa,causa}` de `/metrics`.
- **En `chispa train`** (donde nace el problema): sin `--torre`, resume las capas del `.chispa` (`capas del .chispa: L0 no, L1 sí, L2 sí, torre al vuelo (TORR) no`) y, si falta `TORR`, avisa de que no decidirá esquemas nuevos en L2. Se eligió **avisar, no fallar**, tampoco con `--perfil servidor` (un `.chispa` solo con ESQUEMAS es legítimo); `--sin-torre` declara que es a propósito y silencia el aviso. Con `--ckpt`, si junto al checkpoint hay un `torre.onnx` (o `torre-int8.onnx`) se incluye por defecto (`--sin-torre` lo evita).
- Con torre, un esquema nuevo que no llega al τ escala **con probs** (`baja_confianza`): entra en `exactitud` y no dispara la alerta.

## Informe
El informe incluye la sección «CALIB del servidor» (leída de `/metrics`, con `--tok` o `CHISPA_TOKEN_METRICAS` si está protegido; `calib_servidor` en el JSON) y un AVISO, también por stderr, si alguna capa decidió con la CALIB por defecto.

`--salida informe` escribe `informe.md` (tablas por global, tipo, grupo y conjunto, y el veredicto frente a la línea base) e `informe.json`; con `--filas`, también la predicción de cada fila. Sin `--salida` imprime el markdown. Los errores y avisos van por stderr. Probada con servidores falsos en `sdk/python/tests/test_bateria.py` (en robustez, uno estable y otro que cambia con la permutación).

## Latencia por muestras, CALIB por corrida, textos largos y línea base corrupta
- **Latencia**: p50/p99 salen solo de las filas con respuesta; el reporte guarda `n_latencia` y la puerta no los juzga con menos de 30 muestras de latencia (en la base o en la corrida), no con menos de 30 filas. Las bases antiguas sin `n_latencia` usan `n`.
- **Línea base anterior a las métricas de escalado** (sin `exactitud_contestada`): no falla; avisa y pide regenerarla. Su `exactitud` contaba lo escalado sin respuesta como fallo; la actual es el argmax de `probs`.
- **CALIB**: se lee `/metrics` antes de la pasada y después de todo (robustez incluida); `calib_servidor.defecto` y el aviso son la diferencia, no los contadores acumulados del servidor. Si no se pudo leer la lectura previa, el contador es el acumulado y el informe lo dice (`defecto_acumulado`).
- **`--agrupar`**: las filas del mismo conjunto y el mismo texto viajan en una sola petición (una pregunta por fila, ids `q0…`), como un cliente que agrupa preguntas; sin él, una pregunta por petición. Los grupos se cortan en lotes de a lo sumo 256 preguntas (`MaxPreguntas` del servidor) y por debajo de 1 MiB de cuerpo, y conjuntos distintos con el mismo texto no comparten petición. Un fallo de la petición lo es de todas sus filas del lote. La latencia de una petición se cuenta una vez (`n_latencia` cuenta peticiones, no filas). La línea base guarda `agrupado`; si el modo de la corrida y el de la base difieren, no se comparan p50/p99 y se avisa. Sirve para poner a prueba el límite de preguntas por petición y el presupuesto de un texto largo con varias preguntas (`max_trozos`). **No detecta el reparto del presupuesto entre textos distintos de una misma petición**: cada petición agrupada lleva un solo texto, así que ese texto recibe el cupo completo; el caso en que el texto B se queda con una ventana porque A gastó el cupo (el servidor cobra una vez por texto y por petición) no lo genera esta batería.
- **Textos largos (sintético)**: `python sdk/python/ejemplos/bateria_textos_largos.py DIR --textos 6 --preguntas 4 --kb 24` crea `DIR/manifiesto.json` y `largos.jsonl` (textos de ~24 KB, 4 preguntas cada uno); córrelo con `chispa evaluar --bateria DIR/manifiesto.json --url … --agrupar`. Sin `--agrupar` no ve los fallos de presupuesto por petición de un texto con varias preguntas. Falta el dorado de servidor (`server/`, fuera de esta zona).
- **`--guardar-linea-base RUTA`**: valida la ruta antes de medir (directorio, carpeta inexistente o sin permiso → código 2 sin correr). Si `RUTA` existe y no es una línea base válida, avisa, la ignora y la sobrescribe.
