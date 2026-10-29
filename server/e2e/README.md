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

`chispa-server` no tiene bandera ni variable para la ruta de ORT (ver [HALLAZGOS.md](HALLAZGOS.md)): el script enlaza
`CHISPA_ORT_LIB` como `onnxruntime.so` en un directorio de trabajo y lo pone en `LD_LIBRARY_PATH`.

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
8. 3 SIGHUP con 8 hilos de esquema nuevo (se cierran y reabren las sesiones ORT de L2 y torre): 0 peticiones fallidas, `recargas ok` = 3.

Comprobado que puede fallar: con `CHISPA_ORT_LIB` apuntando a un fichero vacío, el script sale con 1 (L2 queda en stub y fallan 7 comprobaciones).

## Ficheros
`correr.sh` (orquestación), `comprobar.py` (HTTP, formas, métricas, carga con SIGHUP; solo stdlib), `gensint/` (modelos sintéticos),
`datos/` (esquema, ejemplos, muestra y peticiones), `HALLAZGOS.md`.
