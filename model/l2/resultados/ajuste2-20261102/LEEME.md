# (c) Segundo ajuste fino de G.8: 3 épocas, con W5 (RM4) (g5.xlarge, `0e0da2b`, 35 min, ≈ 0,6 USD)

**No cumple el criterio.**

| criterio | nuevo (c) | G.8 | ajuste 1 (2026-10-29) | ¿cumple (c)? |
|---|---|---|---|---|
| JevBench k = 0 | 0,4719 | 0,4805 | 0,4935 | sí (−0,9, dentro de −1) |
| es − en | −3,3 | −3,3 | −3,2 | no |
| variantes > 5 % en L2 | 8 de 9 | 8 de 9 | 8 de 9 | no |

- Más épocas de aumento no mueven la robustez. Renombrar se queda en el 35 % y mayúsculas en el 24 %. Solo bajan esquema en
  inglés (15 → 10,5 %) y largo (62 → 52 %).
- **Lectura:**
  - **Renombrar.** El id de la opción va dentro del texto de la torre («pregunta · id · descripción»). Con ids opacos
    solo en el 30 % de los episodios, el modelo sigue usando el id.
  - **Mayúsculas.** La variante de E2 no pone todo en mayúsculas, así que la regla del 70 % casi nunca se activa.

  Ninguna de las dos cosas se arregla con más épocas.
- **El mejor modelo disponible sigue siendo el ajuste 1** (`s3://…/ajuste-80ab8ef/ckpt/mejor.pt`), con JevBench 0,4935.
