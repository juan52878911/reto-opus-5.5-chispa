# M2 textos largos (max_tok 256)

231 casos, 82 largos (la cabeza los trunca). IC95 por bootstrap sobre casos.

| estrategia | global | IC95 | choice | noul | score | largos | IC95 largos | Δ vs cabeza (IC95) | tokens/caso largo | pases |
|---|---|---|---|---|---|---|---|---|---|---|
| cabeza | 0.485 | 0.420–0.550 | 0.468 | 0.554 | 0.333 | 0.366 | 0.256–0.463 | +0.000 [+0.000, +0.000] | 256 | 1.0 |
| cola | 0.446 | 0.381–0.511 | 0.446 | 0.473 | 0.333 | 0.256 | 0.171–0.354 | -0.110 [-0.220, +0.000] | 256 | 1.0 |
| cabeza_cola | 0.468 | 0.403–0.528 | 0.432 | 0.568 | 0.333 | 0.317 | 0.220–0.427 | -0.049 [-0.122, +0.024] | 256 | 1.0 |
| trozos_max | 0.481 | 0.416–0.545 | 0.475 | 0.541 | 0.278 | 0.354 | 0.256–0.451 | -0.012 [-0.073, +0.049] | 1693 | 7.0 |
| trozos_media | 0.476 | 0.411–0.541 | 0.468 | 0.527 | 0.333 | 0.341 | 0.244–0.451 | -0.024 [-0.110, +0.049] | 1693 | 7.0 |

Recomendación: **cabeza** (ninguna gana con IC que no se solape ni empata siendo más barata).
