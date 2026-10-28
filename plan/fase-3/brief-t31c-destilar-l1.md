# T3.1c L1 propio: destilar un embedding estático y su cabeza por tarea (preparación offline)

Fase 3, T3.1 propiamente dicha. El runtime de L1 (`runtime/l1/`, Model2Vec en Go puro, int8, determinista) ya existe y usa
potion-multilingual-128M. Ahora toca un L1 propio. Juan eligió (c) para L2 el 2026-10-28: L2 queda de respaldo y la
cascada L0 → L1 → L2 es lo que se juzga. Por eso L1 importa como filtro barato antes de L2 (166 µs frente a 30,6 ms en el i7).

## Hipótesis
- H1: destilar Model2Vec desde e5-small (el codificador de L2) da un embedding estático de ≤ 30 MB, con vocabulario podado
  a ≤ 55 k como `model/bench/vocab-podado-e5-small.json`. En L1-zs (coseno contra «pregunta · opción · descripción») y
  en L1-proto (prototipos de train por clase) iguala o supera a potion en macro-F1 medio sobre las 5 tareas de T2.2, y
  pesa 5× menos.
- H2: una cabeza por tarea (prototipos más una capa lineal int8) entrenada con las distribuciones del mejor maestro por
  tarea (L0 o L2 con soporte, según `model/l2/resultados/ronda3-t22/delta.md`) mejora a L1-proto en ≥ 3 tareas.
- Se refuta midiendo.

## Terminado cuando
- `model/l1/` (paquete Python con tests):
  - `destilar.py`: Model2Vec `distill` desde `~/hf/intfloat/multilingual-e5-small`, con el vocabulario podado, y PCA a
    256 dimensiones; prueba también 128.
    - Si el paquete `model2vec` no está en `~/venv`, implementa la destilación mínima (el vector de cada token del
      vocabulario pasado por el codificador como frase de un token, más PCA y ponderación Zipf/SIF) y documenta la
      diferencia.
    - Exporta al formato que lee `runtime/l1`. Sigue su exportador; no cambies el formato.
  - `cabeza.py`: prototipos por clase más una capa lineal pequeña, entrenada con KL frente a las distribuciones del
    maestro.
    - Las distribuciones de L0 salen fuera de pliegue (k = 5), con el código de `model/lineas_base/correr.py`.
    - Las de L2 no se pueden calcular aquí, porque no hay GPU ni S3: deja la interfaz `--maestro <jsonl {id, probs}>` y
      prueba con L0 como maestro.
  - `evaluar.py`: por tarea, el macro-F1 de potion-zs, potion-proto, propio-zs, propio-proto y propio-cabeza; el tamaño en
    disco; el p99 en este host con `runtime/l1` (por `go test -bench` o un binario pequeño), a 16, 64 y 256 tokens; y el
    coseno medio frente al codificador maestro en las 2.274 frases del sondeo.
- Corrida real aquí, sobre los datos del golden y sin L2: informe en `model/l1/resultados/<fecha>/informe.md`.
- Determinismo: el L1 propio exportado pasa el test dorado de `runtime/l1` en amd64. Hazlo con un test nuevo **dentro de
  `model/l1/`**, sin tocar el de `runtime/l1`.
- `python -m unittest discover -s model -t .`, `cd runtime/l1 && go test ./...`, `make test` y `make smoke` en verde.
- Los modelos generados no van a git si pasan de 5 MB: se regeneran con un comando del README.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/l1/**`. `runtime/l1/` es de lectura: si su exportador no te vale, dilo en el informe y no lo cambies.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf`, Go en `~/go-sdk/bin` y datasets en `~/datos`. Sin GPU.
- Sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto. Las PQRS no entran.

## Tope
- ≤ 150 min de reloj · ≤ 7 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas:
- rama y sha;
- la tabla por tarea;
- el tamaño;
- el p99;
- qué falta para usar a L2 como maestro (lo correrá el orquestador en AWS);
- qué recomiendas.
