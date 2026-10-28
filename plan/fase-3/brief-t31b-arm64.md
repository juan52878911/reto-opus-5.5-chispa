# T3.1b Prueba dorada del runtime L1 en arm64 real (AWS Graviton)

Sigue a T3.1: `runtime/l1/`, con su README y el test dorado de 200 embeddings. Tú no lanzas nada en AWS.

## Hipótesis
- Con acumulación entera y una sola división final, el hash dorado de los 200 embeddings es idéntico
  en arm64 y en amd64.
- Se refuta si no coincide en una t4g o c7g.

## Terminado cuando
- `runtime/l1/aws/arranque-arm64.sh`, user-data para Amazon Linux 2023 **arm64** con el mismo patrón
  que `model/bench/aws/arranque.sh`:
  - el marcador `CHISPA_S3=__CHISPA_S3__`;
  - el código llega como `$CHISPA_S3/codigo.tgz`;
  - un trap que sube `log.txt` y `resultados.tgz`;
  - `shutdown -h +60` al empezar.
  En la instancia:
  1. instala Go 1.27 desde go.dev para linux-arm64 y Python 3.11 con `pip install` de model2vec,
     numpy, safetensors y tokenizers (lo mínimo que use `exportar.py`);
  2. baja `minishlab/potion-multilingual-128M`;
  3. exporta el `.chispa-l1` y comprueba que el hash del cuerpo es
     `01fe1e57dc1bb1917757723e35264b146c25c4d81a3950a8ec7bb0f6a4ba8808`;
  4. corre `go test -run Dorado ./...` (o el nombre real del test dorado) y `cmd/l1medir` para la latencia;
  5. guarda `uname -m`, `lscpu` y la salida de los tests.
- `runtime/l1/aws/empaquetar.sh`, que empaqueta solo `runtime/l1/` y `model/sondeo/` si el test lo necesita.
- Prueba en seco aquí en amd64 con `CHISPA_LOCAL=1`: salta las instalaciones y usa `~/go-sdk`,
  `~/venv` y `~/hf`. Pega la cola del log.
- `bash -n` pasa. `cd runtime/l1 && go test ./...` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `runtime/l1/aws/` y, si hace falta un ajuste mínimo para el modo instancia, `runtime/l1/README.md`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, Python en `~/venv`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 45 min de reloj · ≤ 2 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas: rama y sha, la cola del log de la prueba en seco, y qué tengo
que sustituir para lanzarlo.
