# P5, segunda corrida (c6a.2xlarge, `integracion` @ `8df79cd`, checkpoint G.8 corrida 2, 2026-10-29): las torres al vuelo funcionan

- **Torres al vuelo por `/v1/decide`:** los 231 casos de JevBench, ninguno en el `.chispa`, con el perfil servidor (fp32 y
  vocabulario completo). En `/metrics`, **`chispa_torres_calculadas_total` = 368 y 0 errores.** La cadena exportador →
  `chispa train --torre` → servidor funciona.
- **Con τ de CALIB:** L2 contesta 15 de 231 y el resto escala.
- **Con `tau_l2_esquema_nuevo` = 0,276:** L2 contesta 185 de 231 (80 %) y escalan 46. Es lo que preveía el barrido.
- **Exactitud del servidor (mejor respuesta):** 0,437, frente a 0,485 en Python k = 0 con los mismos casos. Son
  **−4,8 puntos** y el objetivo era ≤ 1. Sospecha principal: **noul invertido**, el fallo de R9.
  - El exportador guarda la torre de la última opción y el runtime la lee como la de `true`.
  - En los 74 casos noul eso basta para unos −3,5 puntos.
  - No hay desglose por tipo, porque esta corrida no guardaba las respuestas por caso. `servidor.py` ya lo hace
    (`d7ec0b1`).
  - **noul queda pendiente del arreglo R9.** Tras R9 se repite P5.
- **Perfil servidor, otra vez exacto:** coseno 1,0000, top-1 1,000, torre de 471,6 MB y p50/p99 de 16,5/23,3 ms.
- **Coste:** c6a.2xlarge spot de 5 min, ≈ 0,02 USD.
