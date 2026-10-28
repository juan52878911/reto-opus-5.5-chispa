# Fase 2: informe de L2 y propuesta de G2 (2026-10-28)

Encargo: `plan/fase-2/encargo.md`. Decisión de Juan del 2026-10-28: «C y después b».

## Criterios
| criterio | resultado | dónde |
|---|---|---|
| T2.1: L2 con el codificador congelado, ≥ +5 sobre kNN-32 en ≥ 3 tareas | **no** (3 rondas) | `model/l2/resultados/ronda1…ronda3-t22` |
| T2.2: L2 solo, ≥ 0,95 × mejor referencia y caída al renombrar ≤ 5 | **no** con L2 solo; **sí con la cabeza conjunta L0 + L2 (b)** en 5/5, con caída ≤ 0,1 | `model/l2/resultados/t22c-conjunta`, `t22d-conjunta` |
| (c) cascada L0 → L2 frente al listón | sí, 5/5; con L0 completo, la conjunta (b) le gana en 4/5 | `model/cascada/resultados/2026-10-28`, `t22d-conjunta` |
| T2.4, redefinido por tarea el 2026-10-28 (ver abajo) | **3 de 5 cumplen** (clinc150, massive y herramientas); hatecheck e inyecciones no, por ECE | `t22d-conjunta/cvtest/calibracion.md` |
| T2.5: `.chispa` v3 con fuzz | sí, y además las secciones CONJ y L0TF con fuzz | `format/chispa3` |
| T2.6: L2 ≤ 60 MB y p99 < 50 ms a 64 tokens en AVX2 | sí: 48 MB y 20 ms en la c6a; de punta a punta, p99 de 9,6–11,3 ms | `server/deploy/resultados/` |
| T2.6: ASR de la Arena ≤ 0,15 | **sí**: el detector cascada saca 0,021 en spam y en injection, pero se abstiene en el 83 % y el 47 % de los ataques | `server/deploy/resultados/arena-20261028/LEEME.md` |
| De punta a punta, H2: `/v1/decide` a ≤ 1 punto de `conjunta.py` | sí: massive 0,814 frente a 0,817 y clinc150 0,887 frente a 0,890 | `server/deploy/resultados/e2e-20261028/LEEME.md` |

## Qué es L2 en el producto
- **Cascada del servidor.** Primero responde L0 (TF-IDF de caracteres con LR, sección L0TF), si su confianza llega a τ:
  el 54–57 % de las consultas, con p99 de 0,2 ms. El resto lo responde L2c: e5-small int8 con ranuras y prototipos de los
  ejemplos del cliente, más una cabeza `lr` sobre [log-probs de L0, similitudes de L2]. Su p99 es de unos 10 ms en la c6a.
- **Entrenamiento.** Todo lo que depende del cliente (L0, prototipos y cabeza) lo entrena `chispa train --conjunta`. L2
  (el codificador y las ranuras) es genérico.
- **L1.** potion con prototipos ayuda en la cascada (T2.7). Con el L1 del servidor (zs), no. El L1 propio destilado no
  supera a potion (T3.1c).

## T2.4 con el criterio por tarea (cifras de T2.2d, cabeza `cvtest`, sin cómputo nuevo)
| tarea | macro-F1 | ¿se calibra? | ECE usado | ECE ≤ 0,05 | cobertura a p 0,95 | exigida (F1 ≥ 0,85) | resultado |
|---|---|---|---|---|---|---|---|
| clinc150 | 0,891 | sí | 0,022 | sí | 80 % | sí, ≥ 70 % | **cumple** |
| inyecciones | 0,922 | no (116 filas ≤ 500) | 0,053 | **no, por 0,003** | 84 % | sí, ≥ 70 % | **no cumple por ECE** |
| massive | 0,818 | sí | 0,012 | sí | 72 % | no: curva | **cumple** (curva pendiente) |
| herramientas | 0,734 | sí | 0,037 | sí | 49 % | no: curva | **cumple** (curva pendiente) |
| hatecheck | 0,667 | sí | 0,060 (sin calibrar, 0,058) | **no** | 7 % | no: curva | **no cumple por ECE** |

- Cumplen 3 de 5: clinc150, massive y herramientas.
- **inyecciones** queda a 0,003 del ECE con n = 116. Con tan pocas filas, ese margen está dentro del ruido: el
  intervalo de un ECE con 116 filas es mucho más ancho que 0,003. Lo señalo, pero no cambio el criterio.
- **hatecheck** no cumple: ni la temperatura ni Platt bajan su ECE de 0,058.
- **Curvas de cobertura** de massive, herramientas y hatecheck: publicadas en `model/l2/resultados/t22d-conjunta/curvas/`
  (tabla cada 5 % de cobertura y SVG).

## Para Juan (G2)
1. **T2.4: decidido** (criterio por tarea). Cumplen 3 de 5. Fallan hatecheck (ECE 0,058–0,060) e inyecciones (ECE 0,053 con
   116 filas, sin calibrar).
2. **ASR de la Arena: medido, cumple.** Queda abierta la abstención: medir el escalado con tráfico no adversarial antes de
   los pilotos.
3. **Dónde se ajusta la cabeza.** En hatecheck, la que se ajusta fuera de pliegue sobre datos del cliente rinde más que la
   que se entrena en train (T2.2d). En producto, eso significa ajustarla con los ejemplos del cliente, que es lo que ya hace
   `chispa train`.

## Coste de la fase
- AWS: menos de 5 USD en total en el día (g5 y c6a/m6a, spot cuando había capacidad).
- Workers: 21,3 USD de cuenta en el día (`delega spend`, perfil personal).

## Cierre de G2 (2026-10-28)
| criterio | estado |
|---|---|
| T2.1, L2 solo con el codificador congelado | no, superado por (b) según la decisión de Juan |
| T2.2, con la cabeza conjunta | sí, 5/5 |
| T2.4, por tarea | 3/5: hatecheck e inyecciones fallan por ECE (0,058 y 0,053) |
| T2.5, formato | sí |
| T2.6: tamaño, latencia y punta a punta | sí |
| T2.6: ASR | sí, con abstención alta |

**Propuesta: G2 pasa con dos excepciones anotadas.** Una es el ECE de hatecheck e inyecciones. La otra es la abstención
ante ataques, que hay que medir con tráfico normal en la fase 4. Si G2 pasa con esas excepciones lo decide Juan.

**Decisión de Juan (2026-10-28): G2 pasa**, con las dos excepciones anotadas: el ECE de hatecheck e inyecciones y la
abstención. **Abstención máxima con tráfico normal: 20 % por ahora.**
