# Chispa

Monorepo. Mapa:

- `arena/`: banco de pruebas adversarial en Go (cmd, internal, contracts congelado, scripts). Su README está en `arena/README.md`.
- `sdk/`: SDK cliente de Chispa (esqueleto, ver `sdk/README.md`).
- `server/`: servidor de inferencia (esqueleto, ver `server/README.md`).
- `nix/`: entorno reproducible (`nix/flake.nix`: Python con torch, sentence-transformers, onnxruntime y optimum, más Go 1.27).
- `model/`: informes y conjunto de sondeo de la fase 0.
- `plan/`: encargos y briefs.
- `docs/`: documentación de producto, empieza en [`docs/00-indice.md`](docs/00-indice.md).

Desde la raíz, `make test` y `make smoke` delegan en `arena/`.
