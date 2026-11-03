# Latencia de Chispa en un Android real: moto g24 power (MediaTek Helio G85, 8 núcleos, 8 GB, Android 14), 2026-11-02

- **App:** demo «Medir» (APK `ae49d46`).
- **Modelos:** los del perfil móvil del ajuste 1 (`modelos.sh`): `modelo-int8.chispa` (250 MB) y `modelo-fp16.chispa`
  (332 MB), más `e5.chispa-tok`.
- **Cómo se midió:** `medir.sh` con N = 1000 se quedó sin tiempo (40 min por perfil). Se midió a mano: `am start … --ei n 50`
  para int8 y `--ei n 300` para fp16.

## int8 (`int8-n50.json`)

| escenario | p50 | p95 | p99 | decisiones/s |
|---|---|---|---|---|
| L1 solo | 2,7 ms | 3,3 ms | 5,4 ms | 353 |
| cascada zero-shot, CPU | **28,3 ms** | 36,0 ms | **40,3 ms** | 35 |
| cascada zero-shot, XNNPACK | 28,7 ms | 37,3 ms | 41,4 ms | 35 |
| cascada zero-shot, NNAPI | 195 ms | 225 ms | 290 ms | 5 |
| cascada few-shot, CPU | 0,8 ms | 32,2 ms | 38,7 ms | 103 |

**Cumple el criterio de la fase 3: p99 < 150 ms en un Android de gama media, con CPU o XNNPACK.** NNAPI va mucho más lento
en este SoC.

## fp16 (`fp16-n300-fallido.json`): **falla**
- El SDK Android rechaza las torres al vuelo: `ErrorChispa: L2: el motor rechazó las torres al vuelo (d=256, n=5)`, en
  `CapaL2.torresAlVuelo`.
- Las latencias de L2 que salen (≈ 1 ms) no son válidas: L2 no calcula.
- Pasado a la otra sesión: probablemente es la salida float16 de la torre en el puente Kotlin–Go.
- **Memoria** con fp16 cargado: PSS ≈ 556 MB. Datos de la app: 328 MB.
