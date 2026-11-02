# M3 robustez de L1 y L2 frente a variantes

Cambia = % de decisiones (argmax) distintas del original, con IC95 de Wilson. Δexact = exactitud(variante) − exactitud(original), IC95 de las diferencias emparejadas. «estructural»: el modelo no lee esa parte del caso, así que no puede cambiar.

max_tok 256 · filas por tarea 150 · semilla 0

## L1

| tipo | n | cambia | IC95 | exact orig | Δexact | IC95 Δ | |
|---|---|---|---|---|---|---|---|
| permutar | 450 | 0.0 % | 0.0–0.8 | 0.651 | +0.000 | +0.000–+0.000 | estructural |
| renombrar | 450 | 0.0 % | 0.0–0.8 | 0.651 | +0.000 | +0.000–+0.000 | estructural |
| parafrasear | 716 | 0.0 % | 0.0–0.5 | 0.649 | +0.000 | +0.000–+0.000 | estructural |
| erratas | 716 | 8.7 % | 6.8–10.9 | 0.649 | -0.017 | -0.036–+0.002 | **> 5 %** |
| mayusculas | 716 | 46.4 % | 42.7–50.0 | 0.649 | -0.261 | -0.300–-0.223 | **> 5 %** |
| mezcla | 716 | 0.6 % | 0.2–1.4 | 0.649 | +0.003 | -0.001–+0.007 |  |
| largo | 716 | 69.6 % | 66.1–72.8 | 0.649 | -0.415 | -0.457–-0.372 | **> 5 %** |
| pregunta_en | 566 | 0.0 % | 0.0–0.7 | 0.670 | +0.000 | +0.000–+0.000 | estructural |
| esquema_en | 266 | 0.0 % | 0.0–1.4 | 0.647 | +0.000 | +0.000–+0.000 | estructural |

## L2

| tipo | n | cambia | IC95 | exact orig | Δexact | IC95 Δ | |
|---|---|---|---|---|---|---|---|
| permutar | 450 | 0.0 % | 0.0–0.8 | 0.598 | +0.000 | +0.000–+0.000 |  |
| renombrar | 450 | 35.6 % | 31.3–40.1 | 0.598 | -0.153 | -0.194–-0.112 | **> 5 %** |
| parafrasear | 716 | 9.6 % | 7.7–12.0 | 0.542 | -0.001 | -0.020–+0.017 | **> 5 %** |
| erratas | 716 | 10.9 % | 8.8–13.4 | 0.542 | -0.015 | -0.034–+0.003 | **> 5 %** |
| mayusculas | 716 | 23.0 % | 20.1–26.3 | 0.542 | -0.094 | -0.121–-0.066 | **> 5 %** |
| mezcla | 716 | 5.6 % | 4.1–7.5 | 0.542 | -0.006 | -0.020–+0.009 | **> 5 %** |
| largo | 716 | 53.6 % | 50.0–57.3 | 0.542 | -0.275 | -0.313–-0.237 | **> 5 %** |
| pregunta_en | 566 | 14.7 % | 12.0–17.8 | 0.523 | -0.016 | -0.040–+0.008 | **> 5 %** |
| esquema_en | 266 | 7.5 % | 4.9–11.3 | 0.447 | +0.008 | -0.025–+0.041 | **> 5 %** |

## Arreglos propuestos (no ejecutados)

- **L1 / erratas** (cambia 8.7 %): Aumento de datos con 1–3 erratas por texto en ≈ 20 % de los ejemplos; en el runtime, nada fiable. Coste: ≈ 3 h g5 ≈ 3 USD.
- **L1 / mayusculas** (cambia 46.4 %): Normalizar en el runtime (minúsculas si el texto es casi todo mayúsculas) o aumento con mayúsculas/minúsculas. Coste: runtime: 0 GPU, horas; datos: ≈ 3 h g5 ≈ 3 USD.
- **L1 / largo** (cambia 69.6 %): Estrategia de M2 (`model.l2.largos`) para textos largos: recorte o ventanas, sin reentrenar. Coste: 0 GPU (ver M2).
- **L2 / renombrar** (cambia 35.6 %): Aumento de datos: sustituir ids por ids opacos en una parte de los ejemplos (la descripción manda); en el runtime, puntuar con el texto «pregunta · descripción» sin el id y mapear de vuelta. Coste: runtime: 0 GPU, ≈ 0,5 día; datos: ≈ 3 h g5 ≈ 3 USD.
- **L2 / parafrasear** (cambia 9.6 %): Aumento de datos con paráfrasis de la pregunta (plantillas fijas, sin LLM) en ≈ 30 % de los ejemplos. Coste: ≈ 3 h g5 ≈ 3 USD.
- **L2 / erratas** (cambia 10.9 %): Aumento de datos con 1–3 erratas por texto en ≈ 20 % de los ejemplos; en el runtime, nada fiable. Coste: ≈ 3 h g5 ≈ 3 USD.
- **L2 / mayusculas** (cambia 23.0 %): Normalizar en el runtime (minúsculas si el texto es casi todo mayúsculas) o aumento con mayúsculas/minúsculas. Coste: runtime: 0 GPU, horas; datos: ≈ 3 h g5 ≈ 3 USD.
- **L2 / mezcla** (cambia 5.6 %): Aumento con mezcla es/en (glosario) en ≈ 20 % de los ejemplos; añadir fuentes en inglés si faltan. Coste: ≈ 3 h g5 ≈ 3 USD.
- **L2 / largo** (cambia 53.6 %): Estrategia de M2 (`model.l2.largos`) para textos largos: recorte o ventanas, sin reentrenar. Coste: 0 GPU (ver M2).
- **L2 / pregunta_en** (cambia 14.7 %): Aumento de datos con la pregunta en inglés (traducción con plantillas) en ≈ 20 % de los ejemplos. Coste: ≈ 3 h g5 ≈ 3 USD.
- **L2 / esquema_en** (cambia 7.5 %): Aumento de datos con esquemas completos en inglés (pregunta y descripciones) en las tareas que ya los tengan. Coste: ≈ 3 h g5 ≈ 3 USD.
