# Laya (zero-shot, CPU con 4 hilos) frente a Chispa, 2026-11-02 (c6a.2xlarge, 80 min, ≈ 0,4 USD)

- **Laya:** `laya` 0.4.21, `convaiinnovations/laya`.
  - Licencia **Apache-2.0** en el paquete y en los pesos de los tres checkpoints (english, multilingual y typed-decisions),
    según las tarjetas de HF.
  - Datos de entrenamiento: la tarjeta describe el método (RLCD), pero no lista datasets (`laya-licencia.json`).
  - `typed-decisions` está ajustado sobre typed decisions, la familia de nuestro tsjev.
- **Recorte:** Laya va a 0,28 s por pregunta en CPU, así que midió **como mucho 750 filas por conjunto**, con una submuestra
  regular y determinista. Chispa midió todas. Las cifras no son del mismo subconjunto, aunque sí de la misma distribución.
- **Las latencias de Chispa son por servidor HTTP** (`/v1/decide`). Las de Laya son en proceso. Aun así, Chispa es entre 10 y
  30 veces más rápido.

| global | exactitud | F1 macro | ECE | p50 / p99 (ms) |
|---|---|---|---|---|
| Laya multilingual | 0,529 | 0,467 | 0,228 | 277 / 1242 |
| Laya typed-decisions | 0,498 | 0,423 | 0,034 | 793 / 3192 |
| **Chispa, ajuste 1 (línea base oficial)** | **0,644** | **0,577** | 0,113 | **22 / 171** |
| Chispa v2 | 0,584 | 0,530 | 0,110 | 24 / 176 |

**Por conjunto:**
- **Chispa gana** en massive, clinc150, spam y herramientas.
- **Laya gana** en hatecheck (0,598 frente a 0,476) e inyecciones (0,621 frente a 0,491).
- **JevBench queda igualado:** 0,489–0,506.

**En español** (M4, exactitud es − en): Laya multilingual pierde −6,0 puntos en massive y −2,0 en MMMLU; typed-decisions,
−18,5 y −6,0. Chispa v2, en M4 (otra medida), −2,6.

Tabla completa en `laya-frente-chispa.md`.
