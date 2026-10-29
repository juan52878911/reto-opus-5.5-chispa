# G.7c Arreglar `calibrar.py` para scoreK (umbrales como lista)

## Antecedentes
El paso «`.chispa` score» de `model/l2/aws/barrido.sh` falló en la c6a. El log está en
`model/l2/resultados/barrido-20261029/calib-score.log`:

```
File "model/l2/calibrar.py", line 76, in probs_de
    pt = torch.sigmoid(p["a"] * s[0] + p["b"])
TypeError: unsupported operand type(s) for +: 'Tensor' and 'list'
```

Para `scoreK`, `p["b"]` es la **lista** de umbrales `b_j`, y el código la trata como un escalar.

## Terminado cuando
- `probs_de` y todo lo que calibre o evalúe `score` en `calibrar.py` usa los umbrales como lista:
  - `P(y > j) = σ(a·s − b_j)`, con el signo y la convención de CORAL que ya usa `modelo.Coral` y documenta
    `model/l2/README.md`;
  - la etiqueta, por la mediana CORAL;
  - lo que se escribe en CALIB (`scoreK` con `a = w/T` y `b = b_1`, y `scoreK#j` con los incrementos) no cambia.
- Tests en `model/l2/tests/test_t24*.py` o en uno nuevo, con K = 3 y K = 5:
  - `probs_de` no falla;
  - las probabilidades suman 1;
  - la ida y vuelta CALIB → probabilidades coincide con `modelo.Coral`.
- Una prueba local del paso «`.chispa` score» de `barrido.sh` con pesos aleatorios y el fixture de JevBench, que escriba las
  claves `scoreK`.
- `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/calibrar.py` y `model/l2/tests/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 30 min de reloj · ≤ 2 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 5 líneas:
- rama y sha;
- el arreglo;
- los tests.
