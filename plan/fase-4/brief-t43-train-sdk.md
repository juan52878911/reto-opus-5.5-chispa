# T4.3 `chispa train` few-shot en CPU y SDK de Python

Plan aprobado, fase 4, T4.3. Criterio: con 50 ejemplos por clase, `chispa train` produce un `.chispa`
en ≤ 5 minutos en CPU.

Antecedentes:
- `model/l2/` (T2.1, T2.4, T2.6): calibración y exportación;
- `format/chispa3/`: el formato;
- `server/`: el contrato `/v1/decide`.
Se adelanta por la directiva de Juan del 2026-10-28.

## Hipótesis
- El modo few-shot del producto se resuelve sin reentrenar el codificador:
  - un L0 lineal sobre los ejemplos;
  - prototipos de L2 calculados con los ejemplos de soporte (la vía de T2.1b);
  - torres de opción precalculadas;
  - calibración en una partición de validación de los mismos ejemplos.
- Todo cabe en ≤ 5 min de CPU con 50 por clase.
- Se refuta midiendo en la microVM, que es un i3: es una cota pesimista.

## Terminado cuando
- `sdk/python/chispa/`, un paquete instalable (`pyproject.toml`, sin dependencias pesadas en el
  cliente) con dos partes:
  - **Cliente HTTP** de `/v1/decide`: `Chispa(url).decidir(estado, preguntas)`, con tipos para
    `choice`, `noul` y `score`, reintentos y nonce. Está probado contra el JSON del contrato en
    `server/README.md`, con un servidor falso en los tests;
  - **`chispa train`** (CLI y función):
    - entrada: un CSV/JSONL de ejemplos y un esquema YAML/JSON con preguntas, opciones y descripciones;
    - salida: un `.chispa` v3 con META, L0 (llama al entrenador de L0 que use `server/` o `arena/`,
      vía `go run`, si está; si no, deja L0 fuera y dilo), ESQUEMAS (las torres, con
      `model/l2/exportar.py` si hay checkpoint de L2) y CALIB;
    - sin checkpoint de L2, solo L0 y L1, con L1 sobre el potion exportado.
- Una prueba de punta a punta en la microVM: 50 por clase de intención de `model/sondeo/` → `chispa
  train` → `.chispa` → cargar con `format/chispa3` (con un `go run` pequeño) → precisión en el test
  del sondeo. Mide el tiempo de reloj y apúntalo en el README.
- Tests con `unittest` en `sdk/python/tests/`.
- `python -m unittest discover -s sdk/python -t sdk/python`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `sdk/python/`. Lo demás solo se usa.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, el tiempo de `chispa train` con 50
por clase y su precisión, qué quedó sin verificar y qué recomiendas.
