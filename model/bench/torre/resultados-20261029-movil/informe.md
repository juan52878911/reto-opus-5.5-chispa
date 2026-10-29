# P2b: perfil móvil, variantes de consulta y torre

Frente a PyTorch fp32 (checkpoint real, max_tok 256). Cumple = top-1 ≥ 0,93 y consulta y torre ≤ 60 MB.

Poda ampliada: 55000 ids → 60485 con 4020938 textos del corpus. `<unk>` en la comprobación (348396 textos que no están en el corpus): 1,60 % antes, 0,08 % después.

| variante | vocabulario | consulta MB | torre MB | coseno h (media / mín) | coseno S | top-1 | torre p50 / p99 ms | consulta p50 / p99 ms | `<unk>` % | cumple |
|---|---|---|---|---|---|---|---|---|---|---|
| dinamico | completo | 121,1 | 119,6 | 0,970 / 0,921 | 0,994 | 0,86 | 9,6 / 13,5 | 5,3 / 12,2 | 0,00 | no |
| dinamico | poda ampliada | 50,3 | 48,8 | 0,905 / 0,634 | 0,994 | 0,87 | 9,7 / 13,3 | 5,2 / 12,2 | 0,08 | no |
| ffn-estatico | completo | 142,8 | 141,3 | 0,814 / 0,614 | 0,957 | 0,67 | 12,3 / 17,1 | 7,2 / 15,8 | 0,00 | no |
| ffn-estatico | poda ampliada | 72,0 | 70,5 | 0,801 / 0,552 | 0,957 | 0,68 | 12,3 / 16,8 | 7,1 / 15,8 | 0,08 | no |
| fp16 | completo | 236,7 | 236,0 | 1,000 / 1,000 | 1,000 | 1,00 | 17,3 / 22,9 | 10,6 / 22,0 | 0,00 | no |
| fp16 | poda ampliada | 93,1 | 92,4 | 0,931 / 0,813 | 1,000 | 0,90 | 16,8 / 23,3 | 10,5 / 21,8 | 0,08 | no |
| fp32 | completo | 473,1 | 471,6 | 1,000 / 1,000 | 1,000 | 1,00 | 16,1 / 21,5 | 9,9 / 20,7 | 0,00 | no |
| fp32 | poda ampliada | 183,9 | 182,4 | 0,931 / 0,813 | 1,000 | 0,90 | 16,4 / 21,9 | 9,9 / 21,1 | 0,08 | no |

Cumplen: ninguna.
