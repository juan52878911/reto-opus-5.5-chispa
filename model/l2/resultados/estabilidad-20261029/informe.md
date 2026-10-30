# M2 textos largos (max_tok 256)

231 casos, 82 largos (la cabeza los trunca). IC95 por bootstrap sobre casos.

| estrategia | global | IC95 | choice | noul | score | largos | IC95 largos | Δ vs cabeza (IC95) | tokens/caso largo | pases |
|---|---|---|---|---|---|---|---|---|---|---|
| cabeza | 0.485 | 0.420–0.550 | 0.468 | 0.554 | 0.333 | 0.366 | 0.256–0.463 | +0.000 [+0.000, +0.000] | 256 | 1.0 |
| cola | 0.446 | 0.381–0.511 | 0.446 | 0.473 | 0.333 | 0.256 | 0.171–0.354 | -0.110 [-0.220, +0.000] | 256 | 1.0 |
| cabeza_cola | 0.468 | 0.403–0.528 | 0.432 | 0.568 | 0.333 | 0.317 | 0.220–0.427 | -0.049 [-0.122, +0.024] | 256 | 1.0 |
| trozos_max | 0.481 | 0.416–0.545 | 0.475 | 0.541 | 0.278 | 0.354 | 0.256–0.451 | -0.012 [-0.073, +0.049] | 1693 | 7.0 |
| trozos_media | 0.476 | 0.411–0.541 | 0.468 | 0.527 | 0.333 | 0.341 | 0.244–0.451 | -0.024 [-0.110, +0.049] | 1693 | 7.0 |

Recomendación: **cabeza** (ninguna gana con IC que no se solape ni empata siendo más barata).
# M6 L1 frente a L2

L1 = potion con prototipos (32 por clase). L2 = checkpoint con k = 32 y sin soporte. Mismo test por tarea.

| tarea | n test | L1 | L2 k=32 | L1/L2 | L2 k=0 | L1/L2(k=0) |
|---|---|---|---|---|---|---|
| massive | 2974 | 0.597 | 0.431 | 1.387 | 0.308 | 1.938 |
| hatecheck | 361 | 0.540 | 0.515 | 1.049 | 0.531 | 1.017 |
| clinc150 | 5500 | 0.745 | 0.823 | 0.905 | 0.784 | 0.951 |
| inyecciones | 116 | 0.793 | 0.379 | 2.091 | 0.326 | 2.434 |
| herramientas | 368 | 0.597 | 0.639 | 0.934 | 0.603 | 0.991 |

Media L1/L2 con L2 k = 32 (criterio de la fase 3): **1.273** (5 tareas) → cumple el criterio ≥ 0.90

Media L1/L2 con L2 k = 0: **1.466** (5 tareas) → cumple el criterio ≥ 0.90
# Batería de regresión: bateria-chispa

Fuente: `/opt/chispa/g8.chispa` · objetivo de precisión: 0,95 · 2026-10-30T02:26:35

## Global
|  | n | exactitud | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| global | 11000 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,9 | 3,5 |

## Por tipo
| tipo | n | exactitud | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| choice | 8981 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 2,0 | 3,5 |
| noul | 2001 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 2,6 |
| score | 18 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,4 | 2,1 |

## Por grupo
| grupo | n | exactitud | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 250,2 |
| prueba | 10769 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,9 | 3,5 |

## Por conjunto
| conjunto | n | exactitud | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 250,2 |
| massive | 2974 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,7 | 3,0 |
| clinc150 | 5500 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 2,2 | 3,6 |
| hatecheck | 361 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 2,4 |
| spam | 1450 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 2,6 |
| inyecciones | 116 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,4 | 2,4 |
| herramientas | 368 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,6 | 2,8 |

## Conjuntos omitidos
- massive-nv: sin datos: ${CHISPA_DATOS}/no_vistas/massive.jsonl
- hatecheck-nv: sin datos: ${CHISPA_DATOS}/no_vistas/hatecheck.jsonl
- inyecciones-nv: sin datos: ${CHISPA_DATOS}/no_vistas/inyecciones.jsonl
- clinc150-control: sin datos: ${CHISPA_DATOS}/no_vistas/clinc150_control.jsonl
- herramientas-control: sin datos: ${CHISPA_DATOS}/no_vistas/herramientas_control.jsonl

Exactitud y F1 cuentan un error de petición o una fila sin respuesta como fallo. ECE con 10 cubos sobre la confianza de la mejor respuesta (en multi, una decisión por opción). Cobertura = fracción de decisiones que un umbral único de confianza acepta con precisión ≥ objetivo. p50/p99: cliente, extremo a extremo.
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
| mezcla | 716 | 1.7 % | 1.0–2.9 | 0.649 | +0.000 | -0.009–+0.009 |  |
| largo | 716 | 71.1 % | 67.7–74.3 | 0.649 | -0.426 | -0.468–-0.384 | **> 5 %** |
| pregunta_en | 566 | 0.0 % | 0.0–0.7 | 0.670 | +0.000 | +0.000–+0.000 | estructural |
| esquema_en | 266 | 0.0 % | 0.0–1.4 | 0.647 | +0.000 | +0.000–+0.000 | estructural |

## L2

| tipo | n | cambia | IC95 | exact orig | Δexact | IC95 Δ | |
|---|---|---|---|---|---|---|---|
| permutar | 450 | 0.0 % | 0.0–0.8 | 0.591 | +0.000 | +0.000–+0.000 |  |
| renombrar | 450 | 37.6 % | 33.2–42.1 | 0.591 | -0.144 | -0.187–-0.102 | **> 5 %** |
| parafrasear | 716 | 9.5 % | 7.6–11.9 | 0.560 | -0.015 | -0.035–+0.004 | **> 5 %** |
| erratas | 716 | 12.8 % | 10.6–15.5 | 0.560 | -0.029 | -0.049–-0.010 | **> 5 %** |
| mayusculas | 716 | 33.4 % | 30.0–36.9 | 0.560 | -0.115 | -0.147–-0.083 | **> 5 %** |
| mezcla | 716 | 6.7 % | 5.1–8.8 | 0.560 | -0.011 | -0.026–+0.004 | **> 5 %** |
| largo | 716 | 61.3 % | 57.7–64.8 | 0.560 | -0.334 | -0.374–-0.294 | **> 5 %** |
| pregunta_en | 566 | 16.6 % | 13.8–19.9 | 0.549 | -0.035 | -0.062–-0.008 | **> 5 %** |
| esquema_en | 266 | 15.0 % | 11.2–19.8 | 0.508 | -0.068 | -0.114–-0.022 | **> 5 %** |

## Arreglos propuestos (no ejecutados)

- **L1 / erratas** (cambia 8.7 %): Aumento de datos con 1–3 erratas por texto en ≈ 20 % de los ejemplos; en el runtime, nada fiable. Coste: ≈ 3 h g5 ≈ 3 USD.
- **L1 / mayusculas** (cambia 46.4 %): Normalizar en el runtime (minúsculas si el texto es casi todo mayúsculas) o aumento con mayúsculas/minúsculas. Coste: runtime: 0 GPU, horas; datos: ≈ 3 h g5 ≈ 3 USD.
- **L1 / largo** (cambia 71.1 %): Estrategia de M2 (`model.l2.largos`) para textos largos: recorte o ventanas, sin reentrenar. Coste: 0 GPU (ver M2).
- **L2 / renombrar** (cambia 37.6 %): Aumento de datos: sustituir ids por ids opacos en una parte de los ejemplos (la descripción manda); en el runtime, puntuar con el texto «pregunta · descripción» sin el id y mapear de vuelta. Coste: runtime: 0 GPU, ≈ 0,5 día; datos: ≈ 3 h g5 ≈ 3 USD.
- **L2 / parafrasear** (cambia 9.5 %): Aumento de datos con paráfrasis de la pregunta (plantillas fijas, sin LLM) en ≈ 30 % de los ejemplos. Coste: ≈ 3 h g5 ≈ 3 USD.
- **L2 / erratas** (cambia 12.8 %): Aumento de datos con 1–3 erratas por texto en ≈ 20 % de los ejemplos; en el runtime, nada fiable. Coste: ≈ 3 h g5 ≈ 3 USD.
- **L2 / mayusculas** (cambia 33.4 %): Normalizar en el runtime (minúsculas si el texto es casi todo mayúsculas) o aumento con mayúsculas/minúsculas. Coste: runtime: 0 GPU, horas; datos: ≈ 3 h g5 ≈ 3 USD.
- **L2 / mezcla** (cambia 6.7 %): Aumento con mezcla es/en (glosario) en ≈ 20 % de los ejemplos; añadir fuentes en inglés si faltan. Coste: ≈ 3 h g5 ≈ 3 USD.
- **L2 / largo** (cambia 61.3 %): Estrategia de M2 (`model.l2.largos`) para textos largos: recorte o ventanas, sin reentrenar. Coste: 0 GPU (ver M2).
- **L2 / pregunta_en** (cambia 16.6 %): Aumento de datos con la pregunta en inglés (traducción con plantillas) en ≈ 20 % de los ejemplos. Coste: ≈ 3 h g5 ≈ 3 USD.
- **L2 / esquema_en** (cambia 15.0 %): Aumento de datos con esquemas completos en inglés (pregunta y descripciones) en las tareas que ya los tengan. Coste: ≈ 3 h g5 ≈ 3 USD.
# M4 español frente a inglés (L2, k = 0)

Mismo esquema (pregunta, ids y descripciones en español) y los mismos casos en los dos idiomas. Δ = es − en, IC95 por bootstrap emparejado (B = 1000). Puntos = 100 × diferencia.

| tarea | n | exact es | exact en | Δ exact (pts) | IC95 | F1 es | F1 en | Δ F1 (pts) | IC95 |
|---|---|---|---|---|---|---|---|---|---|
| massive | 400 | 0.405 | 0.463 | -5.8 | -11.0–-0.5 | 0.323 | 0.341 | -1.8 | -7.7–+2.4 |
| xnli | 400 | 0.357 | 0.372 | -1.5 | -5.5–+2.5 | 0.313 | 0.336 | -2.3 | -6.1–+1.7 |
| sib200 | 204 | 0.456 | 0.520 | -6.4 | -12.7–+0.0 | 0.436 | 0.500 | -6.3 | -12.7–+0.5 |
| paws-x | 400 | 0.525 | 0.527 | -0.2 | -2.5–+2.0 | 0.390 | 0.345 | +4.5 | +1.4–+7.8 |
| **media** | 1404 | 0.436 | 0.471 | -3.5 | -5.9–-1.1 | 0.366 | 0.381 | -1.5 | -4.1–+0.9 |


**Brecha > 3 puntos: SÍ, ver plan.md.**
# M4 plan de reentrenamiento para cerrar la brecha es − en (preparado, NO lanzado)

Motivo: |es − en| > 3 puntos (ver `espanol.json`).

## Fuentes en español con licencia comercial

| fuente | para qué | filas aprox. | uso | licencia en la tarjeta de HF | entra en train |
|---|---|---|---|---|---|
| SINAI/ALIA-es-discriminative-hate-speech | toxicidad/odio en español | 8000 | train | cc-by-4.0 | sí |
| Multilingual-Perspectivist-NLU/MultiPICo | ironía en español (perspectivista) | 6000 | train | cc-by-4.0 | sí |
| bgonzalezbustamante/toxicity-Constitution-ES | toxicidad en español | 4000 | train | cc-by-4.0 | sí |
| bgonzalezbustamante/toxicity-protests-ES | toxicidad en español (protestas) | 4000 | train | cc-by-4.0 | sí |
| google-research-datasets/paws-x | paráfrasis es/en (noul) | 49000 | train | other | NO hasta comprobar |
| Davlan/sib200 | tema es/en (7 clases) | 700 | train | cc-by-sa-4.0 | sí |
| (PQRS propios) | PQRS en español colombiano | - | solo test | propia (sin publicar) | solo test |

Las licencias se leen de `README.md` de la caché de ~/hf; si no está ahí, queda «NO COMPROBADA». PQRS solo entra en test.

## Tamaño

≈ 71700 filas nuevas en español en `train` (tope por tarea 2000 y p ∝ n^0,3, así que cada fuente aporta como mucho 2000 por tarea tras el reparto: unas 10000 filas efectivas). Es < 10 % de la mezcla de G.8.

## Cambios en `model/l2/aws/general.sh`

1. `CONV`: pasar `--fuentes` con las nuevas (`odio_alia`, `toxicidad_constitucion`, `toxicidad_protestas` ya están en `model.datos`; MultiPICo, PAWS-X y SIB-200 necesitan conversor nuevo en `model/datos/` con licencia comprobada en la tarjeta).
2. Descarga de HF: `snapshot_download` de esos datasets (con `HF_HUB_OFFLINE=1` después).
3. `EXCLUIR`: dejar `massive,hatecheck,inyecciones` fuera del entrenamiento (siguen siendo el test no visto) y añadir `xnli` solo a test.
4. `G8`: mantener `--tope-tarea 2000 --alfa 0.3 --max-tok 256`; subir `--frac-es` (o equivalente) si el reparto lo permite, sin tocar el resto.
5. Evaluar con `python -m model.l2.espanol` y `model.l2.robustez` al terminar (mismo checkpoint) para comprobar que la brecha baja de 3 puntos.

## Coste en GPU

g5.xlarge, ~1.01 USD/h: reentrenamiento completo ≈ 3.0 h de entrenamiento + 1 h de descarga y evaluación = tope de 240 min de general.sh = **≈ 4.0 USD** (+ ~0,1 USD de disco). Una corrida de ajuste fino desde el checkpoint de G.8 (1 h de entrenamiento) saldría en ≈ 2.0 USD.
