# T2.4 + T2.6 Calibración por tipo de pregunta, exportación a ONNX int8 y empaquetado en `.chispa` v3

Encargo: `plan/fase-2/encargo.md`, con los criterios de T2.4 y T2.6 congelados. Parte de:
- `model/l2/` (T2.1);
- `format/chispa3/` (T2.5, el formato y su cargador en Go);
- `server/` (T4.1, la capa L2 es un stub).
Aún no hay checkpoint entrenado aquí: trabajas con uno construido al azar con la misma arquitectura.
El orquestador corre la calibración real sobre el checkpoint de la g5.

## Hipótesis
- La temperatura por tipo y pregunta, ajustada en dev (Platt o búsqueda en rejilla de T, más a/b
  en noul), da ECE ≤ 0,05.
- τ de escalate, elegido en dev por tarea, da la cobertura máxima a precisión 0,95.
- El codificador más las ranuras se exportan a un solo ONNX. Las torres de opción se precalculan y
  van a la sección ESQUEMAS. Con cuantización int8 dinámica, la diferencia con fp32 en las
  probabilidades es ≤ 0,01 de media y el fichero ocupa ≤ 60 MB.
- Se refuta midiendo.

## Terminado cuando
- `model/l2/calibrar.py --ckpt <dir> --dev <jsonl…> --salida calib.json`:
  - T, a, b y θ por tipo y tarea;
  - τ por tarea, a la máxima cobertura con precisión ≥ 0,95 en dev;
  - informe de ECE antes y después.
- `model/l2/exportar.py --ckpt <dir> --calib calib.json --esquemas <jsonl…> --salida l2.chispa`:
  1. ONNX del codificador más las ranuras (entrada: ids y máscara; salida: S ∈ R^{K×d}) con opset ≥ 17;
  2. int8 dinámico con onnxruntime (sin optimum), aplicando el vocabulario podado de
     `model/bench/vocab-podado-e5-small.json` si el ckpt lo usa;
  3. torres de opción precalculadas en int8 con escala para cada pregunta y opciones de los
     esquemas dados;
  4. un `.chispa` v3 con META, L2, ESQUEMAS y CALIB. Ese paso lo hace un `format/chispa3/cmd/empaquetar`
     en Go, pequeño, que ya está en esa zona si existe; si no, crea `model/l2/empaquetar_go/` con un `go run`
     que importa `format/chispa3` mediante `replace`.
- Paridad: probabilidades de Python fp32 frente a ONNX int8 sobre 500 filas de dev; diferencia media
  y máxima, y acuerdo del top-1.
- Latencia del ONNX int8 en la microVM a 16, 64 y 256 tokens con 1 hilo. Es solo una cota; el
  orquestador mide en c6a.
- Tests con `unittest`:
  - calibración en datos sintéticos con ECE conocida;
  - exportación e ida y vuelta del `.chispa` con `format/chispa3` (desde Go, con `go test` en ese
    paquete pequeño);
  - paridad en un modelo diminuto.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/` (archivos nuevos: `calibrar.py`, `exportar.py`, `empaquetar_go/`). No toques
  `entrenar.py` ni `modelo.py` salvo para exponer lo mínimo que la exportación necesite. Hay otro
  worker cambiando `entrenar.py` y `modelo.py` a la vez (T2.2): **evita conflictos**.
- Ni `server/` ni `format/chispa3/`: solo se usan.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` y Go en `~/go-sdk/bin`. Sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: qué cambiaste, rama y sha, la paridad, el tamaño, la latencia,
qué quedó sin verificar y qué recomiendas.
