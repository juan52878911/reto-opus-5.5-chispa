# Corrida local con esquemas (nodo-b) — NO es cifra del i7

`correr.sh -m l1 -c "1 4 16" -d 10s -n 1 -E esquemas-carga.json -L uno|ocho -t textos-es-co.txt`, con los `.chispa` de `server/testdata` y sin modelos reales
(sin L1 ni L2 útiles, sin ORT). Todas las decisiones acaban en `escalar` (los `.chispa` de testdata no conocen estos esquemas), así que mide el coste de
HTTP + validación + cascada vacía, no el de L1/L2. Una sola tanda por punto, nodo WSL compartido: sin valor como objetivo del i7.

| lote | c | preguntas/s | peticiones/s | p99 ms |
|---|---|---|---|---|
| uno | 1 | 2536 | 2536 | 0.61 |
| uno | 4 | 6723 | 6723 | 1.28 |
| uno | 16 | 13467 | 13467 | 3.09 |
| ocho | 1 | 14815 | 1852 | 0.95 |
| ocho | 4 | 36953 | 4619 | 1.76 |
| ocho | 16 | 57474 | 7184 | 5.95 |

Detalle y entorno: los `resultados-*-2302*.md/.csv` y `-2306*` de esta misma carpeta (uno por lote).
