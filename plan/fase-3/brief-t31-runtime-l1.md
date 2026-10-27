# T3.1 (adelantado) Runtime L1: Model2Vec en Go puro, int8 y determinista

Pertenece a la fase 3, T3.1. La parte de runtime se adelanta: no depende del L1 propio, que se
destilará después. Juan lo pidió el 2026-10-27.

## Hipótesis
- Un Model2Vec (potion) es un embedding estático: se tokeniza, se buscan los vectores, se hace la
  media y se normaliza. En Go puro con pesos int8 y una escala por fila, con acumulación entera y una
  sola división final en float64, da el mismo resultado en amd64 y arm64 bit a bit, y un coseno
  ≥ 0,999 frente a la referencia en Python.
- Se refuta si el tokenizador no se puede reproducir exacto en Go.

## Terminado cuando
- Módulo Go en `runtime/l1/` (go.mod propio, `go 1.27`, solo biblioteca estándar).
- Modelo de referencia: `minishlab/potion-multilingual-128M`, que está en `~/hf`. Lee su licencia en
  la tarjeta y anótala en `runtime/l1/README.md`. Si no fuera abierta, usa otro potion de `~/hf` y dilo.
- Exportador en Python, `runtime/l1/exportar.py`, que lleva el modelo a un formato binario propio
  `.chispa-l1` y lo documenta en el README:
  - cabecera con versión, dimensión, vocabulario y hash;
  - tabla de vocabulario;
  - pesos int8 por fila con su escala float32;
  - parámetros del tokenizador.
  Debe poder ser una sección dentro del `.chispa` v3 más adelante: deja escrito cómo encajaría.
- Tokenizador en Go idéntico al de potion (WordPiece o el que use; mira su `tokenizer.json`), con un
  test sobre ≥ 2.000 frases (las de `model/sondeo/*.jsonl`) cuyos ids coincidan con los de
  `tokenizers` en Python.
- Paridad:
  - coseno entre el embedding Go int8 y el de Python fp32 ≥ 0,999 en media, con el mínimo
    informado, sobre esas frases;
  - Go int8 frente a Python con la misma cuantización: idéntico, o diferencia ≤ 1e-6 si es float.
- Determinismo:
  - `GOARCH=arm64` cross-compila;
  - corre en arm64 con `qemu-aarch64` si está en la VM (`which qemu-aarch64`); si no, dilo, y deja
    un test dorado (hash de los embeddings de 200 frases) para que el orquestador lo corra en ARM;
  - en amd64 el hash coincide con el de la referencia.
- Mide en la microVM y apúntalo en el README:
  - latencia p50/p99 a 16, 64 y 256 tokens;
  - tamaño del `.chispa-l1`;
  - RSS;
  - arranque en frío.
- `cd runtime/l1 && go vet ./... && go test -race ./...` en verde. `make test` y `make smoke` en la
  raíz siguen en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `runtime/l1/`. **No tocar**: `server/`, `model/` (solo leer `model/sondeo/`), `arena/` ni el Makefile raíz.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.
- El `.chispa-l1` exportado no va a git: pesa cientos de MB. Va a `/tmp` y su hash, al README.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin` y Python en `~/venv`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 150 min de reloj · ≤ 8 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, la paridad (coseno medio y
mínimo), el resultado del determinismo en arm64, latencias y tamaño, qué quedó sin verificar y qué
recomiendas.
