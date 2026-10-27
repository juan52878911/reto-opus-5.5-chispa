# T1.6 Etiquetas blandas del maestro (Qwen) en una g5.xlarge

Encargo: `plan/fase-1/encargo.md`; esquema `model/esquema.md` (campo `blanda`, congelado). Plan
aprobado: D4 = Qwen3.5-4B (Apache 2.0) es **la única** fuente de distribuciones para destilar; Haiku
nunca. Tú no lanzas nada en AWS. El orquestador lanza una g5.xlarge **on-demand** (la cuota de
spot de GPU es 0) con la AMI «Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.10 (Amazon Linux
2023)», con 24 GB de A10G, CUDA y PyTorch ya instalados, e internet.

## Hipótesis
- Puntuar cada opción por el logprob del primer token de su letra (A, B, C…), con un prompt que
  lista las opciones y sus descripciones, da una distribución útil. La medida: el top-1 del maestro
  coincide ≥ 85 % con las etiquetas de oro de los test públicos (MASSIVE, CLINC) y de T1.4. Se
  refuta midiendo en la instancia.

## Terminado cuando
- `model/maestro/blandas.py --entrada <jsonl…> --salida <dir> --modelo <id HF> [--lote N] [--max-filas N]`:
  - añade `blanda: {opcion: prob}` a cada fila;
  - con más de 26 opciones (CLINC: 151; herramientas), puntúa por bloques de ≤ 26 y combina:
    o bien softmax sobre los logprobs de los bloques, o bien dos pasadas con candidatos. Elige una,
    justifícala en el README y que la suma dé 1;
  - bf16 en CUDA y batching por longitud;
  - reanuda desde lo ya escrito;
  - escribe `resumen.json` con filas/s, acuerdo top-1 con `etiqueta` por tarea y split, ECE del maestro y horas de GPU.
- Modelo por defecto: `Qwen/Qwen3.5-4B-Instruct`, o el id exacto que exista (la instancia
  comprueba con `huggingface_hub` y cae a `Qwen/Qwen3-4B-Instruct-2507` si no existe; registra cuál usó).
- `model/maestro/aws/arranque.sh`: user-data con el mismo patrón que `model/bench/aws/arranque.sh`:
  - marcadores `CHISPA_S3=__CHISPA_S3__` y `MAX_FILAS=__MAX_FILAS__`;
  - el código llega como `$CHISPA_S3/codigo.tgz`;
  - `$CHISPA_S3/corpus.tgz` es opcional: si no llega en 10 min, sigue sin él;
  - trap que sube `blandas.tgz` y `log.txt`;
  - `shutdown -h +200` al empezar.
  En la instancia:
  1. usa el Python de la AMI (`/opt/pytorch` o el que traiga; compruébalo con `ls` y regístralo);
  2. `pip install` transformers, accelerate y huggingface_hub;
  3. baja los datasets públicos como hace `.delega/golden.sh`;
  4. corre `python -m model.datos.convertir`;
  5. puntúa train, dev y test de todo lo convertido, más T1.4, más el corpus si llegó, hasta `MAX_FILAS`.
  Las filas con `uso_comercial: false` se puntúan solo para medir, y van marcadas.
- `model/maestro/aws/empaquetar.sh`, como los otros.
- Prueba en seco aquí, en CPU:
  - `CHISPA_LOCAL=1` y un Qwen diminuto con pesos aleatorios, construido desde la configuración
    (`AutoConfig` → `AutoModelForCausalLM.from_config`, 2 capas), con el tokenizador de cualquier
    modelo que esté en `~/hf`;
  - punta a punta sobre 50 filas: las probs suman 1, el bloqueo por > 26 opciones funciona y el
    resumen se escribe.
  - Tests con `unittest` en `model/maestro/tests/`.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/maestro/`. **No tocar**: `model/esquema.md`, `model/datos/` (solo usar), otras carpetas.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas:
- qué cambiaste, rama y sha;
- la cola del log de la prueba en seco;
- tu estimación de filas/s y de horas de GPU para unas 60 k filas en una A10G;
- qué quedó sin verificar y qué recomiendas.
