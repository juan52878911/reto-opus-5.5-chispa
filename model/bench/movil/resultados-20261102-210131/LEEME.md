# fp16 seguro para ARM (W15) frente a int8 en el moto g24 power (Helio G85, Android 14), N = 50, 2026-11-02

- **APK con ZK**, compilado en Docker en el Mac.
- **fp16:** `modelo-fp16.chispa` reexportado sin checkpoint con `model/bench/movil/reexportar_fp16.py`: LayerNorm, Softmax y
  atención en fp32. En x86, coseno 0,999999 frente al fp32.
- **int8:** el del ajuste 1.
- **Cómo se midió:** el APK escribe el JSON en el almacenamiento de la app y ya no en logcat; `medir.sh` agotaba su tiempo
  esperando logcat. Los JSON se sacaron con `adb pull`. 2 medidas de fp16 y 3 de int8, todas sin errores.

| escenario (p50 / p99 ms, decisiones/s) | fp16 seguro | int8 |
|---|---|---|
| zero-shot · L1 solo | 0,5 / 0,9 · 1 700–1 860 | 0,6–2,7 / 1,6–4,8 · 360–1 500 |
| zero-shot · cascada CPU | **151 / 171** · 6,7 | **28 / 40–41** · 34,5 |
| zero-shot · cascada XNNPACK | 150 / 174–178 · 6,7 | 28 / 40–42 · 35 |
| zero-shot · cascada NNAPI | 150–152 / 172–187 · 6,6 | 195 / 255–274 · 5,1 |
| few-shot · cascada CPU | 0,8 / 168–171 · 20 | 0,8 / 38–40 · 100 |

- **fp16 ya funciona en el móvil:** 0 errores y desaparece el «el motor rechazó las torres al vuelo».
  - L2 calcula: en zero-shot responde 2 y escala 48 de 50, como en int8.
- **fp16 es ~5× más lento que int8** en la cascada (p50 151 frente a 28 ms) y su p99 (171 ms) **no cumple** < 150 ms.
  - int8 sigue siendo el perfil móvil recomendado.
- **NNAPI:** con fp16 da lo mismo que CPU (probablemente cae a CPU); con int8 es más lento.
- **Memoria con fp16:** PSS del proceso ≈ 888 MB.
