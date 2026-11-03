# Chispa: Caída

Juego original de bloques que caen, hecho para ver cómo decide Chispa en tiempo real en una tarea ajena a su dominio.
No es un clon de Tetris: piezas, regla de chispa, colores y nombre son propios.

Python ≥ 3.9. Todo es biblioteca estándar salvo el vídeo (Pillow + ffmpeg, solo en `renderizar`).

## Reglas

- Tablero **9 × 15** (9 columnas, 15 filas). Cada turno llega una pieza; se elige giro (90°) y columna y cae de golpe (caída instantánea).
- Una colocación es válida si la pieza cabe al aparecer arriba en esa columna. **Game over** cuando no hay ninguna colocación válida.
- Fila llena → se borra. **Regla de chispa:** algunas celdas (≈ 3 de cada 10 piezas llevan una) son «chispa». Si una fila que se limpia contiene una celda chispa, se borra también **toda su columna**.
- **Gravedad tras borrar:** las filas borradas se quitan y todo lo de arriba baja tantas filas como filas borradas haya debajo (apilado normal). Una columna borrada queda vacía y no necesita gravedad. No hay cascadas: la caída no cambia el contenido de ninguna fila.
- Puntos: 10 por pieza, `100 × filas²` por limpieza y 10 por cada celda borrada por la regla de chispa fuera de las filas limpiadas.
- La secuencia de piezas depende solo de la semilla (no del agente): dos corridas con la misma semilla y las mismas jugadas son idénticas.

## Piezas (7, de 2 a 4 celdas)

| nombre | celdas | forma (fila, columna) |
|---|---|---|
| domino | 2 | (0,0) (0,1) |
| diagonal | 2 | (0,0) (1,1) |
| recta3 | 3 | (0,0) (0,1) (0,2) |
| ele3 | 3 | (0,0) (1,0) (1,1) |
| pinza | 4 | (0,0) (0,2) (1,0) (1,2): dos dominós verticales con una columna libre en medio |
| punta | 4 | (0,0) (1,0) (2,0) (2,2): tres en vertical y una celda suelta a dos columnas |
| gancho | 4 | (0,0) (0,1) (1,3) (1,4): dos dominós horizontales que no se tocan |

Las formas de 4 celdas unidas por lados son todas las clásicas; por eso las de 4 celdas de este juego **no están unidas por lados**
(un test lo comprueba para todos los giros). Cada giro distinto cuenta una vez.

## Agentes

- **aleatorio**: colocación válida al azar (semilla propia).
- **profesor**: heurístico con pesos fijos (`caida/agentes.py`, `PESOS`) sobre el tablero resultante: `+8` por fila limpiada, `+0,4` por celda borrada por chispa, `−6` por hueco (celda vacía con algo encima), `−1` por altura máxima, `−0,35` por altura total, `−0,8` por rugosidad (suma de |h[i]−h[i+1]|). Desempate: giro y columna menores.
- **chispa**: cada turno **dos** peticiones a `POST /v1/decide` (`state` es uno por petición; contrato: `docs/03-api.md`, `server/api/openapi.yaml`, cliente en `sdk/python/chispa/cliente.py`):
  - `colocacion` (`choice`, «¿Dónde coloco la pieza?»): las **6** mejores colocaciones del profesor, ids `1`…`6` (la `1` es la mejor), cada descripción con sus consecuencias («limpia 1 fila, deja 0 huecos, altura máxima 5»).
  - `riesgo` (`score`, ids `1`…`5`): riesgo de quedarse sin salida.
  - `completa` (`noul`): ¿esta pieza puede completar una fila?
  - Si Chispa escala (`escalate: true`), no opina o la red falla, juega el profesor y cuenta como **intervención del escudo** (`escalate_reason` queda en la traza; un error de red cuenta aparte en `errores_red`).

El `state` es texto y sale de `caida/estado.py:texto_pregunta`, la misma función que usa `entrenar_fewshot` para los ejemplos: `colocacion` lleva tablero (ASCII: `.` vacío, `#` bloque, `*` chispa), alturas, huecos, pieza **y la lista de opciones**; `riesgo` y `completa` (segunda petición) llevan solo tablero y pieza.

**Orden de las opciones:** se ofrecen **barajadas** con la semilla de la partida (la `1` ya no es la del profesor); cada opción de la traza lleva su `rank` (puesto del profesor, 1 = la mejor) y su `rot`/`col` reales. «Siempre la 1» coincide como un azar entre 6 (≈ 0,167).

**`--decidir argmax|tau`** (por defecto `tau`, el comportamiento de siempre): con `tau`, si Chispa escala juega el profesor (escudo). Con `argmax`, si el choice trae `probs` válidas se juega su argmax aunque escale; solo sin `probs` (o inválidas) juega el profesor. Cada turno anota `decidio`: `chispa_tau` (no escaló), `chispa_bajo_tau` (escaló pero se jugó su argmax) o `escudo`. El evaluador y su tabla separan las tres cifras y la coincidencia con el profesor de cada una; el vídeo muestra «bajo τ: el servidor escalaría» en esos turnos y el modo en una esquina. El τ del servidor no se toca.

## Los comandos

Desde `demos/caida/` (o con `PYTHONPATH=demos/caida`):

| comando | qué hace |
|---|---|
| `python3 -m caida.jugar --url URL --salida traza.jsonl [--semilla N --max-piezas N --decidir argmax|tau]` | Juega una partida de Chispa y escribe la **traza** JSONL. Solo biblioteca estándar. |
| `python3 -m caida.renderizar --traza traza.jsonl --salida partida.mp4` | Traza → MP4 1080p/30 fps. Necesita Pillow y ffmpeg; sin ellos sale con código 3 y avisa. |
| `python3 -m caida.entrenar_fewshot --salida dir/ --n 60 …` | Genera los ejemplos few-shot, los esquemas y `entrenar.sh`. |
| `python3 -m caida.medir --url URL --salida dir/ [--n 100 --decidir argmax|tau]` | Latencia p50/p95/p99 por decisión (2 peticiones, 3 preguntas) con caché de torres fría y caliente, y decisiones/s. |
| `python3 -m caida.evaluar --url URL [--url-fewshot URL2] --salida dir/ [--decidir argmax|tau]` | 20 partidas con semillas 1…20 por agente (aleatorio, profesor, Chispa zero-shot, Chispa few-shot). |
| `python3 -m caida.servidor_falso --modo primera\|escalar\|aleatorio\|escalar_probs\|escalar_probs_ciego --puerto 8099` | Servidor HTTP falso con la forma de `/v1/decide` (sin modelos). |
| `demos/caida/correr.sh --url URL --salida dir/ [--decidir argmax|tau]` | `jugar` + `medir` + `evaluar` y, si hay Pillow y ffmpeg, `renderizar`. Si faltan, lo dice y se salta solo el vídeo. |
| `demos/caida/empaquetar.sh [dir]` | `chispa-server` linux/amd64 (`-tags ort`) + `libonnxruntime.so` (la de `CHISPA_ORT_LIB`) + `bin/chispa-entrenador` (el entrenador de Go, linux/amd64) + `sdk/python/chispa` + `demos/caida` en un tar.gz fuera del repo. |

Zero-shot y few-shot son dos servidores distintos: `evaluar` y `correr.sh` usan `--url` para zero-shot y `--url-fewshot` (por defecto, el mismo `--url`) para few-shot.

### La traza (`traza.jsonl`)

Una cabecera (`semilla`, `url`…) y una línea por turno con: `tablero` (antes de colocar), `pieza`, `estado` enviado, `opciones` con descripciones y celdas,
`preguntas` (por cada una: `answer`, `probs`, `layer`, `escalate`, `escalate_reason`, `ms_servidor`), `elegida`, `rot`/`col`, `decidio`, `escudo` y su `motivo_escudo`,
`ms_cliente` (medida en el cliente) y `ms_servidor` (suma de lo que reporta el servidor), `filas`, `puntos`. La partida se reproduce **sin modelo**
con `caida.traza.reproducir(ruta)` (motor + semilla + jugadas, y comprueba que cada tablero coincide).

### Cómo leer el vídeo

A la izquierda, el tablero (la pieza cae a su sitio; si limpia, destellan las columnas borradas por chispa; la celda con estrella ámbar es chispa).
A la derecha, el panel de ese turno (`caida/panel.py`, cálculo puro):

- **Jugada elegida** (opción, columna y giro; «escudo» si jugó el profesor).
- **Barras de probabilidad** de las 6 opciones (la elegida, en verde menta).
- **Riesgo** 1–5 y su distribución; **¿completa fila?** sí/no con la probabilidad de «sí».
- **Capa** que decidió el choice: L0, L1, L2 o escalar (resaltada).
- **Latencia** de la petición en ms y **decisiones/s** (decisiones acumuladas ÷ tiempo acumulado de espera).
- **Escudo**: intervenciones acumuladas sobre decisiones acumuladas. **Puntos** y filas.

Para renderizar: `pip install -r requirements-render.txt` (Pillow e `imageio-ffmpeg`, que trae su propio ffmpeg; se usa el del `PATH` si existe).

## Entrenar el `.chispa` few-shot

`chispa train` hace un `.chispa` por pregunta. `entrenar_fewshot` genera, de partidas del profesor (con `--ruido` de jugadas al azar para llegar a tableros altos; las etiquetas siguen siendo las del profesor), `N` ejemplos por pregunta
(JSONL con `texto` y `etiqueta`, repartidos por igual entre clases):

- `colocacion`: etiqueta = id (1…6) de la jugada del profesor. En vivo el profesor es siempre la opción 1, así que en los ejemplos la lista se **baraja** y se renumera (como en vivo), y el texto lista las opciones en ese orden; si no, todas las etiquetas serían `1` y `chispa train` no puede entrenar.
- `riesgo`: nivel 1–5 por la altura máxima antes de colocar (≤4 → 1, 5–7 → 2, 8–10 → 3, 11–12 → 4, ≥13 → 5).
- `completa`: `true` si alguna colocación de la pieza limpia al menos una fila, si no `false`.

```
python3 -m caida.entrenar_fewshot --salida /tmp/fs --n 60 --l1 potion.chispa-l1 --l2 servidor.chispa --torre torre.onnx
bash /tmp/fs/entrenar.sh        # desde la raíz del repositorio
```

Que equivale, por pregunta (`<q>` ∈ `colocacion`, `riesgo`, `completa`), a este comando exacto (sin `--conjunta`: L0/L1 con ejemplos, L2 zero-shot con torre al vuelo, sin torch):

```
PYTHONPATH=sdk/python python -m chispa train --ejemplos /tmp/fs/ejemplos-<q>.jsonl --esquema /tmp/fs/esquema-<q>.json \
  --l1 potion.chispa-l1 --l2 servidor.chispa --torre torre.onnx --salida /tmp/fs/<q>.chispa
```

Con `N ≥ 60` hay ≥ 10 ejemplos por opción en `colocacion` y se entrena también L0; con menos, L0 no se entrena y L1 se calibra con los ejemplos (lo avisa `chispa train`).
Para servir las tres preguntas few-shot a la vez junto a un L2 de servidor, ver la receta de abajo («Las tres preguntas en un solo servidor»). Para una sola, sirve el `.chispa` con `chispa-server -modelo … -tok e5.chispa-tok` (compilado con `-tags ort`, ver `docs/06-despliegue.md`); un servidor lleva un `.chispa`, así que el few-shot de una pregunta
no cambia las otras dos, que se deciden con L1 y la torre al vuelo del esquema de la petición.

### Las tres preguntas en un solo servidor

Entrena cada pregunta solo con L0 (sin `--l2` ni `--torre`) y sirve el `.chispa` de servidor aparte:

```
chispa-server -modelo servidor.chispa -tok e5.chispa-tok -config config.json
# config.json: {"modelos": ["colocacion.chispa", "riesgo.chispa", "completa.chispa"]}
```

**La calibración es la del `-modelo`**: de cada `.chispa` de `modelos` solo se usa su L0 (L0TF); CALIB, SOPL1 y demás se ignoran con un aviso al arrancar, y si traen L1, L2 o TORR el arranque falla.
L0 se elige por el conjunto de ids de las opciones: `colocacion` (choice 1…6), `riesgo` (score 1…5) y `completa` (noul, ids `false`/`true`) no chocan. Dos L0 con las mismas etiquetas hacen fallar el arranque. Detalle: `docs/06-despliegue.md`.

## Tests

`python3 -m pytest demos/caida` (o, sin pytest, `python3 -m unittest discover -s demos/caida/tests -t demos/caida`): determinismo por semilla, regla de chispa, piezas propias,
forma exacta de la petición, escudo, datos few-shot (incluye leerlos con el cargador de `sdk/python`), evaluador, medidor y panel contra el servidor falso, traza reproducible.
Los tests de dibujo se saltan sin Pillow.

## Entrenar sin Go en el destino

`chispa train` compila el entrenador de Go con `go build`. Si el destino (Linux amd64) no tiene Go, el tar de `empaquetar.sh` trae el binario
`bin/chispa-entrenador` y el SDK en `sdk/python`; se le indica con la variable `CHISPA_ENTRENADOR`:

```
export CHISPA_ENTRENADOR="$PWD/bin/chispa-entrenador"
PYTHONPATH=sdk/python python3 -m chispa train --ejemplos … --esquema … --salida x.chispa
```

Sin la variable, todo sigue como antes (Go + fuentes del repositorio). Las órdenes que además necesitan Go (`--conjunta`, `--ckpt`) no usan el binario.
