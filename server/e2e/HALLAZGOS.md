# Hallazgos de la prueba e2e

Base: rama `delega/chispa-e2e` desde `9984421`. Corrida: `server/e2e/correr.sh` → todos los pasos pasan (zero-shot, few-shot con
torre y λ, servidor ORT con `-tok`, torre al vuelo con decisión de L2, recarga SIGHUP bajo carga sin peticiones falladas,
`evaluar`, `/metrics`). No se tocó código de producto.

## H1. `chispa-server` no permite indicar la ruta de ONNX Runtime, y sin ella L2 degrada a stub con 200

**Resuelto en `593f065`:** `-ort-lib` > `CHISPA_ORT_LIB` > `-ldflags -X …decide.RutaORT=` > búsqueda del sistema, para L2 y para la torre; aviso al arrancar si ORT no carga. `correr.sh` ya no necesita `LD_LIBRARY_PATH`.
- `server/decide/l2_ort.go:17` y `server/torre/ort.go:14` declaran `RutaORT`, pero nada en `server/cmd/chispa-server/main.go` la asigna
  (ni bandera ni variable de entorno). `CHISPA_ORT_LIB` solo la leen los tests (`server/decide/l2_ort_test.go:15`, `server/torre/ort_test.go:19`).
- Resultado: `onnxruntime_go` busca `onnxruntime.so` por el cargador del sistema. Con un `libonnxruntime.so.1.31.1` (venv, nombre con
  versión) el servidor arranca igual y degrada: `server/decide/modelo.go:162` añade un aviso solo al log
  («L2 queda como stub: … cannot open shared object file»); `/healthz` da 200 y `/v1/decide` responde 200 con L1/escalar.
- Reproducción: `go build -tags ort ./cmd/chispa-server`; `./chispa-server -modelo zs.chispa -tok /tmp/e5.chispa-tok` (con un `.chispa` con TORR)
  y pedir un esquema nuevo con L1 τ=1 → `layer: escalar`, `chispa_torres_calculadas_total 0`. Con
  `LD_LIBRARY_PATH=<dir con symlink onnxruntime.so>` funciona (así lo hace `correr.sh`).
- Documentación: `docs/02-inicio-rapido.md` y `docs/08-esquemas-nuevos.md` piden `-tags ort` pero no dicen cómo localizar la biblioteca.
- Sugerencia (no aplicada): bandera `-ort-lib` / `CHISPA_ORT_LIB` en main.go, y un fallo explícito (o una métrica/gauge) cuando hay TORR + `-tok` y L2 queda en stub.

## H2 (resuelto): `chispa train` multi few-shot no escribía SOPL1
- Resuelto con `mkdir(exist_ok=True)`; el E2E ahora exige SOPL1 y CALIB en `ms.chispa`. Texto original:
- Con `--ejemplos` de un esquema `multi`, `train` avisa «sin SOPL1: no se pudieron embeber los ejemplos: [Errno 17] File exists: …/embeber_go»:
  `embeber_con_go` (`sdk/python/chispa/train.py`) hace `d.mkdir()` sin `exist_ok` y se llama dos veces con el mismo directorio de trabajo.
  El `.chispa` sale con CALIB de multi pero sin soporte few-shot para L1; el E2E solo comprueba que las probabilidades cambian frente al zero-shot.

## Observaciones menores (no son fallos)
- `chispa train --shrinkage-lambda 4` avisa de que el τ de L1 se calibra sin el encogimiento; el aviso es correcto y está documentado.
- Con `-config`, el `tau_l2_esquema_nuevo` y los τ de `CALIB` no se usan: hay que repetirlos en el JSON (documentado en `02-inicio-rapido.md`).
  El script los repite.

## Sin verificar
- Calidad real: con modelos sintéticos las probabilidades no significan nada; no se verificó paridad con e5 real ni con la torre real.
- Que las entradas de ESQUEMAS que genera `gensint` (hash por opción con vectores arbitrarios) coincidan con las que exporta `model/l2/exportar.py`;
  la ferretería la deciden L1/escalar en la prueba, no se aseguró que L2 lea ESQUEMAS en lugar de la torre.
- `-race` (no se corrió el servidor con detector de carreras bajo la recarga), Android, iOS y motor móvil.
