# Inicio rápido

De un esquema nuevo a una petición `curl`. Los comandos se escriben desde la raíz del repositorio.

Ejemplo de esta página: clasificar solicitudes que llegan a una ferretería colombiana. Es un esquema inventado; no es
ninguna tarea de prueba.

## Requisitos
- Python ≥ 3.9 para `chispa train` ([`pyproject.toml`](../sdk/python/pyproject.toml)). Esquemas `.yaml`: instala PyYAML. Los `.json` no lo piden.
- Un potion exportado con `python runtime/l1/exportar.py` (`potion.chispa-l1`, 155 MB). Sin `--l1` ni `--l2`/`--ckpt`, el zero-shot falla: no habría ninguna capa.
- Go, para el entrenador de L0 y para compilar `chispa-server`. Sin Go, `chispa train` escribe META + L1 + CALIB y no lleva L0.
- Solo para el modo avanzado (`--conjunta`): torch y transformers, un checkpoint de L2 y e5.
- Los comandos de Python se corren con `PYTHONPATH=sdk/python`, o tras `pip install ./sdk/python`.

## 1. El esquema
JSON o YAML con `id`, `pregunta`, `tipo` (`choice`, `noul` o `score`) y `opciones` (mapa id → descripción).
Guarda esto como `ferreteria.yaml`:

```yaml
id: solicitud
pregunta: ¿Qué necesita la persona que escribe a la ferretería?
tipo: choice
opciones:
  cotizacion: pide precio o disponibilidad de un producto, o una cotización de materiales
  pedido: quiere comprar y recibir productos, o pregunta por el estado de un pedido ya hecho
  garantia: reclama por una herramienta defectuosa, un cambio o una devolución
  asesoria: pide ayuda técnica para elegir o usar un material o una herramienta
  factura: pide una factura, un RUT o corregir datos de facturación
```

Escribe las descripciones con cuidado: en zero-shot son lo único que Chispa ve de tu tarea.
Cada descripción debe distinguir su opción de las demás. Opcionales: `licencias` y `dorado`, que van a META.
Si el fichero trae varias preguntas, elige una con `--pregunta`.

## 2. Zero-shot: sin ejemplos
```
PYTHONPATH=sdk/python python -m chispa train --esquema ferreteria.yaml --salida ferreteria.chispa --l1 potion.chispa-l1
```

El `.chispa` trae META, L1 y un `CALIB` sin calibrar con τ = 0,6. No lleva L0. Con `--l2 l2.chispa` o `--ckpt mejor.pt` añade también L2 y ESQUEMAS.

Sirve:
```
cd server && go build -o chispa-server ./cmd/chispa-server
./chispa-server -addr 127.0.0.1:8090 -modelo ../ferreteria.chispa
```

Pregunta:
```
curl -s localhost:8090/v1/decide -d '{"state":"Buenas, ¿cuánto vale el bulto de cemento gris de 50 kg y tienen hoy?","questions":[{"id":"q1","question":"¿Qué necesita la persona que escribe a la ferretería?","kind":"choice","options":[{"id":"cotizacion","description":"pide precio o disponibilidad de un producto, o una cotización de materiales"},{"id":"pedido","description":"quiere comprar y recibir productos, o pregunta por el estado de un pedido ya hecho"},{"id":"garantia","description":"reclama por una herramienta defectuosa, un cambio o una devolución"},{"id":"asesoria","description":"pide ayuda técnica para elegir o usar un material o una herramienta"},{"id":"factura","description":"pide una factura, un RUT o corregir datos de facturación"}]}]}'
```

El esquema viaja en la petición: la pregunta, los ids y las descripciones. El servidor decide con L1 aunque ningún `.chispa` traiga
esa pregunta. Respuesta (la forma; los valores cambian con tu modelo):

```json
{"results": [{"id": "q1", "kind": "choice", "answer": "<id de una opción>",
  "probs": {"cotizacion": 0.0, "pedido": 0.0, "garantia": 0.0, "asesoria": 0.0, "factura": 0.0},
  "layer": "L1", "escalate": false, "ms": 0}]}
```

- `probs` trae un valor por opción, y `answer` es una de ellas.
- Si L1 no llega a τ = 0,6, la respuesta trae `"escalate": true`: `answer` es la mejor pista. Decide tú qué hacer.
- Con un `.chispa` que trae la sección `TORR` y `chispa-server -tok …` compilado con `-tags ort`, un esquema nuevo lo decide también L2 (torre al vuelo); sin `TORR`, solo L1 ([08-esquemas-nuevos.md](08-esquemas-nuevos.md)). `chispa train --torre torre.onnx` (con `--torre-dim`, `--torre-max-len`, `--torre-prefijo` opcionales) añade la sección desde un ONNX que cumpla el contrato. Sin paridad ni cifra medidas del ONNX real de la torre: sin medir.
- Límite: L1 sin ejemplos es flojo. Cifras en [07-rendimiento-y-limites.md](07-rendimiento-y-limites.md#zero-shot).

## 3. Few-shot: k ejemplos por opción
Un fichero por pregunta. CSV con cabecera, o JSONL, con columnas `texto` (o `text`) y `etiqueta` (o `label`).
Cada etiqueta debe ser una opción del esquema y cada opción necesita al menos un ejemplo. Guarda esto como `ejemplos.csv`
(k = 5 por opción):

```
texto,etiqueta
"¿Cuánto vale el galón de pintura blanca de tres años?",cotizacion
"Necesito cotizar 20 láminas de drywall y perfiles",cotizacion
"¿Tienen disponible taladro percutor de media pulgada?",cotizacion
"Me pasa el precio por mayor de la varilla de 3/8",cotizacion
"¿A cómo está el metro de manguera para jardín?",cotizacion
"Quiero comprar dos cajas de tornillos y que me las envíen a Soacha",pedido
"Hice un pedido el lunes y todavía no llega",pedido
"Quiero pagar y recibir en casa las baldosas que cotizamos",pedido
"¿En qué va mi pedido 4587?",pedido
"Confirmo la compra de cinco bultos de cemento para mañana",pedido
"El taladro que compré dejó de funcionar a los tres días",garantia
"Quiero devolver el martillo, vino con el mango roto",garantia
"Me llegó una sierra distinta a la que pedí y quiero cambiarla",garantia
"La garantía de la pulidora aún está vigente, ¿cómo la hago valer?",garantia
"Compré una escalera y está torcida, necesito el reembolso",garantia
"¿Qué broca sirve para perforar concreto sin que se parta?",asesoria
"¿Cuántos bultos de cemento necesito para una placa de 20 metros?",asesoria
"No sé si usar silicona o sellante para el baño",asesoria
"¿Qué diferencia hay entre pintura vinilo y esmalte?",asesoria
"¿Cómo instalo una llave de lavamanos sin cambiar la tubería?",asesoria
"Necesito la factura electrónica de mi compra del viernes",factura
"Me pueden mandar el RUT de la ferretería",factura
"La factura salió a nombre equivocado, hay que corregir el NIT",factura
"Pido factura a nombre de mi empresa para la compra de ayer",factura
"No me llegó la factura al correo",factura
```

Entrena sin `--conjunta`:

```
PYTHONPATH=sdk/python python -m chispa train --ejemplos ejemplos.csv --esquema ferreteria.yaml --salida ferreteria-fs.chispa --l1 potion.chispa-l1
```

Con k = 5 (< 10 en alguna opción), `chispa train` no entrena L0 y calibra L1 con los 25 ejemplos; lo avisa por stderr.
Con 10 o más ejemplos en cada opción entrena también L0.
La misma petición `curl` del paso 2, contra `ferreteria-fs.chispa`, devuelve la misma forma de respuesta.
La calibración de L1 con 25 ejemplos es ruidosa: pon aparte unas decenas de casos reales y mide antes de producción.

## 4. Con datos del cliente: `--conjunta` (modo avanzado)
Con la cabeza conjunta (L0TF + L2c). Necesita train etiquetado de tu tarea: **al menos 20 ejemplos por opción**. Con menos,
`chispa train` avisa por stderr y cae a few-shot.

```
PYTHONPATH=sdk/python python -m chispa train --ejemplos ejemplos.csv --esquema ferreteria.yaml --salida ferreteria-conj.chispa \
  --ckpt mejor.pt --l2 l2.chispa --conjunta --repo .
```

- `--ckpt`: el checkpoint de L2 (e5 con ranuras y torres). **El repositorio no trae ninguno.** Se entrena con `python -m model.l2.entrenar`
  ([`model/l2/README.md`](../model/l2/README.md#uso)).
- `--l2`: el `.chispa` con L2 y ESQUEMAS que sale de `python -m model.l2.calibrar` y `python -m model.l2.exportar`.
  Sin `--l2`, `--ckpt` calibra y exporta por ti.
- `--repo`: la raíz del repositorio. También vale `CHISPA_REPO`.
- `--torre <onnx>`: añade `TORR` también aquí (y en zero-shot y few-shot); detalle en [08-esquemas-nuevos.md](08-esquemas-nuevos.md).
- `--conjunta` solo sirve para `choice`. Escribe `CONJ`, `L0TF` y `tau_l2c` en `CALIB`.
- Topes: `--l0-max-mb` y `--l0tf-max-mb` (48 por defecto). `--precision-objetivo` (0,95) fija el τ de L2c.
- `--validacion` (CSV/JSONL fuera de `--ejemplos`) fija el τ de L2c sobre esas filas.

Cada flag está definido en [`sdk/python/chispa/cli.py`](../sdk/python/chispa/cli.py). Con L2 o L2c, el servidor necesita además
`-tags ort`, ONNX Runtime y el tokenizador (`-tok`): [06-despliegue.md](06-despliegue.md). Sin ellos arranca y L2 queda en stub, con un aviso
en el log. En este modo, la pregunta y los ids de la petición deben ser los del esquema de entrenamiento: L0 elige modelo por el conjunto de ids,
y L2 y L2c usan también la pregunta.

Flags del servidor ([`main.go`](../server/cmd/chispa-server/main.go)): `-addr`, `-config`, `-modelo`, `-tok`.
Sin Go instalado en el servidor, usa la imagen OCI ([06-despliegue.md](06-despliegue.md)).

## Desde Python
```python
from chispa import Chispa, Choice
ops = [("cotizacion", "pide precio o disponibilidad de un producto, o una cotización de materiales"),
       ("pedido", "quiere comprar y recibir productos, o pregunta por el estado de un pedido ya hecho"),
       ("garantia", "reclama por una herramienta defectuosa, un cambio o una devolución"),
       ("asesoria", "pide ayuda técnica para elegir o usar un material o una herramienta"),
       ("factura", "pide una factura, un RUT o corregir datos de facturación")]
rs = Chispa("http://127.0.0.1:8090").decidir("Buenas, ¿cuánto vale el bulto de cemento gris de 50 kg y tienen hoy?",
    [Choice("q1", "¿Qué necesita la persona que escribe a la ferretería?", ops)])
rs[0].answer, rs[0].probs, rs[0].layer, rs[0].escalate
```
