# G.8b: barrido de λ en test

λ = κ de G.8 (`formula-shrinkage.md`): peso de la descripción λ/(λ+n); λ = 0 solo ejemplos, λ = ∞ zero-shot. k = 8 por clase/esquema. Macro-F1. κ elegido en dev: 1. `tasksource_fuera` no tiene train: no depende de λ.

### Tareas no vistas (macro-F1 global por conjunto)

| tarea | λ=0 | λ=1 | λ=2 | λ=4 | λ=8 | λ=∞ |
|---|---|---|---|---|---|---|
| hatecheck | 0.531 | 0.537 | 0.540 | 0.536 | 0.569 | 0.531 |
| inyecciones | 0.362 | 0.362 | 0.344 | 0.326 | 0.326 | 0.326 |
| massive | 0.249 | 0.241 | 0.248 | 0.236 | 0.236 | 0.153 |

### JevBench (macro-F1 por familia)

| tarea | λ=0 | λ=1 | λ=2 | λ=4 | λ=8 | λ=∞ |
|---|---|---|---|---|---|---|
| adequacy | 0.378 | 0.378 | 0.378 | 0.200 | 0.000 | 0.333 |
| adversarial | 0.714 | 0.714 | 0.714 | 0.714 | 0.714 | 0.714 |
| ambiguous | 0.583 | 0.583 | 0.583 | 0.583 | 0.583 | 0.583 |
| extraction | 0.000 | 0.010 | 0.000 | 0.000 | 0.000 | 0.306 |
| fact | 0.077 | 0.077 | 0.077 | 0.077 | 0.143 | 0.556 |
| intent | 0.135 | 0.109 | 0.109 | 0.105 | 0.167 | 0.786 |
| judge_hard | 0.344 | 0.410 | 0.393 | 0.393 | 0.271 | 0.410 |
| long_policy | 0.190 | 0.190 | 0.190 | 0.190 | 0.190 | 0.190 |
| multi_hop | 0.200 | 0.200 | 0.200 | 0.200 | 0.200 | 0.200 |
| ordinal | 0.167 | 0.100 | 0.000 | 0.000 | 0.000 | 0.125 |
| policy | 0.378 | 0.378 | 0.143 | 0.000 | 0.000 | 0.496 |
| probability | 0.200 | 0.200 | 0.200 | 0.200 | 0.200 | 0.200 |
| routing | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.283 |
| routing_hard | 0.111 | 0.111 | 0.111 | 0.111 | 0.111 | 0.111 |
| temporal_numeric | 0.121 | 0.121 | 0.121 | 0.121 | 0.121 | 0.121 |
| tool_selection | 0.147 | 0.107 | 0.107 | 0.214 | 0.537 | 1.000 |
| tradeoff | 0.185 | 0.185 | 0.185 | 0.185 | 0.185 | 0.185 |
| trap | 0.185 | 0.185 | 0.185 | 0.185 | 0.185 | 0.185 |
| (global) | 0.156 | 0.151 | 0.149 | 0.154 | 0.178 | 0.304 |

### L1 (potion con prototipos; macro-F1 global por conjunto)

| tarea | λ=0 | λ=1 | λ=2 | λ=4 | λ=8 | λ=∞ |
|---|---|---|---|---|---|---|
| hatecheck | 0.507 | 0.486 | 0.489 | 0.492 | 0.501 | 0.224 |
| inyecciones | 0.736 | 0.740 | 0.731 | 0.740 | 0.741 | 0.326 |
| jevbench | 0.358 | 0.347 | 0.353 | 0.379 | 0.387 | 0.398 |
| massive | 0.341 | 0.363 | 0.385 | 0.395 | 0.348 | 0.266 |

## τ para esquemas nuevos

Confianza = probabilidad top-1 (en score, la etiqueta es la mediana CORAL). Sobre las no vistas agrupadas, con λ = ∞ y con el λ elegido (1); JevBench solo como comprobación.

| fuente | λ | n | exactitud | τ (prec. 0,95) | abstención | τ (abst. ≤ 20 %) | abstención | precisión |
|---|---|---|---|---|---|---|---|---|
| no_vistas | ∞ | 1077 | 0.455 | 0.846 | 0.969 | 0.276 | 0.200 | 0.529 |
| no_vistas | 1 | 1077 | 0.515 | 0.975 | 0.978 | 0.421 | 0.200 | 0.589 |
| jevbench | ∞ | 231 | 0.485 | 0.924 | 0.935 | 0.389 | 0.199 | 0.530 |
| jevbench | 1 | 231 | 0.299 | 1.000 | 1.000 | 0.439 | 0.199 | 0.308 |

- **Recomendado** (λ = ∞, el valor por defecto del runtime, sobre las no vistas): τ = 0.846 para precisión 0,95 (abstención 0.969); τ = 0.276 deja la abstención en ≤ 20 % (precisión 0.529).
- Con el λ elegido (1): τ = 0.975 (abstención 0.978); τ = 0.421 para abstención ≤ 20 %.
- τ = 1,000 con abstención 1,000 significa que ningún corte llega a 0,95: no se puede garantizar esa precisión.
