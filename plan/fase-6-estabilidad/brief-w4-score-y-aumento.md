# W4 (a) Orientación de score y (b) ids opacos en la torre; preparar el segundo ajuste (c)

## Antecedentes
- Resultados en `model/l2/resultados/ajuste-20261029/comparacion.md`. Léelo entero.
- **(a) Score.** En JevBench, el ρ de Spearman entre s (MaxSim con la torre de score) y el nivel de oro sale **−0,52** de media
  por esquema (`model/l2/diag_score.py`, n = 18), con G.8 y con el ajustado. Reajustar los umbrales no recupera nada; el
  oráculo llega a 0,667 y el checkpoint se queda en 0,333.
  - La conversión de JevBench (`model/evaluacion/jevbench.py`) parece correcta: `criteria` va de menos a más gravedad y
    `expected` es el índice → nivel + 1. Compruébalo con todos los casos score.
  - La torre de score usa el nivel máximo (`max(opciones, key=int)`, R9b, y `niveles_score`, R16).
  - Una s más alta tendría que significar un nivel más alto.
- **(b) Ids opacos.** En el ajuste, renombrar ids sigue cambiando el 35,6 % de las decisiones de L2 (G.8, 37,6 %). Sospecha:
  `model/l2/aumento.py` / `--aumento` en `model/l2/entrenar.py` solo transforma la **consulta** del lote. Si la torre de la
  opción sigue llevando el id real, o la pérdida asocia la clase por id, el modelo no aprende a ignorarlo.

## Terminado cuando
1. **(a) `model/l2/orientacion_score.py`** (nuevo). Para cada esquema score, calcula el ρ de Spearman entre s y el nivel de oro
   y la exactitud de CORAL con:
   - la torre del nivel **máximo** (la actual);
   - la torre del nivel **mínimo**;
   - s invertida (−s).

   Hazlo sobre:
   - JevBench (todos los casos score);
   - **el dev de score del meta de G.8**: filas score con `split == "dev"` de los `meta/<fuente>/*.jsonl.gz`, hasta 3000
     filas, por K.

   Revisa también, línea a línea, que el signo con que la cabeza CORAL usa s en `modelo.py` (`P(y>j) = σ(w·s − θ_j)`) sea
   coherente con la torre usada en entrenamiento y en evaluación.

   Escribe un veredicto con una de estas tres conclusiones:
   - fallo de conversión de JevBench;
   - fallo de orientación en el modelo;
   - el modelo ordena bien en el meta y no generaliza a JevBench.

   **Si hay un fallo de código, arréglalo con un test**, en `model/`. Si estuviera en `model/evaluacion/jevbench.py`,
   arréglalo también.
2. **(b)** Lee `aumento.py`, `entrenar.py` y la pérdida. Comprueba con un test que, con `--aumento` e `ids=1.0`, **la torre de
   las opciones y la etiqueta usan el id opaco**, y que el modelo no ve el id original en ningún sitio de ese episodio. Si no
   es así, arréglalo para que el renombrado se aplique a la fila entera antes de construir torres y etiqueta.
3. **Paso nuevo en `model/l2/aws/estabilidad.sh`**, `orientacion_score`, que corre (a) sobre JevBench y el meta (las descargas
   del meta ya existen para M5).
4. **Ajustes de `model/l2/aws/ajuste.sh`** para el segundo ajuste:
   - **3 épocas** (`--epocas 3` o lo equivalente);
   - `shutdown -h +75`;
   - el coste declarado en la cabecera: ≈ 1 USD en una g5.xlarge;
   - **instala Go** (`go${GO_VERSION}.linux-amd64.tar.gz`, como en `model/bench/torre/e2e.sh`), para que M3 (L1) corra en la
     misma máquina;
   - si (a) encuentra un fallo de código, el ajuste lo lleva.
5. **Prueba en seco** de `estabilidad.sh` y de `ajuste.sh` (`CHISPA_LOCAL=1`), sin `FALLO`.
6. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio. Si
   `make smoke` falla por un puerto ocupado, repítelo una vez y anótalo.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/l2/**` (salvo `resultados/`), `model/evaluacion/jevbench.py` y `model/evaluacion/tests/**`.
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, modelos en `~/hf` y datos en `~/datos`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 90 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- el veredicto de (a) en local (fixtures);
- qué encontraste en (b) y qué cambiaste;
- la tabla de `estado.tsv` de las dos pruebas en seco.
