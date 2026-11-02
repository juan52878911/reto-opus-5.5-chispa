# Ajuste fino de G.8 (aumento + español) frente a G.8, medidos en la misma máquina

## JevBench k=0

| | exactitud | macro-F1 |
|---|---|---|
| nuevo | 0.4935 | 0.3225 |
| G.8 | 0.4805 | 0.3008 |

## M3: % de decisiones de L2 que cambian (umbral 5 %)

| variante | nuevo | G.8 |
|---|---|---|

## M4: exactitud es − en (puntos)

| par | nuevo | G.8 |
|---|---|---|
| **media** | -3.2 | -3.3 |
| massive | -6.0 | -6.2 |
| paws-x | -1.5 | +0.0 |
| sib200 | -6.9 | -5.9 |
| xnli | +1.5 | -1.3 |

## M3 en CPU (c6a, estabilidad.sh con cada checkpoint): % de decisiones de L2 que cambian (umbral 5 %)
| variante | nuevo | G.8 |
|---|---|---|
| permutar | 0,0 | 0,0 |
| renombrar | **35,6** | 37,6 |
| parafrasear | **9,6** | 9,5 |
| erratas | **10,9** | 12,8 |
| mayúsculas | **23,0** | 24,0 |
| mezcla | **5,6** | 6,1 |
| largo | **53,6** | 61,5 |
| pregunta en inglés | **14,7** | 16,6 |
| esquema en inglés | **7,5** | 15,0 |

## M5 score (los dos checkpoints)
- G.8: 0,333 · nuevo: 0,278 (n = 18 en JevBench). Reajustar los umbrales no recupera nada; el oráculo de umbrales por esquema
  llega a 0,667.
- **ρ de Spearman entre s y el nivel: −0,52**, de media por esquema. **s ordena los niveles al revés.** Antes de gastar GPU hay
  que descartar un error de orientación (la torre del nivel máximo, o la semántica de los niveles en JevBench).

## Veredicto del criterio
- JevBench: +1,3 puntos. **Cumple.**
- es/en: −3,2 frente a −3,3. **No cumple** (umbral < 3).
- Ninguna variante por encima del 5 % en L2: **no cumple** (8 de 9). Mejora en esquema en inglés (15,0 → 7,5) y largo
  (61,5 → 53,6); poco o nada en el resto.
