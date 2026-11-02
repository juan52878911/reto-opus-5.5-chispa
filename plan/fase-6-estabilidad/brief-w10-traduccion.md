# W10 Traducción al español de las tareas comerciales de tasksource-jev-typed-decisions (script de AWS)

## Antecedentes
- Juan aprobó traducir al español las tareas con `license_use == "commercial"` de `tasksource-jev-typed-decisions` (el
  meta «tsjev»: `model/meta/tasksource_jev.py`, `model/meta/convertir.py`; el meta convertido está en
  `s3://chispa-pruebas-879381269751/meta-20261027/meta/tsjev/`, con descarga por fichero porque el rol no tiene
  `ListBucket`; mira cómo baja las claves `model/l2/aws/general.sh`).
- **Objetivo:** reducir la brecha español/inglés de L2, hoy −2,6 puntos con el modelo v2
  (`model/l2/resultados/ajuste-v2-20261102/`).
- **Traductor:** abierto y con licencia comercial.
  - **Opus-MT** `Helsinki-NLP/opus-mt-en-es`: comprueba la licencia del par en su tarjeta; se espera CC-BY-4.0, con
    atribución.
  - **MADLAD-400** (`google/madlad400-3b-mt`, Apache-2.0) si Opus-MT no valiera.
  - **NLLB no**: es no comercial.
  - Elige por licencia y coste. Opus-MT es pequeño y cabe en CPU o en una GPU modesta.

## Terminado cuando
1. **`model/meta/traducir.py`** (nuevo): lee las filas commercial de tsjev y traduce al español `texto`, `pregunta` y
   `descripciones`. Los ids de opción **no** se traducen, para que la etiqueta no cambie.
   - Cada fila traducida es nueva y lleva:
     - `idioma: "es"`;
     - `traducida: {"modelo": "<id de HF>", "revision": "<sha del snapshot>", "de": "en"}`;
     - el id original con un sufijo `:es`;
     - la misma `plantilla` que la original, para que caiga en el mismo split y no haya fugas;
     - la licencia original más la del traductor en `licencia`.
   - Los splits se respetan: el test de tsjev **no** se usa para entrenar.
   - Va por lotes, deduplica textos repetidos antes de traducir, y tiene un tope de filas por tarea (`--max-por-tarea`, por
     defecto 300) y otro total (`--max-filas`).
2. **Muestra de revisión:** escribe 50 pares original → traducción al azar, con semilla fija, en `muestra-revision.md`,
   para que el orquestador los revise a mano. Incluye heurísticas automáticas de basura:
   - traducción vacía;
   - idéntica al original;
   - longitud fuera de [0,3, 3] veces;
   - repeticiones de n-gramas.

   Descarta y cuenta las filas que las disparen.
3. **`model/meta/aws/traducir.sh`** (nuevo): el user-data con el patrón de `model/l2/aws/general.sh`.
   - Instancia: **c6a.2xlarge en CPU con Opus-MT, o g5.xlarge si hace falta MADLAD**. Elige la más barata que termine
     en ≤ 90 min.
   - Lleva `__CHISPA_S3__`, `shutdown -h +100` y el coste declarado en la cabecera. **Tope: 2 USD.**
   - Baja las claves de tsjev, traduce y sube a `$CHISPA_S3/tsjev-es/` los `.jsonl.gz` con las filas traducidas, en el
     mismo formato que el meta, más `muestra-revision.md`, `resumen.json` (filas por tarea, descartadas y tiempo) y
     `estado.tsv`.
   - Opcionales: `CHISPA_META_S3` y `CHISPA_MAX_FILAS`.
4. **Prueba en seco** (`CHISPA_LOCAL=1`) con un tsjev de fixture y un traductor pequeño: Opus-MT desde `~/hf` si está; si
   no, un traductor falso de identidad, marcado. Tests:
   - los ids de opción no se traducen;
   - la etiqueta se conserva;
   - la plantilla y el split se conservan;
   - las heurísticas descartan;
   - es determinista.
5. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/meta/**` y `model/datos/LICENCIAS.md`. No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` y modelos en `~/hf`. Sin red salvo la API de Claude.

## Tope
- ≤ 75 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- traductor elegido, licencia comprobada, instancia y coste estimado;
- la tabla de `estado.tsv` de la prueba en seco;
- cómo se lanza.
