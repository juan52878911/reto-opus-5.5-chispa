# Inicio rápido

De un esquema a una petición `curl`. Los comandos se escriben desde la raíz del repositorio.

## Tres modos
Chispa es multipropósito: el camino por defecto no pide datos etiquetados de tu tarea. Cada modo añade datos y calidad.
massive, clinc150 y las demás tareas son pruebas de que cada modo funciona, no el objetivo del producto.

| Modo | Qué necesitas | Qué corre | Cifra medida | Límite |
|---|---|---|---|---|
| 1. Zero-shot | La pregunta y las opciones (con descripción) | L1 con el esquema, sin ejemplos | macro-F1 medio 0,353 con el L1 propio de 256 dim y 0,455 con potion, en 5 tareas ([fuente](../model/l1/resultados/2026-10-28/informe.md)); massive 0,406 y clinc150 0,445 con potion | L1 por sí solo es flojo sin ejemplos. **L2 no sirve esquemas nuevos** (ver [08](08-esquemas-nuevos.md)) |
| 2. Few-shot | ~50 ejemplos por clase; `chispa train` sin `--conjunta` | L0 (+ L1 con `--l1`) | Intención del sondeo, 50 por clase: L0 0,821; L1 0,672; cascada L0→L1 0,762 contando lo escalado como fallo ([fuente](../sdk/python/README.md#punta-a-punta-intención-del-sondeo-50-por-clase)) | Una tarea y 390 filas de test (±2 puntos). La variante con L2 y prototipos no se midió |
| 3. Con datos del cliente | Train etiquetado de la tarea, checkpoint de L2 y e5; `--conjunta` | L0TF + L2c (cabeza conjunta) | massive 0,814 y clinc150 0,887 por `/v1/decide` ([07](07-rendimiento-y-limites.md#calidad-de-punta-a-punta)) | Solo `choice`; un `.chispa` por pregunta; el repositorio no trae checkpoint de L2 |

Un esquema que llega en la petición sin `.chispa` propio solo lo decide L1 (modo 1). L0, L2, L2c y L0TF dependen del esquema con el que se entrenó el `.chispa`.

## Requisitos
- Python ≥ 3.9 para `chispa train` ([`pyproject.toml`](../sdk/python/pyproject.toml)). Esquemas `.yaml`: instala PyYAML. Los `.json` no lo piden.
- Go, para el entrenador de L0 y para compilar `chispa-server`. Sin Go, `chispa train` escribe META + L1 + CALIB y no lleva L0.
- Solo para el modo 3 (`--conjunta`): torch y transformers, un checkpoint de L2 y e5 (ver el paso 3).
- Los comandos de Python se corren con `PYTHONPATH=sdk/python`, o tras `pip install ./sdk/python`.

## 1. Zero-shot: solo el esquema (modo 1)
Un `.chispa` con META y L1 (más CALIB si lo tienes) basta: L1 calcula al vuelo el embedding de «pregunta · opción · descripción» de cada
opción y lo cachea por esquema. Escribe las descripciones con cuidado: son lo único que L1 ve de tu tarea. Sirve `choice` y `noul`; `score` no.
Salta al paso 5 con ese `.chispa`. Para pasar a few-shot, sigue con los pasos 2 a 4.

## 2. Los ejemplos (modos 2 y 3)
Un fichero por pregunta. CSV con cabecera, o JSONL, con columnas `texto` (o `text`) y `etiqueta` (o `label`).
Cada etiqueta debe ser una opción del esquema.

```
texto,etiqueta
"quiero comprar dos camisetas",compra
"mi pedido no ha llegado",soporte
```

El recorrido medido con 50 ejemplos por clase está en [`sdk/python/README.md`](../sdk/python/README.md#punta-a-punta-intención-del-sondeo-50-por-clase).

## 3. El esquema
JSON o YAML con `id`, `pregunta`, `tipo` (`choice`, `noul` o `score`) y `opciones` (mapa id → descripción).

```json
{"id": "intencion", "pregunta": "¿Qué quiere hacer la persona?", "tipo": "choice",
 "opciones": {"compra": "quiere comprar", "soporte": "tiene un problema con un pedido"}}
```

Opcionales: `licencias` y `dorado`, que van a META. Si el fichero trae varias preguntas, elige una con `--pregunta`.
Un `.chispa` por pregunta: el servidor elige L0 por el conjunto de etiquetas.

## 4. Entrenar con `chispa train`
**Few-shot (modo 2).** Sin L2 (L0 y, si quieres, L1):

```
PYTHONPATH=sdk/python python -m chispa train --ejemplos ejemplos.csv --esquema esquema.json --salida intencion.chispa [--l1 potion.chispa-l1]
```

`--l1` es el potion que exporta `python runtime/l1/exportar.py` (155 MB por fichero).

**Con datos del cliente (modo 3).** Con la cabeza conjunta (L0TF + L2c), que es la configuración medida en [07](07-rendimiento-y-limites.md); necesita el train etiquetado de tu tarea:

```
PYTHONPATH=sdk/python python -m chispa train --ejemplos ejemplos.csv --esquema esquema.json --salida intencion.chispa \
  --ckpt mejor.pt --l2 l2.chispa --conjunta --repo .
```

- `--ckpt`: el checkpoint de L2 (e5 con ranuras y torres). **El repositorio no trae ninguno.** Se entrena con `python -m model.l2.entrenar`
  ([`model/l2/README.md`](../model/l2/README.md#uso)).
- `--l2`: el `.chispa` con L2 y ESQUEMAS que sale de `python -m model.l2.calibrar` y `python -m model.l2.exportar`.
  Sin `--l2`, `--ckpt` calibra y exporta por ti.
- `--repo`: la raíz del repositorio. También vale `CHISPA_REPO`.
- `--conjunta` solo sirve para `choice`. Escribe `CONJ`, `L0TF` y `tau_l2c` en `CALIB`.
- Topes: `--l0-max-mb` y `--l0tf-max-mb` (48 por defecto). `--precision-objetivo` (0,95) fija el τ de L2c.

Cada flag está definido en [`sdk/python/chispa/cli.py`](../sdk/python/chispa/cli.py).

## 5. Servir
```
cd server && go build -o chispa-server ./cmd/chispa-server
./chispa-server -addr 127.0.0.1:8090 -modelo ../intencion.chispa
```

Con L2 o L2c hacen falta además `-tags ort`, ONNX Runtime y el tokenizador (`-tok`). Ver [06-despliegue.md](06-despliegue.md).
Sin ellos, el servidor arranca y L2 queda en stub, con un aviso en el log. El resto de capas responde.

Flags de [`server/cmd/chispa-server/main.go`](../server/cmd/chispa-server/main.go): `-addr`, `-config`, `-modelo`, `-tok`.

Sin Go instalado en el servidor, usa la imagen OCI ([06-despliegue.md](06-despliegue.md)).

## 6. Una petición
```
curl -s localhost:8090/healthz
curl -s localhost:8090/v1/decide -d '{"state":"quiero comprar dos camisetas","questions":[{"id":"u1","question":"¿Qué quiere hacer la persona?","kind":"choice","options":[{"id":"compra","description":"quiere comprar"},{"id":"soporte","description":"tiene un problema con un pedido"}]}]}'
```

Con L0, L2 o L2c, el `question` y los ids deben ser los del esquema de entrenamiento: L0 elige modelo por el conjunto de ids, y L2 y L2c usan también la pregunta. L1 acepta un esquema nuevo.

Respuesta: ver [03-api.md](03-api.md).

## Desde Python
```python
from chispa import Chispa, Choice
rs = Chispa("http://127.0.0.1:8090").decidir("quiero comprar dos camisetas",
    [Choice("u1", "¿Qué quiere hacer la persona?", [("compra", "quiere comprar"), ("soporte", "tiene un problema con un pedido")])])
```
