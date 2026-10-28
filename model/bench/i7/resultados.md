# Latencia en el i7-8700T (nodo kindling-pve-personal)

Medido el 2026-10-28 en una microVM de 2,5 GB (4 vCPU) sobre el i7-8700T, que comparte host con otras VM: hay ruido.
e5-small (`model/bench/codificadores.py`, `_trabajador`), ONNX Runtime CPU, batch 1, ids ya tokenizados (sin tokenizar), 20 calentamientos + 300 repeticiones por celda,
tres tandas separadas por 1 min (`medir_i7.py`). Cifras: **mediana de los tres p99 (mín–máx)**, en ms. Entorno en `entorno.txt`; loadavg y memoria antes/después de cada medida en `medidas.jsonl`.

## Veredicto

**p99 < 50 ms a 64 tokens SE CUMPLE en el i7 para e5-small int8 podado con 1 hilo** (mediana 30.6 ms, rango 26.8–32.4); con 4 hilos: mediana 13.9 ms, rango 13.7–14.5.
L1 (potion-multilingual-128M, Go): p99 a 64 tokens (66 reales) = 166 µs (< 1 ms: sí).

## Comparativa: p99 a 64 tokens, e5-small, ms

| Variante | i3 kindling | c6a | c6i | **i7** |
|---|---|---|---|---|
| int8 podado, 1 hilo | 200.08 | 19.31 | 10.66 | **30.6 (26.8–32.4)** |
| int8 podado, 4 hilos | 743.77 | 12.05 | 6.89 | **13.9 (13.7–14.5)** |
| fp32 podado, 1 hilo | 159.95 | 33.27 | 23.39 | **44.6 (35.8–44.6)** |
| fp32 podado, 4 hilos | 506.79 | 17.44 | 13.32 | **20.4 (20.3–25.2)** |
| fp32 sin podar, 1 hilo | 163.20 | 39.73 | 23.28 | **38.2 (36.6–42.1)** |
| fp32 sin podar, 4 hilos | 323.59 | 24.26 | 13.45 | **28.4 (27.3–34.1)** |
| L1 (potion), 1 hilo, 66 tok | – | – | – | **166 µs (140–764)** |


(i3/c6a/c6i: una tanda de `model/bench/resultados-x86.md` y `aws/resultados/`, 200 repeticiones.)

## e5-small en el i7: p50 y p99 por longitud (mediana de las 3 tandas; p99 con rango)

| variante | hilos | tokens | p50 | p99 (mín–máx) |
|---|---|---|---|---|
| int8 podado | 1 | 16 | 7.0 | 8.3 (7.8–8.4) |
| int8 podado | 1 | 64 | 24.6 | 30.6 (26.8–32.4) |
| int8 podado | 1 | 256 | 110.1 | 125.7 (124.9–126.4) |
| int8 podado | 4 | 16 | 3.9 | 4.9 (4.7–5.0) |
| int8 podado | 4 | 64 | 12.2 | 13.9 (13.7–14.5) |
| int8 podado | 4 | 256 | 48.0 | 78.5 (72.3–78.8) |
| fp32 podado | 1 | 16 | 10.8 | 12.3 (12.2–15.7) |
| fp32 podado | 1 | 64 | 32.4 | 44.6 (35.8–44.6) |
| fp32 podado | 1 | 256 | 134.5 | 155.1 (143.0–156.2) |
| fp32 podado | 4 | 16 | 6.7 | 8.1 (7.7–8.5) |
| fp32 podado | 4 | 64 | 17.9 | 20.4 (20.3–25.2) |
| fp32 podado | 4 | 256 | 71.6 | 92.9 (91.6–126.3) |
| fp32 sin podar | 1 | 16 | 10.8 | 12.4 (12.1–16.0) |
| fp32 sin podar | 1 | 64 | 32.5 | 38.2 (36.6–42.1) |
| fp32 sin podar | 1 | 256 | 134.7 | 156.3 (146.6–163.9) |
| fp32 sin podar | 4 | 16 | 6.6 | 11.6 (9.4–12.5) |
| fp32 sin podar | 4 | 64 | 17.6 | 28.4 (27.3–34.1) |
| fp32 sin podar | 4 | 256 | 71.5 | 126.8 (91.3–167.4) |

## L1 (`runtime/l1/cmd/l1medir`, n=2000), µs, tres tandas

| tokens | p50 | p99 mediana (mín–máx) |
|---|---|---|
| 16 | 16 | 42 (34–46) |
| 66 (pedido 64) | 70 | 166 (140–764) |
| 256 | 259 | 540 (540–564) |

Hash del cuerpo del `.chispa-l1` exportado con `exportar.py`: `01fe1e57dc1bb1917757723e35264b146c25c4d81a3950a8ec7bb0f6a4ba8808` (coincide). linux/amd64 go1.27.1  abrir=337.502µs  abrir+primer_embed=606.62µs; RSS tras primer embed: VmRSS: 7468 kB, RssAnon: 944 kB, RssFile: 6524 kB.

## Ruido y notas

- loadavg(1 min) antes de cada medida: 0.94–2.67; después: 0.97–2.67. Ya en reposo la VM marcaba ≈1,3–1,7 al arrancar (el contador es del host, no solo mío).
- Dispersión máx/mín del p99 a 64 tokens entre tandas: int8 podado 1h ×1.21, int8 podado 4h ×1.06, fp32 podado 1h ×1.25, fp32 podado 4h ×1.24, fp32 sin podar 1h ×1.15, fp32 sin podar 4h ×1.25.
- `lscpu` dentro de la VM da «Intel Xeon Processor @ 2.40GHz» (CPU virtualizada, no el nombre del i7-8700T); tiene AVX2 y FMA, sin AVX-512 ni VNNI: es consistente con el i7 pero no lo prueba.
- `preparar` con 2,5 GB: la cuantización int8 del e5 **sin podar** muere por memoria (OOM, 2 veces), así que esa variante no se midió (no estaba pedida; solo fp32 sin podar). int8 podado sí se cuantizó.
- `make test` y `make smoke` en verde en esta VM.
