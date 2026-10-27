# T1.8 Datos de metaentrenamiento: tasksource-jev (`commercial`), synthetic_zeroshot, PAWS-X es y SIB-200 es

Encargo: `plan/fase-1/encargo.md` (ver los cambios del 2026-10-27). Esquema: `model/esquema.md`, congelado.
El objetivo es que Chispa sea un clasificador de uso general, como Laya. Metaentrenar con cientos de
tareas tipadas.

## Hipótesis
- `tasksource/tasksource-jev-typed-decisions` ya trae `state`, `question`, `kind` (choice, score o
  noul), `options` y `target` con etiquetas blandas, más `license_use` por fila. Se lleva al esquema
  casi uno a uno. Se refuta si el fragmento del dorado no tiene esas columnas.

## Terminado cuando
- `model/meta/tasksource_jev.py`: convierte filas al esquema.
  - `texto` = `state`, `pregunta` = `question`, `tipo` = `kind`, `opciones` = `options`;
    `etiqueta` = argmax de `target`, y `blanda` = `target` normalizado si es una distribución.
  - **Filtro duro**: solo `license_use == "commercial"`. Las filas `non-commercial` y `unspecified`
    se descartan y se cuentan; no se escriben.
  - Guarda la tarea de origen en `fuente` y mapea la licencia de `sources.yaml` en `licencia`.
  - Sin `descripciones` de origen, usa el texto de la opción como descripción.
  - Trabaja con el fragmento que hay en `~/hf`.
- `model/meta/synthetic_zeroshot.py` para MoritzLaurer/synthetic_zeroshot_mixtral_v0.1 (apache-2.0).
  Usa las descripciones de etiqueta que traiga y marca `idioma: en`. La traducción al español va
  después, aparte: no la hagas.
- `model/meta/pawsx_es.py`: PAWS-X `es`, noul («¿son paráfrasis?»), con las dos frases en `texto`
  separadas por un marcador documentado.
- `model/meta/sib200_es.py`: SIB-200 `spa_Latn`, tema, choice de 7 clases.
- **Trampas que el código debe impedir**, cada una con un test que falle si se cuela:
  - nada de GLiClass, XNLI ni ANLI, ni derivados;
  - en tasksource, ninguna fila que no sea `commercial`.
- `model/meta/aws/arranque.sh` y `empaquetar.sh`, con el mismo patrón que `model/bench/aws/`
  (marcador `CHISPA_S3=__CHISPA_S3__`, `shutdown -h +170`, trap que sube `log.txt`). En una c6a.xlarge:
  1. baja tasksource-jev **completo** (`default`; `full` solo si cabe en 60 GB y tarda < 1 h);
  2. corre los cuatro conversores;
  3. escribe JSONL partidos en trozos de ~100 MB y comprimidos;
  4. sube `$CHISPA_S3/meta/…` más un `resumen.json`: filas por fuente, tipo y split, descartadas
     por licencia, y tareas distintas.
  La instancia sube varios ficheros: usa `aws s3 cp --recursive`.
- Prueba en seco aquí con `CHISPA_LOCAL=1` sobre el fragmento. Pega la cola del log y el resumen.
- Tests con `unittest` y fixtures inventados. `python -m unittest discover -s model -t .`,
  `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/meta/`. **No tocar**: `model/esquema.md` ni otras carpetas.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge. Los datos convertidos
  van a `/tmp` y nunca a git.

## Entorno
- `source ~/.profile`. Python en `~/venv`, datos en `~/hf`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 150 min de reloj · ≤ 8 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, las columnas reales del fragmento
de tasksource, filas por tipo y licencia en el fragmento, la cola del log, qué no se pudo y qué
recomiendas.
