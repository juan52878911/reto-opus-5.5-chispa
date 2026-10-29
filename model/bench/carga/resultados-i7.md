# Prueba de carga G.4 (microVM de kindling, NO el i7-8700T)

**Aviso principal: no es el i7.** La VM de este nodo reporta `Intel Xeon @ 2,40 GHz`, 4 vCPU, 2,5 GB de RAM, sin swap
(`crudo/entorno-medir.txt`). Los objetivos son del i7-8700T, así que esto es una cota orientativa, no la confirmación.
Los objetivos de L1 se superan con margen aquí; **L2 no se pudo medir en el servidor** (abajo).

## Qué se midió
- Servidor: `chispa-server` de `server/` sin cambios, sin ORT (`-tags ort` no compila: falta el módulo Go
  `github.com/yalue/onnxruntime_go` y `GOPROXY=off`; `crudo/ort-build.log`). La `libonnxruntime.so` 1.31.1 existe solo como
  paquete de Python. L2 queda en stub, así que **L2 forzado por HTTP: sin medir**.
- Modelo: `completo.chispa` = L0 + L1 (`chispa train`, potion-multilingual-128M, 800 ejemplos de MASSIVE es agrupados en
  4 opciones inventadas, las que `cmd/carga` manda fijas) + L2 aleatoria (e5 int8 de `~/hf`, cabeza con semilla 0; la
  latencia no depende de los pesos y no hay S3 para el checkpoint real). Tokenizador: `runtime/tok/exportar.py`.
- Modos: `l0l1` = cascada por defecto (sin `--config`): el sondeo con 200 mensajes reales da 121 en L0 y 79 «escalar»
  (L1 corre pero no llega a su τ); `l1-forzado` = `config-l1-forzado.json` (L0 τ=1, L1 τ=0): 200/200 las contesta L1.
  `config-l2-forzado.json` está listo pero no se usó.
- Carga: `server/cmd/carga` sin cambiar, c = 1/4/16/64, 30 s, 3 tandas seguidas. Como `carga` manda siempre el mismo
  mensaje («reclamo de la garantía») y el brief pide mensajes reales, se repitió con `cargamsg/` (copia de `carga` con el
  mensaje por turno de 2000 frases de MASSIVE test; mismas banderas y salida). Cambio que haría falta en `cmd/carga`: una
  bandera `-mensajes FICHERO`.
- El generador corre en la misma VM de 4 vCPU que el servidor (compiten por CPU), igual que en `make carga`.
- Cargas del host: loadavg antes de la primera tanda 1,33; durante, 3,7–5 (lo que genera la propia prueba; `crudo/*.load`).
  No se ve ruido de otros trabajos, pero desde dentro de la VM no se puede saber qué hace el host.

## Resultados (mediana de 3 tandas; objetivo L0+L1: ≥ 5000 decisiones/s y p99 < 20 ms con 4 hilos)

### `server/cmd/carga` sin cambiar (mensaje fijo)

| modo | conc | tandas | decisiones/s (mediana) | rango entre tandas | variación | p50 ms (mediana) | p99 ms (mediana / peor) | errores | objetivo |
|---|---|---|---|---|---|---|---|---|---|
| l0l1 | 1 | 3 | 6320 | 6319–6328 | 0 % | 0.16 | 0.24 / 0.25 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l0l1 | 4 | 3 | 21482 | 21477–21511 | 0 % | 0.17 | 0.54 / 0.54 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l0l1 | 16 | 3 | 31113 | 31040–31377 | 1 % | 0.40 | 2.45 / 2.52 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l0l1 | 64 | 3 | 33292 | 33032–34310 | 4 % | 1.50 | 8.40 / 8.44 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l1-forzado | 1 | 3 | 5043 | 5039–5056 | 0 % | 0.19 | 0.35 / 0.35 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l1-forzado | 4 | 3 | 16464 | 16410–16474 | 0 % | 0.21 | 0.75 / 0.75 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l1-forzado | 16 | 3 | 20718 | 20655–21035 | 2 % | 0.52 | 4.03 / 4.05 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l1-forzado | 64 | 3 | 21641 | 21495–22241 | 3 % | 1.80 | 16.55 / 17.02 | 0 | ≥ 5000 y p99 < 20 ms: sí |

### `cargamsg` (mensajes reales de MASSIVE, uno distinto por petición)

| modo | conc | tandas | decisiones/s (mediana) | rango entre tandas | variación | p50 ms (mediana) | p99 ms (mediana / peor) | errores | objetivo |
|---|---|---|---|---|---|---|---|---|---|
| l0l1 | 1 | 3 | 5640 | 5624–5647 | 0 % | 0.17 | 0.31 / 0.31 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l0l1 | 4 | 3 | 18447 | 18409–18488 | 0 % | 0.19 | 0.66 / 0.67 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l0l1 | 16 | 3 | 25222 | 24912–25232 | 1 % | 0.47 | 3.12 / 3.16 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l0l1 | 64 | 3 | 26633 | 26018–26739 | 3 % | 1.73 | 11.43 / 11.81 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l1-forzado | 1 | 3 | 5082 | 4989–5101 | 2 % | 0.19 | 0.36 / 0.36 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l1-forzado | 4 | 3 | 16307 | 16280–16365 | 1 % | 0.21 | 0.77 / 0.77 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l1-forzado | 16 | 3 | 20510 | 20145–21006 | 4 % | 0.54 | 4.05 / 4.18 | 0 | ≥ 5000 y p99 < 20 ms: sí |
| l1-forzado | 64 | 3 | 21535 | 21474–21845 | 2 % | 1.82 | 16.10 / 16.32 | 0 | ≥ 5000 y p99 < 20 ms: sí |

La variación entre tandas (máx−mín sobre la mediana) es ≤ 4 % en todos los puntos: menos de lo esperado en un host
compartido, pero 3 tandas seguidas en 24 minutos no cubren otras horas ni otros vecinos.

Lectura: con c=4 (los 4 hilos) `l1-forzado` da ~16,3 k/s con p99 0,77 ms y `l0l1` ~18–21 k/s; c=1 ya cumple 5 k/s con una
sola conexión en `l1-forzado` (5,0–5,1 k, justo en el límite). Con c=64 el p99 llega a 16–17 ms en `l1-forzado`, bajo los 20 ms.
Memoria del servidor ≈ 215 MB RSS (`rss_servidor_kb` en cada fichero).

## L2: solo un proxy del codificador (no es el servidor)
`proxy_l2_ort.py`: el mismo ONNX int8 (48 MB) con ONNX Runtime 1.31.1 de Python, 1 hilo intra-op por llamada,
mensajes reales (14 tokens de media), sin HTTP, JSON, torres ni cascada (`crudo/proxy-l2-ort.jsonl`):

| hilos concurrentes | llamadas/s | p50 ms | p99 ms |
|---|---|---|---|
| 1 | 144 | 6,7 | 11,8 |
| 4 | 431 | 8,6 | 18,2 |
| 16 | 409 | 36,6 | 88,5 |

Con 4 hilos el codificador solo ya da ~430/s (> 300), pero con un margen de 1,4× antes de sumar HTTP, ranuras en Go,
torres y carga competida; en el servidor real puede quedar cerca o por debajo de 300. **Hipótesis L2 ≥ 300/s: ni confirmada
ni refutada.** Es de Xeon 2,4 GHz, no del i7 (el i7 midió e5 int8 con p99 30,6 ms, `model/bench/i7/resultados.md`).

## Reproducir
`bash model/bench/carga/armar.sh /tmp/carga` y `bash model/bench/carga/medir.sh /tmp/carga model/bench/carga/crudo 3 30`;
`python model/bench/carga/agregar.py model/bench/carga/crudo`. `exportar_ligero.py` parte `model.l2.exportar` en procesos
porque la cuantización dentro del proceso del export lleva la VM de 2,5 GB al OOM (matado por el kernel, comprobado).

## Qué no se pudo medir
- L2 en el servidor (sin ORT para Go) y por tanto L2c.
- Nada en el i7-8700T real; hay que repetir `armar.sh` + `medir.sh` allí (con ORT y `-tags ort` compilará `armar.sh` solo).
