# D1, paridad servidor ↔ Python en JevBench (2 corridas en c6a.2xlarge, 2026-10-29)

**Medido** (`informe.md`), con la exactitud por tipo frente a Python k = 0 (0,485):

| pasada | exactitud | choice | noul | score |
|---|---|---|---|---|
| base (`.chispa` de `chispa train --torre`) | 0,437 | 0,439 (Py 0,468) | 0,473 (Py 0,554) | 0,278 (Py 0,333) |
| (b) CALIB global del checkpoint | 0,437 | 0,439 | 0,486 | 0,222 |

- **CALIB explica poco.** choice no cambia porque el argmax no depende de T; noul sube 1,3 puntos.
- **Diagnóstico caso a caso** (78 casos, replay fiel |Δp| = 0,000). Las discrepancias se reparten así:
  - **onnx**, la causa principal: la consulta del `.chispa` es int8 con el vocabulario podado a **384 filas** (de 250.037),
    porque `chispa train --ckpt` la poda a los tokens del entrenamiento;
  - **texto de torre**, en noul y score: el servidor omite el `" · "` final cuando no hay descripción, Python no; además la
    petición no lleva la descripción de «true» ni de los niveles.
- **Sin medir:**
  - la pasada (c), CALIB global más consulta fp32 sin poda;
  - el perfil móvil en fp16 con la poda ampliada.
- **Por qué faltan:** fallos de mis scripts en las dos corridas.
  - Corrida 1: `KeyError 'choice'` y luego `'score4'` en `paridad_servidor.probs_calib`, con la CALIB de `chispa train`.
  - Corrida 2: `pasada` se llamó con 2 argumentos bajo `set -u` (`e2e.sh:233`, `$3: unbound variable`).
  - **Dos fallos seguidos: se escala.** La pasada (c) se medirá directamente cuando `chispa train` use la consulta fp32
    (arreglo X1 de la otra sesión).
- **Coste:** dos c6a.2xlarge de unos 15 min, ≈ 0,1 USD.
