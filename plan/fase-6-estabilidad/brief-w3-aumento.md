# W3 Aumento de datos para robustez y español (prepara el ajuste fino de G.8), y arreglo de M5

## Antecedentes
- Resultados de la tanda en `model/l2/resultados/estabilidad-20261029/LEEME.md`. Léelo entero.
- **L2 (G.8) no es robusto.** Cambian más del 5 % de las decisiones con estas variantes:

  | variante | decisiones que cambian |
  |---|---|
  | renombrar ids | 37,6 % |
  | mayúsculas | 33,4 % |
  | frases añadidas («largo») | 61,3 % |
  | pregunta en inglés | 16,6 % |
  | esquema en inglés | 15,0 % |
  | erratas | 12,8 % |
  | paráfrasis | 9,5 % |
  | mezcla | 6,7 % |

- **Español frente a inglés:** −3,5 puntos.
- **Generador de variantes:** `sdk/python/chispa/variantes.py` (E2). La medida está en `model/l2/robustez.py` y
  `model/l2/espanol.py`, y su plan en `model/l2/resultados/estabilidad-20261029/m4/plan.md`.
- **Entrenamiento:** `model/l2/entrenar.py`; en AWS, `model/l2/aws/general.sh`, el que produjo G.8 en
  `s3://chispa-pruebas-879381269751/general-20261029b/ckpt/mejor.pt`.
- **M5 falló** en la corrida porque `model/l2/aws/empaquetar_estabilidad.sh` no incluye
  `model/meta/resultados/conversion-20261027.json`, que usa `model/l2/diag_score.py`.

## Terminado cuando
1. **Arreglo de M5:** el empaquetador incluye ese JSON. Si `diag_score.py` lo lee de otra ruta, alinéalo. Prueba en seco de
   M5.
2. **Aumento de datos en el entrenamiento de L2**, con una opción `--aumento` (desactivado por defecto) en
   `model/l2/entrenar.py` o en su cargador de episodios. Es determinista con semilla, y cada fracción se puede cambiar:
   - ids de opción opacos (p. ej. `op_3f2a`), manteniendo la descripción, en ≈ 30 % de los episodios. La etiqueta se mapea;
   - mayúsculas y minúsculas en el texto, ≈ 15 %;
   - 1–3 erratas por texto, ≈ 20 %;
   - paráfrasis de la pregunta con plantillas, ≈ 30 %;
   - pregunta y descripciones en inglés cuando la fila las tenga, o con plantillas, ≈ 20 %;
   - 2–4 frases de relleno neutras antes o después del texto, ≈ 15 %, sin pasar de `max_tok`.

   **Reutiliza las transformaciones de `sdk/python/chispa/variantes.py`** con un adaptador. No las dupliques. Si hace falta
   algo que no tiene, añádelo en `model/` y explica por qué.

   **Las variantes de evaluación no pueden salir de la misma semilla ni de la misma lista de plantillas que las de
   entrenamiento.** Separa las listas: unas para entrenar y otras para medir, o lo que mida M3 estará contaminado.
3. **Ajuste fino desde un checkpoint:** que `entrenar.py` pueda partir de un `mejor.pt` (`--desde CKPT`), con pocos pasos y
   un LR bajo, además del entrenamiento desde cero.
4. **Más español de licencia comercial:** conversores en `model/datos/` para SIB-200 y PAWS-X, si sus licencias lo
   permiten. Compruébalo en la tarjeta de HF y escríbelo en `licencia` y `uso_comercial`. Añade lo que ya existe en
   `model.datos` (`odio_alia`, `toxicidad_*`). Las tareas de M4 (massive es, xnli, sib200 y paws-x **test**) no entran en
   train.
5. **`model/l2/aws/ajuste.sh`**, el user-data de una **g5.xlarge bajo demanda**, con el patrón de `general.sh`:
   - baja G.8 y los datos;
   - hace el ajuste fino con `--aumento` y el español extra (≈ 1 h);
   - mide en el mismo script JevBench k=0 (`model/evaluacion/jevbench_l2.py`), M3 (`robustez.py`) y M4 (`espanol.py`) con
     el checkpoint nuevo **y** con G.8, para tener la comparación en la misma máquina;
   - sube `ckpt/mejor.pt`, los resultados y `estado.tsv`;
   - lleva `shutdown -h +120` y `__CHISPA_S3__`;
   - coste declarado en la cabecera: ≈ 1,5 USD.
6. **Prueba en seco** (`CHISPA_LOCAL=1`) de `ajuste.sh` con el checkpoint aleatorio, pocos pasos y fixtures, sin `FALLO`.
   Tests:
   - el aumento es determinista;
   - la etiqueta sigue siendo correcta tras renombrar;
   - el relleno respeta `max_tok`;
   - las plantillas de entrenamiento y de evaluación no se solapan.
7. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio. Si
   `make smoke` falla por un puerto ocupado, repítelo una vez y anótalo.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/l2/**` (salvo `resultados/`), `model/datos/**` y `model/l2/tests/**`.
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, modelos en `~/hf` y datos en `~/datos`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 120 min de reloj · ≤ 8 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- qué hace el aumento y con qué fracciones;
- las fuentes en español añadidas y sus licencias;
- la tabla de `estado.tsv` de la prueba en seco;
- el coste y tiempo estimados de `ajuste.sh`.
