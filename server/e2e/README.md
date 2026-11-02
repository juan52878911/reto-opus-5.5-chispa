# e2e: train → .chispa → chispa-server (ORT) → evaluar

Encadena el flujo de un cliente con **modelos sintéticos**: `chispa train` (zero-shot y few-shot con `--torre` y
`--shrinkage-lambda`) de la ferretería de `docs/02-inicio-rapido.md`, `chispa-server -tags ort -tok`, peticiones con un esquema
que el `.chispa` no trae (torre al vuelo), recarga con SIGHUP bajo carga, `chispa evaluar` y `/metrics`.

**Con modelos sintéticos los números (exactitud, probabilidades, cobertura) no significan calidad**: la prueba verifica
que las piezas encajan (códigos, formas, capas, contadores), no que Chispa clasifique bien.

## Receta
```
. ~/orquestador/herr/env.sh          # Go, venv con numpy/onnxruntime/PyYAML (si `go` no está en el PATH, correr.sh lo carga)
server/e2e/correr.sh                 # desde la raíz del repo; ~1 min; código ≠ 0 si algo falla
```
Variables:
| variable | por defecto | uso |
|---|---|---|
| `CHISPA_ORT_LIB` | `libonnxruntime.so.*` del venv | biblioteca de ONNX Runtime |
| `CHISPA_TOK` | `/tmp/e5.chispa-tok` | tokenizador de e5 (`-tok`) |
| `PUERTO` | `18090` | puerto del servidor A; B usa `PUERTO+1` |
| `TRABAJO`, `MANTENER=1` | `mktemp -d` | directorio de trabajo; con `MANTENER=1` no se borra (logs, `.chispa`, informe) |
| `CC` | `gcc`, o `~/orquestador/herr/zigcc` si no hay gcc | cgo para `-tags ort` |
| `PYTHON` | `python` / `python3` | intérprete (numpy y PyYAML) |

`chispa-server` recibe la ruta de ORT por `CHISPA_ORT_LIB` (o `-ort-lib`) y la usa en L2 y en la torre; el script la exporta tal cual,
sin `LD_LIBRARY_PATH` (ver H1 en [HALLAZGOS.md](HALLAZGOS.md), corregido).

## Pasos y comprobaciones
1. Compila `chispa-server -tags ort` y `gensint`.
2. `gensint` (Go, `gensint/main.go`) escribe un L1 diminuto (formato de `l1Tiny` de `server/decide/l1_test.go`) y un `.chispa` con
   `l2_sintetico.onnx` + ESQUEMAS.
3. `chispa train` zero-shot y few-shot (`datos/ejemplos.csv`, λ=4), ambos con `--torre server/torre/testdata/sintetico.onnx` y
   `--tau-l2-esquema-nuevo 0.5` (sin él, los pesos aleatorios no pasan el τ). Comprueba META/L1/L2/ESQUEMAS/TORR (+SOPL1).
4. **Servidor A** (sin `-config`, τ de CALIB): `/v1/decide` con la ferretería → 200 y forma (`id`, `kind`, `answer` ∈ opciones,
   `probs` con una clave por opción que suma 1, `layer`, `escalate`, `ms`); `kind` inválido → 400; `/healthz`; `/metrics` por código;
   ORT cargado (el log no dice «L2 queda como stub»).
5. **Recarga**: 2 SIGHUP con 6 hilos pidiendo sin parar y cambiando el `.chispa` (zs → fs): ninguna petición falla ni se corta,
   `chispa_recargas_total{resultado="ok"}` = 2, las probabilidades cambian; un `.chispa` corrupto cuenta `error` y se sigue sirviendo.
6. `chispa evaluar` con `datos/muestra.csv` (15 filas) → rc 0, `informe.json` e `informe.md`.
7. **Servidor B** (`-config`: L1 τ=1 para que decida L2, `tau_l2_esquema_nuevo`, λ) con `datos/peticion_nueva.json` (choice + noul + score,
   esquema que el `.chispa` no trae): alguna decisión con `layer: L2`, `chispa_torres_calculadas_total` ≥ 3, `chispa_esquema_nuevo_decididas_total` ≥ 1,
   2.ª petición con `chispa_torres_cache_aciertos_total` ≥ 3, `chispa_torres_errores_total` = 0.
7b. **tipos_l2** (H8): `gensint` escribe una CALIB en `l2.chispa` (choice T=0,02, τ=0,37); el e2e comprueba que `chispa train --l2` la pasa a `tipos_l2` y `tau_escalate_l2` (distintos de los de L1) y que L2 da otras probabilidades con ella que sin ella.
8. 3 SIGHUP con 8 hilos de esquema nuevo (se cierran y reabren las sesiones ORT de L2 y torre): 0 peticiones fallidas, `recargas ok` = 3.
9. **multi**: zero-shot en el servidor B (`datos/peticion_multi.json`, esquema `datos/temas.yaml`, torres al vuelo): 200, `answers` en el orden de la
   pregunta, `answer` = la activa de mayor p y una `p` en [0,1] por opción (no suman 1). `chispa train --ejemplos datos/ejemplos_multi.csv` (`etiqueta` con `|`,
   celda vacía = ninguna) → `ms.chispa`, servido por un servidor C con la misma config: misma forma; las probabilidades de L1 cambian frente al zero-shot (CALIB de multi + SOPL1).
   `chispa evaluar` con `datos/muestra_multi.csv` → rc 0, `informe_multi.json` (exactitud por subconjunto, F1 micro/macro, Hamming, por etiqueta) e `informe_multi.md`.
   La comparación zero-shot/few-shot se hace en L1 (τ=0): en L2 ambos usan la CALIB de noul (sin `maxsim_l2` no hay `multi_l2`) y coinciden por diseño.
10. **Sin torre no falla en silencio**: `chispa train --l2` sin `--torre` (META+L2+ESQUEMAS+CALIB, como el `.chispa` de la medición M1) avisa y resume las capas;
   `--sin-torre` no avisa. Un servidor con ese `.chispa` loguea las capas efectivas y el aviso, `/healthz` dice `torre_al_vuelo: false`, `peticion_nueva.json`
   escala con `escalate_reason: "sin_opinion"` y sin probs, `chispa_capa_no_opina_total{capa="L2",causa="sin_torre"}` = 3 y la batería (`bateria_nadie.py`) cuenta
   `nadie_opino` = 100 % y alerta. Con `zs.chispa` (TORR) y τ=1 escala con `baja_confianza` y probs, la batería las mide en `exactitud` y no alerta.

Comprobado que puede fallar: con `CHISPA_ORT_LIB` apuntando a un fichero vacío, el script sale con 1 (L2 queda en stub y fallan 7 comprobaciones).

## Ficheros
`correr.sh` (orquestación), `comprobar.py` (HTTP, formas, métricas, carga con SIGHUP; solo stdlib), `gensint/` (modelos sintéticos),
`datos/` (esquema, ejemplos, muestra y peticiones), `HALLAZGOS.md`.
