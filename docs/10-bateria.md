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
| `exactitud` | acierto de la mejor respuesta (si escaló sin respuesta, el argmax de `probs`); en `multi`, subconjunto exacto. Un error de petición cuenta como fallo |
| `f1_macro` | F1 macro sobre las clases `(esquema, opción)` con soporte; en `multi`, cada opción es una clase |
| `ece` | error de calibración esperado, 10 cubos de igual ancho `(k/10, (k+1)/10]` sobre la confianza de la mejor respuesta (en `multi`, una decisión por opción: p si activa, 1−p si no) |
| `cobertura` | fracción de decisiones que un umbral único sobre la confianza acepta con precisión ≥ `objetivo` (0,95); 0 si ninguno lo logra |
| `escalado` | fracción de filas con `escalate` |
| `errores` | fracción de peticiones fallidas (transporte, 4xx/5xx) |
| `p50_ms`, `p99_ms` | latencia de cliente, extremo a extremo |
| `mae` | solo conjuntos con `score`: error medio en niveles |
| `estabilidad`, `delta_conf`, `delta_conf_p95` | con `--robustez`: fracción de decisiones que no cambian con la variante, y media y p95 de \|Δ confianza\| (también por transformación, en `transformaciones`) |

## Línea base y umbrales
La línea base es el JSON del reporte sin filas (`--guardar-linea-base`); el `.json` de `--salida` sirve igual. Se compara cada métrica que la línea base trae, en `global`, `tipos`, `grupos` y `conjuntos`. El **umbral es el empeoramiento máximo tolerado**: absoluto (0,01 = un punto) salvo `p50_ms` y `p99_ms`, que son relativos (0,5 = +50 %) y además deben empeorar más de 1 ms (el ruido de un milisegundo no es una regresión). Mejora la exactitud, el F1 y la cobertura al subir; el resto, al bajar.

| Métrica | Umbral por defecto |
|---|---|
| exactitud, f1_macro | 0,01 |
| cobertura, ece, estabilidad | 0,02 |
| escalado | 0,03 |
| errores | 0 |
| mae, delta_conf | 0,05 |
| p50_ms, p99_ms | 0,5 y 1,0 (relativos) |

Se pisan en el manifiesto (`umbrales`) y con `--umbrales FICHERO.json` (misma forma; `por_conjunto` fija umbrales de un conjunto; `null` desactiva una métrica). Una clave desconocida es un error: una errata no apaga la puerta. Falla también un conjunto de la línea base que no se mide; con `--solo NOMBRE` (repetible) o conjuntos opcionales omitidos la comparación es parcial (solo conjuntos medidos) y lo avisa. Si `n` difiere de la línea base, avisa: no es la misma muestra.

## Robustez
`--robustez` convierte cada fila en un caso completo (`{texto, pregunta, kind, opciones[{id, description}], etiqueta}`) y pide a `chispa.variantes.generar(caso, tipos, semilla=0)` una variante por transformación: `permutar` (orden de opciones), `renombrar` (ids opacos), `parafrasear` (la pregunta), `erratas`, `mayusculas`, `mezcla` (español/inglés) y `largo`. Manda cada variante con sus opciones y compara su decisión con la original usando `variantes.estabilidad`, que traduce los ids con el `mapa` de la variante (en `multi`, el conjunto de opciones activas, traducido igual). `permutar` y `renombrar` solo se aplican a `choice` y `multi`: los ids de `noul` (`false`/`true`) y de `score` (niveles) significan algo. Una variante que no cambia nada (p. ej. un texto ya en mayúsculas) no cuenta; una con error cuenta como decisión cambiada.

El informe da, por conjunto, tipo, grupo y global, `estabilidad` (% de decisiones que no cambian), `delta_conf` (media de \|confianza variante − original\|) y `delta_conf_p95`; y una tabla «Robustez por transformación» (global y por conjunto). Se perturban hasta `--robustez-max` filas por conjunto (200, a paso fijo). Si el módulo no existe, avisa por stderr y sigue sin esas métricas.

**Mínimo de estabilidad (opcional).** Una línea base puede traer `estabilidad_min` (fracción, p. ej. `0.9`): arriba del todo vale para `global` y cada conjunto, y dentro de una entrada (`global`, un conjunto, tipo o grupo) vale solo para ella. Si la estabilidad medida baja de ese mínimo, o falta, la puerta falla, aunque la línea base no haya empeorado. Se añade a mano al JSON de la línea base.

## Informe
`--salida informe` escribe `informe.md` (tablas por global, tipo, grupo y conjunto, y el veredicto frente a la línea base) e `informe.json`; con `--filas`, también la predicción de cada fila. Sin `--salida` imprime el markdown. Los errores y avisos van por stderr. Probada con servidores falsos en `sdk/python/tests/test_bateria.py` (en robustez, uno estable y otro que cambia con la permutación).
