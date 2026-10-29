# D1e: paridad servidor ↔ Python en JevBench, cerrada (integracion @ 458ed94, chispa-sdk f91e143 fusionado)

| pasada | total | choice | noul | score | discrepancias (78 casos) |
|---|---|---|---|---|---|
| base (`.chispa` de `chispa train --ckpt --torre`) | 0,463 | 0,482 | 0,473 | 0,278 | 13, todas por CALIB |
| CALIB del checkpoint en `tipos_l2` | **0,494** | **0,482** | **0,554** | **0,333** | **0** |
| (c) más la consulta fp32 sin poda | 0,494 | 0,482 | 0,554 | 0,333 | 0 |
| Python k = 0 | 0,485 | 0,468 | 0,554 | 0,333 | — |

## Qué cerró el hueco
- **X1** (consulta fp32 sin poda en `chispa train`): choice pasa de 0,439 a 0,482.
- **Peticiones de JevBench con las descripciones de `true` y de los niveles** (`cuerpo_decide`): los textos de la torre
  coinciden con los de Python en el 100 % de los casos.
- **CALIB del checkpoint en `tipos_l2`:** noul y score quedan iguales a Python.

La pasada (c) ya no aporta nada, porque desde X1 la base usa la consulta fp32.

## Queda para el producto
- **`tipos_l2` FALLO en la base.** `chispa train --ckpt` no calibra: solo escribe en `tipos_l2` el tipo del esquema de
  entrenamiento, `choice`. En esquemas nuevos, noul y score usan los valores por defecto del servidor.
  - Arreglo propuesto: que el exportador, o `chispa train`, escriba en `tipos_l2` las cabezas del checkpoint de todos los
    tipos (`cabeza_inicial`, θ = 0,5).
- **`tau_escalate_l2` = 0,93**, el tope de τ a precisión 0,95. Con él escalan 211 de 231 casos.

## Perfil móvil (fp16 con poda ampliada)
- Ocupa 89 MB y da top-1 0,90, con un 7,2 % de `<unk>`.
- Ampliando la poda con los textos medidos, el top-1 sube a 1,00.
- Ninguna variante cumple ≤ 60 MB.
