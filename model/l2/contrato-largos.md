# Contrato de textos largos de L2 (M2)

Para la sesión que lo implemente en el runtime. Referencia ejecutable: `model/l2/largos.py` (`tokenizar`, `ventanas`, `agregar`,
`probs_de_s`); sus tests (`model/l2/tests/test_largos.py`) fijan cada número de aquí. **Qué estrategia usar lo dice la corrida de
`model/l2/aws/estabilidad.sh` (`largos.md`, línea «Recomendación»)**; este documento define las cinco para que el runtime pueda
implementar la que salga sin dudas. Si no sale ninguna con IC95 que no se solape en los casos largos, se queda `cabeza` (lo actual).

## Tokenización (común)
1. Tokeniza `"query: " + texto` con el tokenizador de e5 **sin** tokens especiales (`add_special_tokens=False`, sin truncar). Los
   3 primeros ids (`▁que`, `ry`, `:`; es la tokenización de `"query:"`) son el **prefijo** `P`; el resto es el **cuerpo** `C`, de `n` ids.
2. Presupuesto `b = max_tok − 2 − len(P)` (los 2 son `<s>` y `</s>`). Con `max_tok` 256, `b = 251`. `max_tok` es el del checkpoint.
3. Una **ventana** es `P + trozo de C`. El modelo recibe `[<s>] + ventana + [</s>]`, de a lo sumo `max_tok` ids, atención 1 en todos
   (relleno solo para agrupar ventanas en un lote). El prefijo se repite en todas las ventanas.
4. Si `n ≤ b` solo hay una ventana, `P + C`, y las cinco estrategias coinciden: los textos cortos no cambian.
5. Es **largo** el caso con `n > b` (es el que trunca hoy la cabeza).

## Ventanas, con `n > b`
| estrategia | ventanas |
|---|---|
| `cabeza` | `P + C[:b]` (idéntico a `truncation=True, max_length=max_tok`) |
| `cola` | `P + C[n−b:]` |
| `cabeza_cola` | `P + C[:b − t] + C[n−t:]` con `t = b // 2` (la cabeza se queda con el id impar); una sola ventana de exactamente `max_tok` ids con los especiales; si `t = 0`, solo cabeza |
| `trozos_max`, `trozos_media` | inicio `i₀ = 0`, paso `p = max(1, b − 32)`: ventana `j` = `P + C[j·p : j·p + b]`; se para en la primera ventana con `j·p + b ≥ n`. Solape de 32 ids entre vecinas, la última puede ser más corta, número de ventanas `1 + ceil((n − b) / p)` |

## Agregación y cabeza
- Para cada ventana, `s_w` es el vector de MaxSim de la consulta contra las opciones: `s_w[u] = max_k softplus(h_u · slot_k(w))`, con las
  ranuras calculadas **sobre esa ventana** y el vector de torre `h_u` de la opción (o de la consulta de noul/score) **una sola vez por caso**
  (no depende del mensaje).
- `trozos_max`: `s[u] = max_w s_w[u]`. `trozos_media`: `s[u] = mean_w s_w[u]`. Las estrategias de una ventana usan `s = s_0`.
- La cabeza se aplica **después** de agregar, sobre `s`, igual que hoy sobre un solo pase: choice `softmax(s / T)`; noul `σ(a·s₀ + b)`;
  score CORAL `P(y>j) = σ(w·s₀ − θ_j)` y la etiqueta es la mediana (nº de umbrales con `P(y>j) > 0,5`). La CALIB del `.chispa` (T, a, b, θ)
  no cambia: no se recalibra por la estrategia.
- Sin soporte (k = 0) está medido. Con prototipos (k > 0), el término `simproto` de cada ventana se agregaría igual que `s`, pero no está medido.

## Coste
`cabeza`, `cola` y `cabeza_cola`: un pase por caso, igual que hoy. Los trozos: `1 + ceil((n − b)/(b − 32))` pases de encoder por caso largo
(`largos.md` da tokens y pases medios por caso largo); las ventanas de un caso se pueden agrupar en un lote.

## Paridad con Python
Comprobar: los ids de cada ventana (con `<s>`/`</s>`) iguales a `largos.ventanas` + `con_especiales`, y la `s` agregada con diferencia
< 1e-4 sobre la misma ventana. Los casos de prueba son los de `model/l2/tests/test_largos.py` (cuerpos de 37, 68, 69, 100 y 250 ids, `max_tok` 40 y un prefijo inventado de 2 ids).

La estrategia por defecto sigue siendo `cabeza`: en M2 dio 0,485 global y 0,366 en los 82 casos largos, y cola, cabeza+cola y trozos no la superan (`model/l2/resultados/estabilidad-20261029/m2/`).
