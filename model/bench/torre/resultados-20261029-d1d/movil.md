# P2b: perfil móvil, variantes de consulta y torre

Frente a PyTorch fp32 (checkpoint real, max_tok 256). Cumple = top-1 ≥ 0,93 y consulta y torre ≤ 60 MB.

Poda ampliada: 55000 ids → 55016 con 1360 textos del corpus. `<unk>` en la comprobación (2160 textos que no están en el corpus): 7,25 % antes, 7,23 % después.

`<unk>` de lo medido (antes → después de ampliar): torres de `h` 7,55 → 6,76 %, opciones 7,89 → 7,11 %, mensajes 0,00 → 0,00 %. La fila «+ textos medidos» amplía además con esos textos: aísla la poda de los `<unk>`.

| variante | vocabulario | consulta MB | torre MB | coseno h (media / mín) | coseno S | top-1 | torre p50 / p99 ms | consulta p50 / p99 ms | `<unk>` % | cumple |
|---|---|---|---|---|---|---|---|---|---|---|
| fp16 | poda ampliada | 88,9 | 88,2 | 0,931 / 0,813 | 1,000 | 0,90 | 16,4 / 22,3 | 10,2 / 21,3 | 7,23 | no |
| fp16 | poda ampliada + textos medidos | 88,9 | 88,2 | 1,000 / 1,000 | 1,000 | 1,00 | 16,2 / 22,3 | 10,1 / 21,6 | 0,00 | no |
| fp32 | poda ampliada | 175,5 | 174,0 | 0,931 / 0,813 | 1,000 | 0,90 | 15,4 / 21,2 | 9,7 / 20,3 | 7,23 | no |
| fp32 | poda ampliada + textos medidos | 175,5 | 174,0 | 1,000 / 1,000 | 1,000 | 1,00 | 15,5 / 21,1 | 9,7 / 20,4 | 0,00 | no |

Cumplen: ninguna.
