# T4.5 de punta a punta en AWS (c6a.xlarge, 2026-10-28): funciona, pero H2 no se cumple

- **Cadena completa.** Funcionó de principio a fin:
  - el tokenizador de e5 en Go, con sus tests contra `transformers` en la instancia;
  - L2 exportado a ONNX int8 (46 MB);
  - `chispa train --conjunta` (`.chispa` con META+L0+L2+ESQUEMAS+CALIB+CONJ);
  - `chispa-server -tags ort`;
  - el test completo de massive por `/v1/decide`.
- **massive: macro-F1 0,763**, frente a 0,817 de `conjunta.py` (T2.2c): Δ −5,4. **H2 no se cumple.**
  - **Causa probable: el ONNX int8 de L2.** En la paridad de `exportar` sobre 300 filas de dev coincide en top-1 con
    PyTorch solo en el 80 %, con una diferencia máxima de 0,34 (`exportar.informe.json`).
  - **El L0 de Chispa no lo explica.** Valida 0,790, frente a 0,794 del L0 de sklearn.
  - **simproto int8 tampoco.** Su |Δp| ≈ 3e-3 es demasiado pequeño para explicarlo.
- **clinc150: no arranca.** `L0: weight table larger than 67108864 bytes`: con 151 clases, la tabla de pesos de L0 de
  kindling (`pkg/chispa`) pasa del tope de 64 MB.
- **Latencia en la c6a** (massive, 1 cliente):
  - p99 total 8,7 ms medido en el cliente;
  - L0 responde el 61 % en la cascada, con p99 de 0,1 ms;
  - L2c tiene p99 de 8,6 ms con el codificador incluido; los mensajes de massive son cortos.
- **Arreglos en este intento.** El primero falló porque `exportar.py` fijaba `GOPROXY=off`; lo arregla el commit
  «exportar: respeta GOPROXY…». Coste: dos c6a, unos 30 min en total, ≈ 0,1 USD.
