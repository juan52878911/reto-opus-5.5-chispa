# T2.2c: cabeza conjunta L0 + L2

Decisión de Juan (2026-10-28): «C y después b». En las tres rondas de T2.2, L0 (TF-IDF de caracteres + regresión logística) gana
a todo lo basado en e5-small en las tareas de muchas clases (`resultados/ronda3-t22/LEEME.md`). (b) da a L2 las características de
L0. Aquí está el arnés (`conjunta.py`), pensado para medirse, no los resultados.

## H1: fusión tardía por tarea (implementada)

Una cabeza por tarea sobre, para cada opción (clase) c de cada fila:

| característica | de dónde sale |
|---|---|
| `a_c` = log P_L0(c) | L0 (`model.lineas_base.correr.correr_l0`: char_wb 2–5, LR C=10) |
| `b_c` = simproto(c) | similitud de las ranuras del mensaje con el prototipo de soporte de la clase (`modelo.simproto`) |
| `c_c` = log P_L2(c) | L2 con soporte (`ModeloL2.forward(..., protos=...)`) |
| `top0_c`, `top2_c`, `top0_c·top2_c` | la clase es la primera de L0, de L2, de las dos |

`a`, `b` y `c` se centran por fila y se dividen por su desviación en train. Las diferencias entre capas son lineales en
estas columnas, así que la cabeza lineal ya las expresa; los `top` son lo único no lineal.

Dos cabezas candidatas, ambas con 5–6 parámetros por tarea:

- **`lr`**: regresión logística multinomial con las características por clase **compartidas**: `logit_c = w·f_c`. No depende de
  qué clase es, solo de cómo la ven L0 y L2: sirve igual con 2 que con 151 clases.
- **`puerta`**: apilado `p = g·P_L0 + (1−g)·P_L2`, `g = σ(v·[1, conf_L0, conf_L2, margen_L0, margen_L2])`
  (conf = prob. máxima, margen = 1.ª − 2.ª).

Ajuste: LBFGS en doble precisión sobre NLL + λ‖w‖² (sin penalizar el sesgo de la puerta). Determinista: sin muestreo; los
pliegues y el soporte usan semilla 0. **Elección**: λ ∈ {1e-4, 1e-3, 1e-2, 0,1, 1} y tipo de cabeza por NLL en validación cruzada
sobre train (los mismos 5 pliegues de L0); después se ajusta con todo train. Test no se mira para elegir. `delta.md` lleva las
dos cabezas además de la elegida, solo para leerlas.

### Características sin fuga

- **L0 en train**: fuera de pliegue, k = 5. Cada fila se predice con un L0 entrenado con los otros cuatro pliegues
  (`correr_l0` de las líneas base). Pliegues estratificados por clase, barajados con semilla.
- **L2 en train**: el soporte es el de T1.7a (`datos.soporte_t17a`, 32 por clase, semilla 0). Una fila que está en el soporte se
  puntúa con el prototipo de su clase **sin ella** (`ProtosSinPropia.sin`; equivale a `modelo.prototipos` sobre el soporte menos la
  fila, lo comprueba un test). Una fila fuera del soporte no puede estar en su propio soporte. Una clase que se queda sin ejemplos
  pierde su prototipo (simproto 0, como en el modelo).
- **Test**: L0 con todo train, L2 con el soporte completo de T1.7a; es la evaluación de T2.1b.

Límites que no se pueden quitar desde aquí:

1. L2 se entrenó en el train de esas mismas tareas (checkpoint de T2.1b): sus log-probs en train son más confiadas que en test
   aunque el prototipo no incluya la fila. La cabeza puede sobrevalorar a L2. Si H1 sale floja por esto, la salida es un L2
   entrenado con las tareas de T2.2 retenidas, no cambiar la cabeza.
2. L0 aquí entrena con todo train (spec); la columna «L0 (línea base)» de `delta.md` es la de `lineas_base/resultados.json`, que entrena
   con 32 por clase. Ambas entran en «mejor capa».

### Criterios (`delta.md`)

- H1: la conjunta saca ≥ máx(L0 línea base, L0 completo, L2) + 0,01 de macro-F1 en ≥ 3 de las 5 tareas y cumple el listón
  (≥ 0,95 × la mejor referencia = máx(L0, kNN-32, THX-01) de `lineas_base/resultados.json`) en ≥ 4.
- Se refuta si no supera a la mejor capa (Δ > 0) en ≥ 3 tareas.
- `caida.md` (con `--renombrar`): conjunta y L2 con las opciones renombradas a A/B/C. L0 no depende del nombre: se usa por posición
  (equivale a buscar por `origen`). Los prototipos se buscan por `origen` como en `evaluar.py`. Las filas `noul` no se renombran
  (hatecheck, inyecciones): su caída es 0 por construcción.

## H2: fusión temprana (solo diseño, no implementada)

Si H1 falla porque la información de L0 llega demasiado tarde para corregir lo que L2 representa mal, meter las características de
L0 dentro de la red:

- **Opción A, ranuras**: proyectar el vector TF-IDF de caracteres (SVD a 256, ajustada solo con train y `fit` fuera de pliegue
  para el entrenamiento de L2) y añadirlo como ranura extra (K+1) en `Ranuras`/`simproto`, con el prototipo de clase calculado
  igual. Cambia `modelo.py`: otra tarea.
- **Opción B, torre**: concatenar al vector de la opción un vector de clase aprendido a partir de las log-probs de L0
  (`MLP(log P_L0) → d`), de modo que `maxsim` ve a L0 como parte de la similitud. Hay que entrenar con L0 fuera de pliegue (el
  mismo mecanismo de aquí) o L2 aprenderá a confiar en un L0 que en train acierta de más.
- Riesgos: reentrenar L2 (g5, horas), y la fuga de L0 en train se complica porque entra en el gradiente. Solo si H1 sale entre
  media y buena y falta el último punto.

## Cómo se lanza

Pasos y comandos (el orquestador hace los tres primeros):

1. `bash model/l2/aws/empaquetar_conjunta.sh > codigo.tgz`: es `empaquetar.sh` más `model/lineas_base/correr.py` (L0 con el mismo
   código que las líneas base; `empaquetar.sh` no lo lleva). `conjunta.py` y `conjunta.sh` ya van dentro (`model/l2/*.py|sh`).
   Subirlo a `$CHISPA_S3/codigo.tgz`.
2. Sustituir en `model/l2/aws/conjunta.sh` `__CHISPA_S3__` (prefijo de resultados) y, si no es el de T2.1b, `__CKPT__`
   (por defecto `s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt`). Va como user-data de una g5.xlarge con la AMI de
   `arranque.sh`; apaga a los 120 min.
3. Resultados en `$CHISPA_S3`: `resultados.tgz` (`pred*/`, `resultados*.json`, `cabezas.json`, `delta.md`, `caida.md`), `log.txt`, y
   las características en `caracteristicas/<tarea>.npz`.

Reutilizar las características (cambiar solo las cabezas): `conjunta.sh` baja primero `caracteristicas/<tarea>.npz`; si coinciden
con los datos y el sha del checkpoint, no las recalcula. Fuera de AWS, sin GPU:

```
python -m model.l2.conjunta --fase cabezas --renombrar --cache DIR_NPZ --datos DIR_CONVERTIDOS --salida DIR
```

Prueba en seco: `CHISPA_LOCAL=1 bash model/l2/aws/conjunta.sh` (con `__CHISPA_S3__` sustituido por un prefijo `s3://…` local y
`codigo.tgz` en `/tmp/chispa/s3/<prefijo>/`). Usa solo herramientas recortada a 500 filas y un checkpoint sin entrenar si no hay
.pt: valida el cableado, no los números.

Coste de cómputo previsto: L0 fuera de pliegue (6 ajustes de LR por tarea, CPU) domina; L2 en GPU es minutos. g5.xlarge ≈ 1,0 USD/h.
