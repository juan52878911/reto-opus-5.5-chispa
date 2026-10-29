# D1 Dos diagnósticos: bug de la poda ampliada y paridad servidor ↔ Python en JevBench

## Antecedentes
- **Poda** (`model/bench/torre/resultados-20261029-movil/LEEME.md`). Con el checkpoint real, fp32 **con poda ampliada**
  cae a top-1 0,90 y coseno 0,931, aunque la comprobación solo tiene un 0,08 % de `<unk>`. Sin poda da 1,00. Si la poda
  solo cambiara los `<unk>`, fp32 con poda tendría que dar ≈ 1,0. Sospechas:
  - la tabla id → id podado que se mete en el grafo con `--vocab-ampliar`;
  - el orden o el tamaño de la matriz de embeddings recortada;
  - los textos de la torre de las 300 filas de paridad, que tienen más `<unk>` que la comprobación (míralo).

  **Esto se ve con pesos aleatorios.** e5 es el que manda en el embedding, así que fp32 con poda frente a fp32 completo,
  sobre los mismos textos sin `<unk>`, tiene que dar coseno 1,0.
- **Paridad** (`model/bench/torre/resultados-20261029-p5c/`).
  - `/v1/decide` con torres al vuelo saca 0,437 en JevBench, frente a 0,485 de Python k = 0 (`jevbench_l2`) con el mismo
    checkpoint.
  - Discrepan caso a caso:
    - choice: 34 de 139, más en textos largos (32 % frente a 17 %);
    - noul: 44 de 74, con el servidor desplazado hacia `true`;
    - score: 18 de 18.
  - `capas_por_caso.jsonl` trae las probabilidades del servidor y `pred/l2_k0.jsonl` las de Python.
  - Sospechas:
    - **CALIB:** el `.chispa` sale de `chispa train --torre` sobre un esquema mínimo de 16 ejemplos
      (`model/bench/torre/servidor.py`), y sus a, b, T y θ no son los de Python;
    - el **truncado** de la consulta: max_tok 256 en Python, ¿y en el servidor?;
    - el **texto de la pregunta** y el de la **torre** que arma `servidor.py` (la petición) frente a `jevbench_l2` y
      `model/evaluacion/jevbench.py`.

## Terminado cuando
- **Poda.**
  - Un test con pesos aleatorios compara fp32 con poda ampliada frente a fp32 completo en textos sin `<unk>`. Antes del
    arreglo tiene que fallar si el bug existe; después, dar coseno ≥ 0,9999.
  - Arregla la causa en `model/l2/exportar.py`.
  - Explica en el informe cuál era.
  - Si resulta que no hay bug y la caída sale de los `<unk>` de los textos de la torre, mídelo y dilo.
- **Paridad.**
  - `model/bench/torre/paridad_servidor.py` compara, para N casos de JevBench, servidor y Python, campo a campo:
    - texto de la consulta tras el prefijo y la tokenización (número de tokens y ¿truncado?);
    - texto de la torre por opción;
    - s por opción (el servidor debe exponerlas en `/v1/decide` en modo depuración si existe; si no, recalcúlalas en
      Python con el ONNX del `.chispa` y el mismo texto que usa el servidor);
    - parámetros de CALIB usados (los del `.chispa` frente a los del checkpoint);
    - probabilidad final.
  - Atribuye cada discrepancia a una causa: CALIB, truncado, texto de pregunta, texto de torre u otra.
  - Con eso, en `e2e.sh` añade una pasada que use la **CALIB global de L2 del checkpoint** (la de `calibrar.py` sobre el
    dev del metaentrenamiento, la que usa Python) en lugar de la de `chispa train --torre`. Puede ser un
    `chispa train --torre` con un flag que conserve la CALIB del `l2.chispa`, si existe; si no, reemplazando la sección
    CALIB del `.chispa` desde Python con `sdk/python/chispa/formato.py`. Así se ve si cierra el hueco.
- **Una sola corrida de c6a** (`e2e.sh`, ≤ 75 min) que mida:
  1. fp16 con la poda corregida y fp32 con la poda corregida, del perfil móvil: top-1, MB y latencia;
  2. el diagnóstico de paridad;
  3. JevBench por servidor con la CALIB global, con la exactitud por tipo frente a Python.
  - Deja todo listo para lanzar: el orquestador sustituye `__CHISPA_S3__`.
- **Prueba en seco** (`CHISPA_LOCAL=1`), tests, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/exportar.py`, `model/l2/tests/**` y `model/bench/torre/**`.
- No toques `server/` ni `sdk/`. Si el arreglo de producto va ahí, descríbelo en el informe para la otra sesión.
- Rama: la que te da delega. Base: `integracion`. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, modelos en `~/hf` y datos en `~/datos`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 120 min de reloj · ≤ 7 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- causa del bug de la poda;
- qué mide la corrida;
- qué sustituyo;
- qué arreglo de producto propones para la otra sesión.
