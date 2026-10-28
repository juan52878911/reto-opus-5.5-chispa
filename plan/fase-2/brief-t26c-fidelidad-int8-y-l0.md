# T2.6c Fidelidad del ONNX int8 de L2 y L0 de muchas clases en `chispa train`

## Antecedentes
La prueba de punta a punta de T4.5 en AWS (`server/deploy/resultados/e2e-20261028/LEEME.md`) falló en dos puntos:
1. **massive.** `/v1/decide` saca 0,763, frente a 0,817 de `conjunta.py`. La causa probable es el ONNX int8 de L2:
   `model/l2/exportar.py` usa `quantize_dynamic(weight_type=QInt8)` sobre todo el grafo, y en la paridad con PyTorch (300
   filas de dev) coincide en top-1 solo en el 80 %, con una diferencia máxima de 0,34 (`exportar.informe.json` en esa
   carpeta). Con e5 int8 podado, la fase 0 daba un coseno de 0,9996 frente a fp32, así que lo que se rompe es
   probablemente lo que va después del codificador (las ranuras: atención y proyecciones), o el uso de `QInt8` sin
   `per_channel`.
2. **clinc150.** El servidor no arranca: `L0: weight table larger than 67108864 bytes`. El L0 de kindling (`pkg/chispa`,
   que entrena `sdk/python/chispa/entrenador_go/`) con 151 clases pasa del tope de 64 MB del lector. El tope está en el
   módulo de kindling, que no podemos cambiar desde aquí. Hay que entrenar un L0 que quepa.

## Hipótesis
- H1: cuantizar solo los MatMul del codificador e5, `per_channel=True`, y dejar las ranuras y las proyecciones de salida
  en fp32 sube el acuerdo top-1 con PyTorch a ≥ 0,98, con una diferencia media ≤ 1e-3, y mantiene el `.chispa` ≤ 60 MB y la
  latencia a 64 tokens dentro de +10 % de la actual. Se refuta si no.
- H2: limitar el número de características de L0 en `chispa train` (hashing o vocabulario podado por frecuencia; elige y
  justifica) deja el L0 de clinc150 por debajo de 64 MB con una pérdida ≤ 1 punto de macro-F1 de validación. Se refuta
  midiendo.

## Terminado cuando
- `model/l2/exportar.py`:
  - opciones de cuantización (`--cuant todo|codificador|ninguna`, `--per-channel`), por defecto la que gane H1;
  - el informe de paridad lleva el acuerdo top-1 y la diferencia media y máxima, y falla si el acuerdo top-1 < 0,95
    (umbral configurable);
  - tests nuevos en `model/l2/tests/`.
  - Mide aquí con e5 de `~/hf`. El codificador está congelado en T2.1b, así que la cabeza puede ir con pesos aleatorios
    con semilla: la fidelidad del codificador y de las ranuras no depende de que estén entrenadas. Da la tabla para
    `todo`, `codificador` y `ninguna`.
- `sdk/python/chispa/` (y `entrenador_go/` si hace falta):
  - un tope de tamaño de L0, `--l0-max-mb`, 48 por defecto, que reduce características hasta caber;
  - mide el tamaño y la validación con fixtures sintéticas de 151 clases;
  - si los datos de clinc150 están en el golden (`~/hf`), mídelo también con ellos.
- Prueba en seco: tests, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/exportar.py`, `model/l2/tests/test_exportar*.py` y `sdk/python/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- la tabla de H1 (acuerdo top-1, diferencia media, MB y ms a 64 tokens);
- H2 (MB y validación);
- qué quedó sin verificar.
