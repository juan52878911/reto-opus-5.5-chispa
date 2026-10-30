# Dorados de determinismo en arm64 nativo (Graviton c7g.large spot, `aee1328`, 2026-10-29)

Los dorados se generaron en amd64 (BD, `0988b06`). Aquí se comprueban en arm64 nativo (aarch64, Go 1.27.1, ORT 1.31.1
aarch64). Coste: 3 min de spot, ≈ 0,01 USD.

| paso | resultado |
|---|---|
| dorados del servidor (`decide`, `Dorados`) | OK, 165 peticiones idénticas a amd64 en todas las capas y tipos |
| dorados con ORT real (`-tags ort`, `DoradosORT`) | OK, 8 peticiones, \|Δ\| máx. 1,94e-07 (tolerancia 1e-06) |
| concurrencia | OK |
| `go test ./decide/...` | OK |
| chispamovil (`go test ./...`) | OK, 71 PASS, incluidos sus dorados (95 peticiones) |

**Se cumple el criterio:** arm64 da lo mismo que amd64 dentro de la tolerancia documentada.

**4 tests de chispamovil se saltan** porque falta un fichero que esta corrida no lleva; ninguno es de los dorados:
- `TestMismaHuellaQueDemoWasm`;
- `TestMaxLenDeMetadatos`;
- `TestTokenizarE5ParidadConRuntimeTok`;
- `TestTextoLargoL2ParidadConServidor`.

Faltan `~/.cache/chispa/e5.chispa-tok` y la demo WASM.
