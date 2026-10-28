# T2.5 Formato `.chispa` v3 y su cargador en Go con fuzzing

Encargo: `plan/fase-2/encargo.md`, con el criterio de T2.5 congelado. Antecedentes:
- `.chispa` v1/v2 está en `github.com/juan52878911/kindling/pkg/chispa` v0.17.0, en la caché del dorado
  y en uso en `arena/` y `server/`;
- `.chispa-l1` (L1, Model2Vec int8) está en `runtime/l1/README.md`, que ya explica cómo encajaría como sección.

## Hipótesis
- Un contenedor por secciones resuelve L0, L1, L2 y los esquemas compilados en un único fichero, sin
  romper el v1/v2: cabecera con versión, más una tabla de secciones (tipo, offset relativo, longitud,
  sha256), más las secciones.
- El cargador valida todo antes de usar nada. Se refuta si el fuzzing encuentra un pánico o una
  lectura fuera de rango en 10 min.

## Terminado cuando
- `format/chispa3/`, un módulo Go propio (go 1.27; solo biblioteca estándar, y kindling v0.17.0 si hace
  falta leer v1/v2), con el formato documentado en su `README.md`.
- Secciones:
  - `META`: JSON con versión, tareas, licencias de los datos y hash del dorado;
  - `L0`: el `.chispa` v1/v2 tal cual, como blob;
  - `L1`: el cuerpo `.chispa-l1` de `runtime/l1`, con offsets relativos;
  - `L2`: el ONNX int8, como blob;
  - `ESQUEMAS`: la caché de torres de opción, con hash de pregunta y opciones → vector int8 + escala;
  - `CALIB`: T, a, b y θ por tipo de pregunta, y τ de escalate.
- `Abrir(ruta) (*Fichero, error)` con mmap y `Escribir(w, secciones)`. Validaciones:
  - magic y versión;
  - una tabla de secciones sin solapes, dentro del fichero, sin desbordes de enteros;
  - sha256 por sección, perezoso pero obligatorio antes de entregar los bytes;
  - tamaños máximos configurables.
- Un lector de v1/v2 que lo envuelve en un `Fichero` con solo la sección L0, para compatibilidad.
- Tests:
  - ida y vuelta;
  - cada error de validación;
  - compatibilidad con un `.chispa` v1 real (entrena uno con la Arena como hizo `server/`, o usa
    `server/testdata`).
- `FuzzAbrir` con un corpus semilla. `go test -fuzz=FuzzAbrir -fuzztime=10m` sin fallos: el log va en el README.
- `cd format/chispa3 && go vet ./... && go test -race ./...` en verde. `make test` y `make smoke` en la
  raíz siguen en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `format/chispa3/`. **No tocar** `server/`, `runtime/` ni `arena/` (solo leer) ni el Makefile raíz.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, `GOTOOLCHAIN=local`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, la rama y el sha, el resultado del fuzzing (en
ejecuciones y en tiempo), qué quedó sin verificar y qué recomiendas.
