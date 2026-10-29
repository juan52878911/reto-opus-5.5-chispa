# Corrida final de la tanda (integracion @ 798a68f: chispa-sdk a797bd4, calib_completa)

## JevBench por servidor
- `chispa train --ckpt`, sin pasos manuales.
- **`tipos_l2` OK**, idéntico al checkpoint.
- **Exactitud 0,494**, y 0 discrepancias en 78 casos:

  | tipo | servidor | Python k = 0 |
  |---|---|---|
  | choice | 0,482 | 0,468 |
  | noul | 0,554 | 0,554 |
  | score | 0,333 | 0,333 |

- Coste: c6a.2xlarge bajo demanda, 10 min.

## Android (c6a.xlarge)
- Construye el AAR, de 5,6 MB.
- `./gradlew test` falla: **86 tests, 1 fallido**.
  - El test es `CacheYErroresTest.l2cUsaTauL2cSiEsMayorOIgualACero` (`CacheYErroresTest.kt:107`).
  - Espera escalar con 0,7 < `tauConj` 0,9.
- No hay APK de demo, porque el fallo corta `assembleDebug`.
- Log completo: `server/deploy/resultados/android-sdk-798a68f.log`.
- Es del producto, en `sdk/android`, zona de la otra sesión. Probablemente tiene que ver con H7, «el respaldo de L2c se
  corta con `tau_escalate_l2`», y el test no se actualizó.

## Tests sobre el sha final (V3, 639158a)
- `unittest` de `model`: 445 OK.
- `make test` OK.
- `make smoke` OK.
