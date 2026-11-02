# (a) Orientación de score con G.8 (c6a.2xlarge, `38342fe`, 16 min, ≈ 0,1 USD)

| torre | ρ medio por esquema (JevBench) | exactitud CORAL |
|---|---|---|
| nivel máximo (la actual) | −0,52 | 0,333 |
| nivel mínimo | −0,66 | 0,278 |
| s invertida | +0,52 | 0,278 |
| clase mayoritaria | | 0,556 |

En el dev de score del meta, el ρ con la torre máxima es **+0,12**: positivo pero débil.

**Veredicto: no es un fallo de código.** El modelo ordena (poco) bien en el meta y no generaliza a JevBench.
- El signo es coherente (`w` ≈ 3,94 > 0 en todas las cabezas, con la misma torre en entrenamiento y en evaluación).
- La conversión de JevBench es correcta.
- Con las dos torres el ρ sale negativo. La s está más alta en los mensajes de nivel bajo, sea cual sea la descripción, así
  que la torre no discrimina por nivel.
- Solo hay **un esquema con más de 1 caso** (n = 12). La cifra de JevBench es muy ruidosa.

**M1 (batería), aún sin valor:** 100 % de filas «sin probs». El servidor escala sin devolver `probs` en todas las filas, p50 de
1,8 ms. Pasado a la otra sesión.
