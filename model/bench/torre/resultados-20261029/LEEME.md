# G.6, la torre de L2 de punta a punta con el checkpoint real (c6a, 2026-10-29): no pasa

Rama del modelo: `claude/chispa-plan-83616c`. Rama del servidor: `claude/chispa-sdk-6773ef` @ `83c76d6`, sin integrar.

| punto | resultado |
|---|---|
| coseno de `h` ONNX frente a PyTorch, con poda | **0,954** (mínimo 0,901); el 7,5 % de los tokens pasa a `<unk>` |
| coseno sin `<unk>` (solo la cuantización) | **0,986**, por debajo de 0,999 |
| top-1 de choice, con poda / sin `<unk>` | **0,887** / 0,937, por debajo de 0,98 |
| tamaño y `metadata_props` | OK: 46,7 MB, dim 256, max_len 128, «passage: » |
| `go test -tags ort ./server/torre/...` | 6 pasan; **`TestAbrirSinORT` falla** («protobuf parsing failed»); `TestTorreConTokenizadorReal` se salta |
| `TestIgualdadTransformersPasaje` | se salta: no encontró el tokenizador con `CHISPA_TOK` |
| `chispa train --torre` y el servidor | **el servidor se cae**: «l1: límites de params fuera de rango» |
| torres al vuelo por `/v1/decide` | sin medir |

- **El int8 de la torre no da la fidelidad necesaria.** Con pesos aleatorios, el coseno era 0,9998. Con la torre entrenada
  el error de e5 int8 se amplifica: 0,986 sin `<unk>`, y además la poda resta otro tanto. Hay dos salidas:
  - exportar la torre con e5 en fp32 (≈ 175 MB) o con cuantización estática calibrada;
  - podar el vocabulario con el idioma de los esquemas.
- **Fallos para la sesión SDK:**
  1. `TestAbrirSinORT` falla al abrir el ONNX real.
  2. Los tests con el tokenizador real se saltan, así que hay que revisar la variable o la ruta que esperan.
  3. `chispa-server` rechaza el `.chispa` de `chispa train --torre` por los parámetros de L1.
- **No se relanza:** la semana está cerrada. Coste: una c6a de 4 min, ≈ 0,02 USD.
