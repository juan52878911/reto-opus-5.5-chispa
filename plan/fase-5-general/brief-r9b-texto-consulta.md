# R9b `texto_consulta` de noul con la torre de `true`, y recuento de filas `[true, false]`

## Antecedentes
R9 (`2e7cb86`) dejó dos piezas usando la torre de `true` en las preguntas noul:
- el exportador;
- el runtime.

`model/l2/modelo.py` (`texto_consulta`, que usan entrenamiento, evaluación y `calibrar.py`) sigue con `opciones[-1]`. En
una fila noul `[true, false]`, el entrenamiento y el modelo exportado usarían torres distintas.

## Terminado cuando
- **Código.**
  - `texto_consulta` usa, en noul, la opción `true`. Si no hay `true`, falla con un error claro.
  - En score usa el nivel máximo (`max(opciones, key=int)`), el mismo criterio que el exportador desde R9.
- **Tests.**
  - Con filas `[false, true]` el texto y el resultado son idénticos a los de antes (un test lo compara con la
    implementación anterior).
  - Con `[true, false]` el texto es el de `true`.
  - Score con niveles desordenados.
- **`model/l2/contar_orden_noul.py`.** Cuenta las filas noul con `opciones == ["true", "false"]` o con `true` en una
  posición distinta de la última, por fuente, tarea y split. Las fuentes son:
  - el meta: `tsjev`, `tsinst` y el resto de `meta/<fuente>/*.jsonl.gz`;
  - los conversores de `model.datos`, incluido dev;
  - JevBench (`model/evaluacion/jevbench.py`).
  - Escribe JSON y una tabla Markdown.
  - Pruébalo aquí con fixtures y con lo que haya en `~/datos`.
- **`model/l2/aws/contar_noul.sh`.** User-data de una c6a.xlarge spot, con el patrón de `model/l2/aws/barrido.sh`:
  - marcador `__CHISPA_S3__` y `shutdown -h +45`;
  - descargas por fichero del meta de `s3://chispa-pruebas-879381269751/meta-20261027/meta/` (las mismas claves que usa
    `general.sh`) y de tsinst, si está en S3 (`general-20261029b/`) o se baja de HF;
  - clona JevBench;
  - corre el recuento y sube el resultado;
  - ≤ 16 KB.
- **Prueba en seco**, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/modelo.py`, `model/l2/contar_orden_noul.py`, `model/l2/aws/contar_noul.sh`, `model/l2/aws/empaquetar*.sh` y
  `model/l2/tests/**`.
- Rama: la que te da delega. Base: `integracion`. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf` y datos en `~/datos`. Sin red salvo la API de Claude.

## Tope
- ≤ 45 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- tests;
- recuento local;
- qué sustituyo para lanzar.
