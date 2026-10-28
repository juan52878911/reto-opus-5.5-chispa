# Fase 2: informe de L2 y propuesta de G2 (2026-10-28)

Encargo: `plan/fase-2/encargo.md`. Decisión de Juan del 2026-10-28: «C y después b».

## Criterios
| criterio | resultado | dónde |
|---|---|---|
| T2.1: L2 con el codificador congelado, ≥ +5 sobre kNN-32 en ≥ 3 tareas | **no** (3 rondas) | `model/l2/resultados/ronda1…ronda3-t22` |
| T2.2: L2 solo, ≥ 0,95 × mejor referencia y caída al renombrar ≤ 5 | **no** con L2 solo; **sí con la cabeza conjunta L0 + L2 (b)** en 5/5, con caída ≤ 0,1 | `model/l2/resultados/t22c-conjunta`, `t22d-conjunta` |
| (c) cascada L0 → L2 frente al listón | sí, 5/5; con L0 completo, la conjunta (b) le gana en 4/5 | `model/cascada/resultados/2026-10-28`, `t22d-conjunta` |
| T2.4: ECE ≤ 0,05 y cobertura a precisión 0,95 ≥ 70 % | **parcial**: ECE en 3/5 y cobertura en 2/5 (clinc150 y massive) | `t22d-conjunta/LEEME.md` |
| T2.5: `.chispa` v3 con fuzz | sí, y además las secciones CONJ y L0TF con fuzz | `format/chispa3` |
| T2.6: L2 ≤ 60 MB y p99 < 50 ms a 64 tokens en AVX2 | sí: 48 MB y 20 ms en la c6a; de punta a punta, p99 de 9,6–11,3 ms | `server/deploy/resultados/` |
| T2.6: ASR de la Arena ≤ 0,15 | **sin medir** | — |
| De punta a punta, H2: `/v1/decide` a ≤ 1 punto de `conjunta.py` | sí: massive 0,814 frente a 0,817 y clinc150 0,887 frente a 0,890 | `server/deploy/resultados/e2e-20261028/LEEME.md` |

## Qué es L2 en el producto
- **Cascada del servidor.** Primero responde L0 (TF-IDF de caracteres con LR, sección L0TF), si su confianza llega a τ:
  el 54–57 % de las consultas, con p99 de 0,2 ms. El resto lo responde L2c: e5-small int8 con ranuras y prototipos de los
  ejemplos del cliente, más una cabeza `lr` sobre [log-probs de L0, similitudes de L2]. Su p99 es de unos 10 ms en la c6a.
- **Entrenamiento.** Todo lo que depende del cliente (L0, prototipos y cabeza) lo entrena `chispa train --conjunta`. L2
  (el codificador y las ranuras) es genérico.
- **L1.** potion con prototipos ayuda en la cascada (T2.7). Con el L1 del servidor (zs), no. El L1 propio destilado no
  supera a potion (T3.1c).

## Para Juan (G2)
1. **Umbral de cobertura de T2.4.** Con un macro-F1 de 0,67–0,73, hatecheck y herramientas no pueden cubrir el 70 % con
   precisión 0,95. ¿Se mantiene ese umbral, se baja, o se mide por tarea?
2. **ASR de la Arena** (spam e inyección): falta medirlo con la cascada nueva.
3. **Dónde se ajusta la cabeza.** En hatecheck, la que se ajusta fuera de pliegue sobre datos del cliente rinde más que la
   que se entrena en train (T2.2d). En producto, eso significa ajustarla con los ejemplos del cliente, que es lo que ya hace
   `chispa train`.

## Coste de la fase
- AWS: menos de 5 USD en total en el día (g5 y c6a/m6a, spot cuando había capacidad).
- Workers: unos 15 USD de cuenta en el día.
