# T4.1 (adelantado) Servidor de Chispa: `POST /v1/decide` y cascada por capas

Plan aprobado, fase 4, T4.1. Se adelanta porque no depende del modelo entrenado. Juan lo pidió el
2026-10-27. Esquema de preguntas: `model/esquema.md` (choice, score, noul).

## Hipótesis
- El servidor se define ya por completo con interfaces fijas: L0 real (el Chispa lineal de
  `github.com/juan52878911/kindling/pkg/chispa` v0.17.0, el mismo que usa `arena/`) y L1, L2 y L3
  como stubs. Cuando lleguen los modelos solo se sustituyen los stubs.
- Se refuta si L0 no se puede cargar desde un `.chispa` o si la cascada no se puede probar sin modelos.

## Terminado cuando
- Módulo Go en `server/` (go.mod propio, `go 1.27`, `require github.com/juan52878911/kindling v0.17.0`;
  sin red: `GOFLAGS=-mod=mod GOPROXY=off`, el módulo ya está en la caché del dorado).
- `POST /v1/decide`, compatible con `/v1/systemone` de Jev:
  - entrada: `state` (texto) y `questions`, una lista de `{id, question, kind: choice|score|noul, options: [{id, description}], nonce?}`;
  - salida por pregunta: `{id, kind, answer, probs, layer, escalate: bool, ms}`;
  - escribe en `server/README.md` el contrato exacto, con ejemplos, y en qué se parece y en qué no a
    `/v1/systemone`. Si no tienes la especificación de Jev, documenta tu suposición y márcala.
  - `nonce` se devuelve tal cual y sirve de clave de idempotencia en la caché de respuestas.
- `type Decisor interface { Decidir(ctx, Pregunta) (Respuesta, error); Nombre() string }`, una por
  capa. La cascada pasa de L0 a L1, L2 y L3 mientras la confianza top-1 sea < τ de la capa (umbrales
  en un YAML o JSON de configuración). La última capa escala (`escalate: true`) por debajo de su τ.
- L0: carga uno o varios `.chispa` (uno por esquema o tarea) con la API de `pkg/chispa`. Entrena uno
  de prueba con la Arena (`make dataset` y el entrenador que use `arena/internal/detectors/train.go`)
  para los tests.
- L1, L2 y L3: stubs que devuelven «sin opinión» (confianza 0) y cumplen la interfaz.
- Caché de esquemas: hash estable de `question + options` → torres u opciones precompiladas (para L0,
  el modelo cargado). LRU con tamaño configurable.
- `/healthz`, `/metrics` (Prometheus: peticiones, latencia por capa, escalados y aciertos de caché).
  Usa `prometheus/client_golang` solo si ya está en la caché de módulos; si no, escribe el formato de
  texto a mano.
- Tests:
  - JSON de contrato con golden files;
  - la cascada con decisores falsos (umbral, escalado, orden);
  - la caché;
  - el nonce;
  - errores 400 con mensaje claro.
- Benchmark con L0: `go test -bench` y un generador de carga sencillo (`server/cmd/carga`) contra el
  servidor en la microVM. Mide decisiones/s y p50/p99 con 1 y con 4 núcleos y apúntalo en el README.
  Es la cota del i3; el objetivo del plan es ≥ 5 k/s con L1 en el i7.
- `cd server && go vet ./... && go test -race ./...` en verde. `make test` y `make smoke` en la raíz
  siguen en verde. No toques el Makefile raíz: si quieres un objetivo nuevo, ponlo en `server/Makefile`.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `server/`. **No tocar**: `arena/`, que solo se lee, ni `model/`, `contracts/` o el Makefile raíz.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, `GOTOOLCHAIN=local`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 150 min de reloj · ≤ 8 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, decisiones/s y p99 medidos,
suposiciones sobre el contrato de Jev, qué quedó sin verificar y qué recomiendas.
