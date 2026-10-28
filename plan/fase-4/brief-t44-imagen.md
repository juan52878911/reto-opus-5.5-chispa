# T4.4 Imagen OCI del servidor (con L2 vía ONNX Runtime) y su prueba en AWS

Plan aprobado, fase 4, T4.4. Criterio: la imagen se construye, arranca y responde a `/v1/decide`.
Antecedentes:
- `server/` (T4.1, T4.1b): L0 y L1 reales; L2 tras `//go:build ort`, sin compilar todavía con ORT;
- `nix/flake.nix`;
- el patrón de user-data de `model/bench/aws/arranque.sh`.
Tú no lanzas nada en AWS. El orquestador lanza una c6a.xlarge con tu script.

## Hipótesis
- Un Dockerfile multietapa (Go 1.27 → distroless o debian-slim con `libonnxruntime.so` de la
  release oficial de ORT) produce una imagen de ≤ 150 MB con `chispa-server -tags ort`.
- En la instancia, la imagen sirve un `.chispa` v3 con L0 y L1, y L2 si hay un `l2.chispa` en S3.
- Se refuta si `go build -tags ort` no compila contra la API de ORT de esa versión.

## Terminado cuando
- `server/deploy/Dockerfile`, multietapa, con la versión de ORT fijada en un `ARG`, y
  `server/deploy/README.md` con la construcción y el uso.
- `nix/`: un paquete `chispa-server` en el flake. Compila sin ORT: es la variante sin cgo. No hace
  falta probarlo con nix aquí si no está instalado; dilo.
- `server/deploy/aws/arranque.sh`, user-data para Amazon Linux 2023 x86_64, con el patrón de siempre:
  - marcador `CHISPA_S3`, `shutdown -h +90` y un trap que sube `log.txt` y `resultados.tgz`;
  - código en `$CHISPA_S3/codigo.tgz` y modelos opcionales en `$CHISPA_S3/modelos/{l0l1,l2}.chispa`, **por fichero**;
  - pasos:
    1. instala docker;
    2. construye la imagen;
    3. mide su tamaño;
    4. la arranca con el `.chispa` (si no hay ninguno en S3, genera uno pequeño con L0 desde
       `server/testdata` y un L1 diminuto, como en los tests);
    5. hace 20 peticiones de contrato a `/v1/decide`, `/healthz` y `/metrics`;
    6. mide decisiones/s con `cmd/carga` dentro de la instancia;
    7. compila también `go build -tags ort ./...` fuera de docker y corre los tests de `decide`
       con `-tags ort`;
  - todo al log.
- `server/deploy/aws/empaquetar.sh`: empaqueta `server/`, `runtime/l1/` y `format/chispa3/`, que hacen falta por los `replace`.
- Prueba en seco aquí, `CHISPA_LOCAL=1`: salta docker y ORT, compila sin la etiqueta y corre los pasos 4 a 6
  con el binario nativo. Pega la cola del log.
- `cd server && go vet ./... && go test ./...`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `server/deploy/**` y `nix/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`. Sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas: la rama y el sha, la cola de la prueba en seco y lo que tengo
que sustituir para lanzarlo.
