# G.8b, barrido de λ y τ para esquemas nuevos (c6a, checkpoint de G.8 corrida 2, 2026-10-29)

## λ recomendado (fórmula del runtime: w = k/(k+λ))
- **L2: λ = ∞ por defecto** (zero-shot, solo la descripción).
  - En JevBench (1–2 ejemplos por opción), λ = ∞ da 0,304 de macro-F1 frente a 0,15–0,18 con cualquier λ finito.
  - Con 8 ejemplos de verdad, como en las tareas no vistas, el soporte ayuda poco y de forma desigual: en massive λ = 0–2
    da ≈ 0,25 frente a 0,15 con ∞, y en hatecheck lo mejor es λ = 8.
  - El soporte de L2 debería ir por el modo «con datos del cliente» (CONJ), no por el shrinkage por defecto.
- **L1: λ = 4.**
  - massive 0,395 (con ∞: 0,266), inyecciones 0,740 (0,326), hatecheck 0,492 (0,224) y JevBench 0,379 (0,398).
  - En L1 el soporte ayuda mucho y λ = 4 casi no pierde en JevBench.

## τ para esquemas nuevos (L2, λ = ∞, tareas no vistas, n = 1.077)
| objetivo | τ | abstención | precisión |
|---|---|---|---|
| precisión 0,95 | 0,846 | **96,9 %** | 0,95 |
| abstención ≤ 20 % | **0,276** | 20 % | **0,529** |

- Con esquemas nuevos, **L2 no puede dar precisión alta sin abstenerse casi siempre**. JevBench lo confirma: τ = 0,924 da
  93,5 % de abstención, y τ = 0,389 da 20 % con precisión 0,53.
- El valor que elija Juan depende del uso:
  - **0,846** si el producto prefiere escalar;
  - **0,276** si prefiere contestar (precisión ≈ 0,53).

## `.chispa` con score K ≥ 3: falló otra vez (segunda vez)
`calibrar.py:76` (`probs_de`) da `TypeError: Tensor + list`. Para `scoreK`, `p["b"]` es la lista de umbrales y el código lo
trata como un escalar. No lo relanzo: **se escala**. El arreglo es leer los umbrales de `scoreK#j` o la lista en
`probs_de`. Ver `calib-score.log`.

Coste: una c6a de 3 min, ≈ 0,01 USD.
