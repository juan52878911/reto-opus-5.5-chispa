# T2.6b La cabeza conjunta L0 + L2 en el producto: `.chispa`, `chispa train` y servidor

## Antecedentes
- Decisión de Juan del 2026-10-28: «C y después b».
- T2.2c y T2.2d (`model/l2/resultados/t22c-conjunta/LEEME.md` y `t22d-conjunta/LEEME.md`): la cabeza conjunta por tarea
  (`model/l2/conjunta.py`, cabeza `lr`) gana a la cascada L0 → L2 en 4/5 tareas y pasa el listón de T2.2 en 5/5.
  - Su entrada son los log-probs de L0 (entrenado con todo el train del cliente) y las similitudes de L2 con soporte
    (prototipos de los ejemplos del cliente).
  - La cabeza es por tarea, igual que L0, así que se entrena en `chispa train`, junto a L0.
- Lo que hay hoy:
  - `format/chispa3/` (secciones META, L0, L1, L2, ESQUEMAS y CALIB, con fuzzing);
  - `sdk/python/chispa/train.py` (`chispa train`: L0 con `entrenador_go/` y L1, más L2 y ESQUEMAS si se le pasan);
  - `server/decide/` (cascada; L2 con ORT detrás de `-tags ort` en `l2_ort.go`, y `l2_stub.go` sin ORT);
  - `model/l2/exportar.py` (ONNX de L2: el codificador y las ranuras dan S).

## Hipótesis
- Una sección nueva, `CONJ`, con los pesos de la cabeza por esquema (hash del esquema, dimensiones, pesos y sesgo en
  float32, y el tipo de cabeza) y los prototipos de L2 por clase en int8 con escala, cabe en < 1 MB por tarea de 150 clases.
- El servidor, con `CONJ` presente, sustituye la capa L2 por «L2 conjunta»:
  - log-probs de L0 (ya calculadas en la cascada) y similitudes de L2 frente a los prototipos dan la cabeza y luego softmax;
  - mismo contrato `/v1/decide` y la misma τ de CALIB.
- Python (`conjunta.py`) y Go deben coincidir: |Δp| ≤ 1e-4 en las probabilidades de la cabeza, dadas las mismas entradas.
- Se refuta si no coinciden, o si el formato no admite una sección nueva sin romper los ficheros v3 existentes.

## Terminado cuando
- `format/chispa3/`:
  - `CONJ` como tipo nuevo (al final del enum, sin renumerar), con escritor, lector y validación;
  - los ficheros sin `CONJ` siguen cargando igual: test de ida y vuelta, y fuzz de 5 min sobre el lector nuevo.
- `sdk/python/chispa/train.py`:
  - con `--l2 <l2.chispa>` y `--conjunta`, calcula las características como `model/l2/conjunta.py` (impórtalo; no lo copies):
    L0 fuera de pliegue en los ejemplos y prototipos de L2 sin la propia fila;
  - entrena la cabeza `lr` y escribe `CONJ`;
  - sin `--conjunta`, el fichero no cambia.
- `server/decide/`:
  - capa `L2c` («L2 conjunta») que usa `CONJ` si existe; si no, se comporta como hoy;
  - el codificador va detrás de una interfaz, para probar sin ORT con similitudes falsas;
  - test de paridad Go ↔ Python con un fixture que genera `conjunta.py` (entradas fijas → probabilidades esperadas,
    |Δp| ≤ 1e-4);
  - `go test ./...` y `go vet ./...` sin la etiqueta `ort`.
  - Con `-tags ort`, que compile si la VM tiene la biblioteca; si no, dilo. Se probará en AWS como en T4.4.
- `server/README.md` y `sdk/python/README.md`: cómo se activa y qué cuesta en latencia. La cabeza son µs frente a los
  ~30 ms de L2.
- `make test`, `make smoke` y `python -m unittest discover -s model -t .` en verde. Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `format/chispa3/**`, `sdk/python/**`, `server/decide/**`, `server/README.md` y `model/l2/tests/fixtures_conjunta/**`
  (para el fixture de paridad).
- No toques `contracts/`, `model/esquema.md` ni `model/l2/conjunta.py`. Si necesitas cambiar `conjunta.py`, dilo en el informe.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, Python en `~/venv` y modelos en `~/hf`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto. Las PQRS no entran.

## Tope
- ≤ 150 min de reloj · ≤ 8 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas:
- rama y sha;
- el tamaño de `CONJ` en una tarea de 150 clases;
- la paridad;
- el fuzz;
- qué falta para medir en AWS con ORT;
- qué quedó sin verificar.
