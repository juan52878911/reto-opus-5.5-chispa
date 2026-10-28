# T4.1b Servidor: L1 real y carga de `.chispa` v3 en la cascada

Plan aprobado, fase 4. Directiva de Juan del 2026-10-28: adelantar todo lo que no esté bloqueado.

Antecedentes:
- `server/` (T4.1): L0 real, y L1, L2 y L3 como stubs;
- `runtime/l1/` (T3.1): L1 en Go puro, determinista;
- `format/chispa3/` (T2.5): el contenedor por secciones;
- `model/l2/` (T2.4+T2.6): ONNX int8 y el empaquetado.

## Hipótesis
- El servidor carga un `.chispa` v3 y monta la cascada desde sus secciones:
  - L0 desde la sección `L0`;
  - L1 desde la sección `L1` con `runtime/l1`, puntuando las opciones por coseno entre el embedding
    del mensaje y el de `pregunta · opción · descripción`, con la temperatura de `CALIB`;
  - L2 desde la sección `L2` vía ONNX Runtime, solo con la etiqueta de build `ort`, porque la VM no
    trae la biblioteca de ORT.
- Sin la etiqueta `ort`, L2 sigue siendo un stub y todo compila sin cgo.
- Se refuta si la cascada no pasa sus tests con un `.chispa` v3 real que tenga L0 y L1.

## Terminado cuando
- `server/` importa `format/chispa3` y `runtime/l1` con `replace` en `go.mod` (módulos locales), sin red.
- `decide/l1.go`: un `Decisor` sobre `runtime/l1`, con caché de embeddings de opciones por hash de
  esquema y τ desde `CALIB`.
- `decide/l2_ort.go` (`//go:build ort`): un `Decisor` sobre el ONNX de la sección `L2` y las torres de
  `ESQUEMAS`, con la puntuación MaxSim de `model/l2/README.md`. Sin la etiqueta, `decide/l2_stub.go`.
  Documenta en el README cómo compilar con ORT; compilar con `ort` lo prueba el orquestador en AWS.
- `cmd/chispa-server --modelo x.chispa`: lee v3, o v2 envuelto, y arma L0, L1 y L2 según las
  secciones presentes; las capas que falten quedan como stub.
- Tests:
  - un `.chispa` v3 construido en el test con L0 de `server/testdata` y un L1 pequeño (un vocabulario
    diminuto escrito con el formato de `runtime/l1`; no hace falta el potion de 155 MB);
  - la cascada L0 → L1 → escalate según los τ;
  - compatibilidad del JSON del contrato.
- Benchmark con L1 de verdad: si cabe, exporta el potion de `~/hf` a `/tmp`. Mide decisiones/s y p99
  con L1 en lotes de 16, en el README. Es la cota en el i3; el objetivo del plan es ≥ 5 k/s en el i7.
- `cd server && go vet ./... && go test -race ./...` en verde. `make test` y `make smoke` en la raíz.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `server/`. `runtime/l1/` y `format/chispa3/` solo se usan.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, `GOTOOLCHAIN=local`. Sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, las decisiones por segundo con L1,
qué quedó sin verificar y qué recomiendas.
