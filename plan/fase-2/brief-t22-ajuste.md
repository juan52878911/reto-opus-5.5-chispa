# T2.2 Ajuste contrastivo del codificador, robustez al renombrado y destilación

Encargo: `plan/fase-2/encargo.md`, con el criterio de T2.2 congelado. Parte de `model/l2/` (T2.1), que
ya entrena con e5 congelado en una g5. Tú escribes y pruebas en CPU; el orquestador lanza la g5.

## Hipótesis
- Descongelar las últimas 4 capas de e5 con un lr bajo, más aumentos de renombrado de opciones,
  mejora la macro-F1 y hace que la caída al renombrar las opciones a A/B/C quede ≤ 5 puntos.
- Renombrar significa sustituir el id de la opción por «A», «B», «C»… manteniendo la descripción.
- Se refuta midiendo en test con y sin renombrado.

## Terminado cuando
- `model/l2/` admite estas opciones, que con sus valores por defecto dejan T2.1 igual:
  - `--descongelar N`: las últimas N capas de e5 se entrenan, con lr 2e-5 y grad-clip 1,0. La
    torre de opción comparte el codificador: con N > 0 la caché de opciones se invalida en cada
    paso de optimización; documenta el coste.
  - `--renombrar p`: con probabilidad p por fila, los ids de las opciones pasan a letras en el texto
    de la torre y la etiqueta se remapea. Que sea idempotente y tenga test.
  - `--maestro-extra <dir>`: blandas adicionales de un segundo maestro, en el formato
    `{id, blanda}` en JSONL. Se promedian con las existentes con el peso `--peso-extra`.
- `evaluar.py --renombrar`: evalúa el mismo test con las opciones renombradas y da la caída por tarea.
- `model/l2/aws/arranque.sh` acepta estas opciones mediante una variable `L2_ARGS`, con el marcador
  `__L2_ARGS__`, y una `CKPT_INICIAL`, con el marcador `__CKPT_INICIAL__`, para arrancar de un checkpoint de T2.1 en S3.
  - **Las descargas de S3 deben ser por fichero, sin `--recursive` ni `sync`**: el rol no puede listar el bucket;
  - la lista de ficheros de metaentrenamiento está en `model/meta/resultados/conversion-20261027.json`
    (clave `ficheros`);
  - lo mismo para subir checkpoints: `aws s3 cp` por fichero.
- Prueba en seco en CPU, con `CHISPA_LOCAL=1` y 2 k filas: `--descongelar 2 --renombrar 0.5`, 50
  pasos, con la pérdida y la caída por renombrado. Tests con `unittest` para el renombrado, la
  invalidación de la caché y la mezcla de maestros.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/l2/`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.
- Ni datos ni pesos a git.

## Entorno
- `source ~/.profile`. Python en `~/venv` y modelos en `~/hf`. Sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, la cola de la prueba en seco, la
estimación de horas de g5 para 1 época con `--descongelar 4`, qué quedó sin verificar y qué recomiendas.
