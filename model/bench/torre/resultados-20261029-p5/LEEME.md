# P5, primera corrida (c6a.2xlarge, `integracion` @ `fd051c7`, checkpoint G.8 corrida 2, 2026-10-29)

- **Perfil servidor:** consulta y torre fp32 con vocabulario completo.
  - **Paridad exacta:** coseno de `h` 1,0000 (mínimo 1,0000), top-1 1,000 y 0 % de `<unk>`.
  - Tamaño de la torre: 471,6 MB. Latencia de la torre: p50 16,2 ms y p99 22,0 ms por texto con 1 hilo. max_len 256.
- **Perfil móvil, frente a PyTorch con el checkpoint real:** int8 dinámico con poda ampliada usando los textos de
  calibración.
  - Coseno 0,905 con un 6,8 % de `<unk>`, y 0,971 sin `<unk>`; top-1 0,88. **No alcanza el objetivo** (≥ 0,93).
  - Con este checkpoint el int8 dinámico pierde fidelidad. Además, la ampliación con los 500 textos de calibración no basta
    para JevBench y massive.
  - Tamaño: 46,7 MB más 48,2 MB de consulta. Latencia: p50 8,8 ms.
- **Servidor por `/v1/decide`: no se llegó a medir.** `chispa train --torre` rechaza el `.chispa`:
  `la dim de la torre (256) no casa con la de L2/ESQUEMAS (131328)`. 131328 = `2<<16 | 256`: `sdk/python/chispa/torre.py`
  (`comprobar_dim_l2`) lee el primer u32 de ESQUEMAS sin quitarle la versión v2. Arreglo: `dim_l2 = u32 & 0xFFFF`
  (y validar la versión con `u32 >> 16`). Corresponde a la zona del SDK.
- **Pasan:** `go test -tags ort ./server/torre/...` (9 PASS, con `CHISPA_TOK`), `TestIgualdadTransformersPasaje` y la
  compilación de `chispa-server -tags ort`. El `.chispa` con score K ≥ 3 se regenera bien.
- **Coste:** c6a.2xlarge spot de 5 min, ≈ 0,02 USD.
