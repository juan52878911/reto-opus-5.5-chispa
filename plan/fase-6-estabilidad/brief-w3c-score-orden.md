# W3c Orden de los niveles de score (R16) y recuento de filas afectadas

## Antecedentes
- **La revisión R16 encontró que `model/l2/modelo.py` indexa CORAL por la posición declarada de las opciones de score.**
  - Un Likert declarado `["5","4","3","2","1"]` se entrena invertido.
  - Ids `0..4` o `"01"` se entrenan, pero el runtime Go no opina sobre ellos, porque exige `1..K`.
  - Puede ser parte de la explicación de que score sea el tipo más débil: 0,333 en JevBench.
- **Ya hay un precedente con noul:** R9b hizo lo mismo con su orden (`texto_consulta` usa `true` y `max(opciones, key=int)`),
  y `model/l2/contar_orden_noul.py` contó las filas afectadas. Léelos.
- El ajuste fino de G.8 (`model/l2/aws/ajuste.sh`) espera este arreglo.

## Terminado cuando
1. **Helper `niveles_score(opciones)`**, en `model/l2/modelo.py`.
   - Devuelve los ids ordenados por `int`.
   - Lanza un `ValueError` claro si no son exactamente `"1".."K"` contiguos: ceros a la izquierda como `"01"`, `"0"`,
     huecos, no enteros.
2. **Aplicarlo en todo sitio que indexe CORAL o asocie una probabilidad a un nivel**, y ordenar antes de indexar:
   - entrenamiento (cargador de episodios y pérdida);
   - `calibrar.py`;
   - evaluación: `jevbench_l2`, `robustez.py`, `espanol.py` y `diag_score.py`;
   - exportador.

   Las probabilidades se devuelven por id, de modo que una lista declarada al revés da el mismo dict.
3. **En los cargadores de datos** (`model.datos` y el meta), las filas score con ids fuera de `1..K` se descartan con un aviso
   y un contador. No se corrigen en silencio. El orden no ascendente se acepta, porque el helper lo ordena.
4. **Tests:**
   - `[5,4,3,2,1]` da la misma etiqueta y las mismas probabilidades por id que `[1,2,3,4,5]`;
   - `[3,1,2]`;
   - `0..4` y `"01"` dan error;
   - el cargador descarta y cuenta;
   - el exportador escribe CALIB `scoreK` con el orden bueno.
5. **`model/l2/contar_orden_score.py`**, con el patrón de `contar_orden_noul.py`.
   - Cuenta, por fuente, tarea, split y K, las filas score con orden no ascendente y las que tienen ids fuera de `1..K`.
   - Fuentes: el meta, los conversores de `model.datos` (incluido dev) y JevBench.
   - Escribe JSON y una tabla Markdown.
   - Pruébalo aquí con fixtures y con `~/datos`.
6. **Añade a `model/l2/aws/ajuste.sh` un paso, antes de entrenar,** que corra el recuento sobre el meta y los datos
   convertidos y lo deje en `estado.tsv` y en los resultados.
7. **Prueba en seco** de `ajuste.sh` (`CHISPA_LOCAL=1`), sin `FALLO`.
8. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio. Si
   `make smoke` falla por un puerto ocupado, repítelo una vez y anótalo.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/l2/**` (salvo `resultados/`), `model/datos/**` y `model/meta/**`.
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, modelos en `~/hf` y datos en `~/datos`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 75 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- en qué sitios se aplica el orden;
- tests;
- el recuento local (fixtures y `~/datos`);
- la tabla de `estado.tsv` de la prueba en seco.
