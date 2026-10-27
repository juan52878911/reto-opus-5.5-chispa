# T1.3b Corpus sintético con un modelo abierto (Qwen) en una g5.xlarge

Encargo: `plan/fase-1/encargo.md` (cambio del 2026-10-27: nada de Haiku para producir datos).
Sigue sobre `model/corpus/`, que ya tiene el generador, los backends `bedrock` y `simulado`, la
dedup, el reparto y el script de AWS.

## Hipótesis
- Un Qwen instruct abierto (Apache-2.0) de 7-9 B en bf16 cabe en la A10G de 24 GB y escribe español
  colombiano útil. Con vLLM o transformers por lotes se generan unos 12 k textos en ≤ 2 h.
- Se refuta si el verificador, el mismo modelo con otra instrucción, rechaza > 30 % o la dedup tira > 40 %.

## Terminado cuando
- Un backend `local` en `generar.py` (vLLM si se puede instalar con pip en la AMI Deep Learning
  PyTorch 2.10 AL2023; si no, transformers con `generate` por lotes).
  - Modelo con `--modelo`. Por defecto, el mayor de estos que exista en el Hub y quepa:
    `Qwen/Qwen3.5-9B-Instruct`, `Qwen/Qwen3.5-9B`, `Qwen/Qwen3-8B`, `Qwen/Qwen3.5-4B`.
  - La instancia verifica en la tarjeta que la licencia sea Apache-2.0 y registra cuál usó.
- Coste en horas de GPU en lugar de USD de tokens: `--tope-min` para la generación.
- La verificación de etiquetas va con el mismo backend local. Quita Haiku y Bedrock como opción por
  defecto: déjalo solo detrás de `--backend bedrock`, documentado como «solo evaluación».
- `fuente: "chispa T1.3 (<modelo>, local)"` y `licencia` = la del modelo más «propia (Chispa)».
- `model/corpus/aws/arranque-gpu.sh`, para la g5.xlarge con la AMI Deep Learning PyTorch 2.10 AL2023:
  - el mismo patrón que `model/maestro/aws/arranque.sh`: marcadores `CHISPA_S3`, `POR_CLASE` y
    `TOPE_MIN`, `shutdown -h +170` y un trap que sube `corpus.tgz` y `log.txt`;
  - usa el Python de la AMI y baja e5-small para la dedup.
- Prueba en seco aquí con `--backend simulado` y `CHISPA_LOCAL=1`, más un test del backend local con
  un modelo diminuto de pesos aleatorios (como en `model/maestro/tests/`) para el formato de los
  prompts y el parseo.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/corpus/`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` y modelos en `~/hf`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, la cola del log de la prueba en
seco, la estimación de horas de GPU para 2 k útiles por tarea, qué quedó sin verificar y qué
recomiendas.
