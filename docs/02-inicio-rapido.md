# Inicio rápido

De 50 ejemplos por clase a una petición `curl`. Los comandos se escriben desde la raíz del repositorio.

## Requisitos
- Python ≥ 3.9 para `chispa train` ([`pyproject.toml`](../sdk/python/pyproject.toml)). Esquemas `.yaml`: instala PyYAML. Los `.json` no lo piden.
- Go, para el entrenador de L0 y para compilar `chispa-server`. Sin Go, `chispa train` escribe META + L1 + CALIB y no lleva L0.
- Para `--conjunta`: torch y transformers, un checkpoint de L2 y e5 (ver el paso 3).
- Los comandos de Python se corren con `PYTHONPATH=sdk/python`, o tras `pip install ./sdk/python`.

## 1. Los ejemplos
Un fichero por pregunta. CSV con cabecera, o JSONL, con columnas `texto` (o `text`) y `etiqueta` (o `label`).
Cada etiqueta debe ser una opción del esquema.

```
texto,etiqueta
"quiero comprar dos camisetas",compra
"mi pedido no ha llegado",soporte
```

Con 50 ejemplos por clase, el recorrido medido está en [`sdk/python/README.md`](../sdk/python/README.md#punta-a-punta-intención-del-sondeo-50-por-clase).

## 2. El esquema
JSON o YAML con `id`, `pregunta`, `tipo` (`choice`, `noul` o `score`) y `opciones` (mapa id → descripción).

```json
{"id": "intencion", "pregunta": "¿Qué quiere hacer la persona?", "tipo": "choice",
 "opciones": {"compra": "quiere comprar", "soporte": "tiene un problema con un pedido"}}
```

Opcionales: `licencias` y `dorado`, que van a META. Si el fichero trae varias preguntas, elige una con `--pregunta`.
Un `.chispa` por pregunta: el servidor elige L0 por el conjunto de etiquetas.

## 3. Entrenar con `chispa train`
Sin L2 (L0 y, si quieres, L1):

```
PYTHONPATH=sdk/python python -m chispa train --ejemplos ejemplos.csv --esquema esquema.json --salida intencion.chispa [--l1 potion.chispa-l1]
```

`--l1` es el potion que exporta `python runtime/l1/exportar.py` (155 MB por fichero).

Con la cabeza conjunta (L0TF + L2c), que es la configuración medida en [07](07-rendimiento-y-limites.md):

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

## 4. Servir
```
cd server && go build -o chispa-server ./cmd/chispa-server
./chispa-server -addr 127.0.0.1:8090 -modelo ../intencion.chispa
```

Con L2 o L2c hacen falta además `-tags ort`, ONNX Runtime y el tokenizador (`-tok`). Ver [06-despliegue.md](06-despliegue.md).
Sin ellos, el servidor arranca y L2 queda en stub, con un aviso en el log. El resto de capas responde.

Flags de [`server/cmd/chispa-server/main.go`](../server/cmd/chispa-server/main.go): `-addr`, `-config`, `-modelo`, `-tok`.

Sin Go instalado en el servidor, usa la imagen OCI ([06-despliegue.md](06-despliegue.md)).

## 5. Una petición
```
curl -s localhost:8090/healthz
curl -s localhost:8090/v1/decide -d '{"state":"quiero comprar dos camisetas","questions":[{"id":"u1","question":"¿Qué quiere hacer la persona?","kind":"choice","options":[{"id":"compra","description":"quiere comprar"},{"id":"soporte","description":"tiene un problema con un pedido"}]}]}'
```

El `question` y los ids deben ser los del esquema de entrenamiento. L0 elige modelo por el conjunto de ids. L2c usa también la pregunta.

Respuesta: ver [03-api.md](03-api.md).

## Desde Python
```python
from chispa import Chispa, Choice
rs = Chispa("http://127.0.0.1:8090").decidir("quiero comprar dos camisetas",
    [Choice("u1", "¿Qué quiere hacer la persona?", [("compra", "quiere comprar"), ("soporte", "tiene un problema con un pedido")])])
```
