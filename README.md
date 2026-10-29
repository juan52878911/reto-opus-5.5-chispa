# Chispa

Clasificador tipado (`choice`, `score`, `noul`) de bajo coste y de propósito general: decide sobre esquemas y opciones que no ha visto,
en zero-shot o con pocos ejemplos, con una cascada L0 → L1 → L2 → escalar en CPU. massive, clinc150, hatecheck, spam e injection son
benchmarks, no el objetivo. Documentación para quien integra: [`docs/00-indice.md`](docs/00-indice.md).

Monorepo. Mapa:

- `docs/`: documentación de producto, empieza en [`docs/00-indice.md`](docs/00-indice.md).
- `format/chispa3/`: el formato `.chispa` v3 (secciones `META`…`SOPL1`) y su cargador en Go. [README](format/chispa3/README.md).
- `server/`: servidor Go `chispa-server` (`POST /v1/decide`, `/healthz`, `/metrics`). [README](server/README.md). Dentro:
  - `server/decide/`: contrato, cascada y capas (L0, L0TF, L1, L2, L2c).
  - `server/torre/`: torre de L2 al vuelo con ORT. [README](server/torre/README.md).
  - `server/api/`: `openapi.yaml`, la especificación del contrato.
  - `server/carga/`: arnés de carga (`correr.sh`, `textos-es-co.txt`, `esquemas-carga.json`). [README](server/carga/README.md).
  - `server/deploy/`: imagen OCI con ORT, receta de AWS, `mkmodelo`. [README](server/deploy/README.md).
  - `server/cmd/`: `chispa-server` y `carga`.
- `runtime/`: `l1/` (Model2Vec en Go int8) y `tok/` (tokenizador de e5 en Go).
- `model/`: entrenamiento, L2, datos, líneas base e informes de las fases.
- `sdk/`: SDK cliente. [`sdk/README.md`](sdk/README.md). `python/` (wheel, `chispa train`), `movil/` (núcleo Go `chispamovil`),
  `android/` (Kotlin), `ios/` (Swift, sin compilar).
- `demo/wasm/`: L1 en el navegador y arnés de latencia. [README](demo/wasm/README.md).
- `deploy/kindling/`: imagen de `chispa-server` para una microVM de kindling (`imagen-cpu` e `imagen-ort`). [README](deploy/kindling/README.md).
- `pilotos/`: kit de piloto para una empresa colombiana (guía, plantillas de esquemas, datos y consentimiento, métrica). [README](pilotos/README.md).
- `audio/`: diseño de Chispa de audio (`DISENO.md`) y esqueleto sin modelos. [README](audio/README.md).
- `arena/`: banco de pruebas adversarial en Go (cmd, internal, contracts congelado, scripts). [README](arena/README.md).
- `nix/`: entorno reproducible (`nix/flake.nix`: Python con torch, sentence-transformers, onnxruntime y optimum, más Go 1.27).
- `plan/`: encargos y briefs.

Desde la raíz, `make test` y `make smoke` delegan en `arena/`.
