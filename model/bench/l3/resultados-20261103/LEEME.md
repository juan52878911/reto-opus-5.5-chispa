# Prueba real de L3 con Ollama en el i7 (CT 109), 2026-11-03

- **Cascada:** `chispa-server` con `modelo-fp16-arm.chispa` (el fp16 seguro del ajuste 1, mismas respuestas que el fp32 en x86), L0+L1+L2 con torre al vuelo, con la config por defecto (`{}`), y L3 = `qwen3:4b-instruct` en Ollama 0.40.13.
  - La variante es `num_thread 4`, porque el CT tiene 4 núcleos; con los 6 hilos por defecto la generación iba a 0,27 tok/s.
  - `tau` 0,6, `timeout` 120 s, `max_por_peticion` 1.
- **Conjuntos** (español, test):
  - MASSIVE-es: 700 filas, submuestra determinista de las 2 974; choice de 60 intenciones;
  - HateCheck-es: las 361; noul.
  - Las PQRS no se usan: no pueden salir de kindling ni del bucket.
- **Método:**
  - pasada A, sin L3: escalada y argmax de L1/L2 por fila;
  - pasada B, con L3: solo las filas que escalaron, 393 en total.
  - Las dos pasadas con la misma config salvo `l3`. Una primera medida con la pasada A sin `-config` no era comparable: la mera presencia de config cambia el τ de L1. Se descartó.

| conjunto | escalada | L2/L1 en las escaladas | L3 en las escaladas | L3 opina | L3 cuando opina | cascada sin L3 → con L3 | L3 p50 / p99 | s por 1000 decisiones |
|---|---|---|---|---|---|---|---|---|
| hatecheck | 42,7 % (154/361) | 30,5 % | 76,6 % | 100,0 % | 76,6 % | 28,8 % → 48,5 % | 4,1 / 5,1 s | 1743,2 |
| massive | 34,1 % (239/700) | 20,5 % | 21,8 % | 2,9 % | 71,4 % | 43,6 % → 44,0 % | 4,1 / 120,0 s | 4064,4 |
| total | 37,0 % (393/1061) | 24,4 % | 43,3 % | 41,0 % | 76,4 % | 38,5 % → 45,5 % | 4,1 / 120,0 s | 3274,7 |

## Lectura
- **HateCheck (sí/no):** L3 contesta en todas las escaladas y acierta el 76,6 %, frente al 30,5 % del argmax de L2.
  - La cascada pasa del 28,8 % al 48,5 %.
  - Coste: ~4 s por escalada; ~29 min de CPU por cada 1000 decisiones con un 43 % de escalada.
- **MASSIVE (60 intenciones):** L3 casi nunca supera τ = 0,6 (opina en el 2,9 %; acierta 5 de 7) y la cascada apenas cambia (43,6 → 44,0 %).
  - Con 60 opciones el prompt es largo; algunas llamadas llegan al `timeout` de 120 s (p99).
- **Lo que dice:**
  - en el i7 sin GPU, L3 sirve como respaldo asíncrono para preguntas de pocas opciones, no para tiempo real;
  - con muchas opciones habría que recortar a las k mejores de L2 antes de llamar a L3, o calibrar su τ con datos propios;
  - las probabilidades de L3 son autodeclaradas, no calibradas.
- **Escalada con la config por defecto:** 37 % en estos dos conjuntos (MASSIVE 34 %, HateCheck 43 %), muy por debajo del 96–100 % de M1. M1 se midió con L1 apagada.
