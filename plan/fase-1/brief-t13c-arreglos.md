# T1.3c Respaldo de vLLM a transformers y PQRS solo en test

Encargo: `plan/fase-1/encargo.md`. Son dos arreglos pequeños en zonas distintas.

## Hipótesis
- `model/corpus/aws/arranque-gpu.sh` y `backends.Local` solo caen a transformers si vLLM no se
  instala. Si vLLM se instala pero falla al arrancar (sin memoria de GPU con el 9B, o flashinfer sin
  `nvcc` en la AMI), la ejecución entera falla.
- Se refuta con un test que simule un `LLM(...)` que lanza `RuntimeError` y compruebe que se
  sigue con transformers.

## Terminado cuando
1. Corpus (`model/corpus/`):
   - `backends.Local` envuelve la creación del motor vLLM. Ante cualquier excepción, la registra en
     el log, libera la GPU (`del`, `gc.collect()`, `torch.cuda.empty_cache()`) y sigue con transformers.
   - Elección del modelo por defecto según la memoria de la GPU: con < 30 GB, como en una A10G de
     24 GB, el 4B; el 9B, solo si cabe en bf16 con margen.
   - Opción `CHISPA_MOTOR=transformers|vllm|auto` en el user-data, con `auto` por defecto.
   - Tests con `unittest` para el respaldo y para la elección del modelo según la memoria, ambos con falsos.
2. PQRS (`model/datos/`): por decisión de Juan, todas las fuentes de datos.gov.co (gb9w, e86p,
   xtj2, m3mt / `pqrs_enrutamiento`) llevan `uso_comercial: false` y van solo a `test`, igual que ALIA:
   - anótalo en `LICENCIAS.md` («solo test por decisión de Juan; conservan ~1 nombre visible por
     cada 300 filas; nunca salen de kindling ni del bucket»);
   - ajusta los tests que esperaban train y dev.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/corpus/**` y `model/datos/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 45 min de reloj · ≤ 2 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas: qué cambiaste, rama y sha, los tests, y qué recomiendas.
