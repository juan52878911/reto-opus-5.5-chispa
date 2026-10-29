# D1f: la base de `chispa train --ckpt` ya da la paridad sin pasos manuales (integracion @ ea79c2b)

- **Con qué:** `exportar` escribe la CALIB de L2 de todas las cabezas (`calib_completa`), y el SDK (TZ) la copia a
  `tipos_l2`.
- **`tipos_l2` OK, idéntico al checkpoint.** Trae `choice`, `noul`, `score2`…`score5` y sus `#j`.
- **Exactitud de la base: 0,494.**

  | tipo | exactitud | Python |
  |---|---|---|
  | choice | 0,482 | 0,468 |
  | noul | 0,554 | 0,554 |
  | score | 0,333 | 0,333 |

  Hay 0 discrepancias en 78 casos.
- **El «replay máx 0,375» de `diag-base.md` es del script, no del producto.** El replay leía `tipos`, la CALIB de L1, en
  vez de `tipos_l2`. Arreglado en el commit siguiente.
- `tau_escalate_l2` = 0,93, y escalan 211 de 231 casos.
