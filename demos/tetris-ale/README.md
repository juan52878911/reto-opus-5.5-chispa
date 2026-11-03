# Tetris ALE — parte sin emulador (W16)

Demo de `ALE/Tetris-v5` (`frameskip=1`, `repeat_action_probability=0`, semillas fijas) en la que **Chispa elige la colocación de
cada pieza** y un controlador fijo pulsa los botones. Aquí está todo lo que no necesita el emulador: simulador, rasgos, maestro,
opciones autodescriptivas, agentes, `evaluar` y los datos de imitación. La percepción y el controlador (con `ale-py`) son otra
pieza; su interfaz está en `tetris_ale/interfaces.py`. Python 3.11, **solo biblioteca estándar** (nada de torch aquí).

## Reglas del simulador (`motor.py`)
- Tablero de 10 × 20: tupla de 20 enteros, fila 0 abajo, bit `c` = columna `c`. Las 7 piezas con sus giros distintos
  (O 1; I, S, Z 2; T, L, J 4). Giro 0 = forma de reposo; cada giro siguiente es un cuarto de vuelta horario.
- Colocación = `(giro, columna)` (columna de la izquierda de la caja de la pieza), con caída directa desde arriba: es legal si la
  pieza cabe al aparecer y baja en línea recta. Unas 34 para T/L/J, 17 para I/S/Z, 9 para O en tablero vacío.
- `aplicar(tablero, colocacion)` → `Efecto(tablero, lineas, celdas_erosionadas, terminado)`; no muta. La partida termina si, tras
  borrar líneas, queda alguna celda en las dos filas de arriba, o si no hay colocación legal.
- Piezas uniformes y deterministas por semilla (`Juego(semilla)`, con `pieza` y `siguiente`).

## Rasgos (`rasgos.py`) y maestro (`maestro.py`)
Altura de aterrizaje, líneas, celdas erosionadas, transiciones de fila y de columna, huecos (y su variación), pozos acumulados,
altura agregada y máxima, irregularidad (bumpiness); definiciones exactas en la cabecera del módulo, cada una con test sobre
tableros pequeños calculados a mano.
- **Dellacherie** (por defecto): −aterrizaje + erosionadas − trans. fila − trans. columna − 4·huecos − pozos (Fahey; Thiery y Scherrer 2009).
- **El-Tetris** (alternativa): pesos de Yiyuan Lee (2013) sobre altura total, líneas, huecos e irregularidad.
- Desempate: mayor valor, luego menor giro, luego menor columna.
- **Veto de seguridad:** se descarta toda colocación que termina la partida si hay alternativa. Lo aplican todos los agentes
  (también el aleatorio) y las opciones que se ofrecen a Chispa.

## Opciones autodescriptivas (`opciones.py`)
Una sola pregunta `choice` por pieza: las 5 mejores del maestro más 2 al azar (semilla), barajadas, ids `1`…`7`.
La descripción lleva los rasgos ya calculados: «limpia 1 línea, huecos +0, altura 7, irregularidad 4, pozos 2, aterriza a 3»
(«no limpia líneas» si no limpia; `huecos` es la variación; `altura` la máxima resultante). El estado es breve:
«Pieza T, siguiente L. Tablero: altura 7, huecos 3.». La decisión la llevan los rasgos de cada opción, no el tablero.
Caveat: dos colocaciones con los mismos rasgos tienen la misma descripción (p. ej. simetrías); el maestro las desempata por
(giro, columna) y eso no se puede deducir del texto, así que la coincidencia máxima alcanzable es algo menor que 1.

## Agentes (`partida.py`)
- `aleatorio`: colocación legal al azar (tras el veto). `maestro` / `el-tetris`: la mejor según su peso.
- `chispa`: `POST /v1/decide` con una pregunta `choice` por turno. `--decidir tau` (por defecto): si Chispa escala, no opina o la red
  falla, juega el maestro y cuenta como **escudo**. `--decidir argmax`: con `probs` válidas se juega su argmax aunque escale
  (`chispa_bajo_tau`); sin ellas o sin red, el maestro.
- `servidor_falso.py` (para tests): modos `primera`, `escalar`, `aleatorio`, `escalar_probs`, `escalar_probs_ciego` y `rasgos`
  (elige leyendo solo las descripciones).

## Comandos (desde `demos/tetris-ale/`)
    python -m unittest discover -s demos/tetris-ale        # desde la raíz del repo; ~35 s
    python -m tetris_ale evaluar --salida OUT              # aleatorio, maestro y el-tetris, 20 semillas, tope 500 piezas
    python -m tetris_ale evaluar --salida OUT --url http://HOST:PUERTO [--decidir argmax]   # añade chispa
    python -m tetris_ale generar --salida DATOS [--n 16000] [--ruido 0.3] [--temperatura 1.0]
    python -m tetris_ale.servidor_falso --modo rasgos --puerto 8099

`evaluar` escribe `evaluacion.json` y `evaluacion.md`: líneas por partida (la principal), piezas, coincidencia con el maestro,
% bajo τ y p50/p99 de latencia. La tabla del simulador está en `resultados-sim.md`: maestro 194,0 líneas de media frente a 0,05 del
aleatorio (20 semillas, 500 piezas).

## Datos de imitación (`generar`)
16 000 decisiones en ~55 s de CPU (un solo hilo). Se juegan partidas del maestro; con probabilidad `--ruido` (0,3) se juega una opción
al azar para llegar a tableros malos, pero la etiqueta es siempre la del maestro. Una de cada 10 partidas es `dev` (sin fugas).
- `filas.jsonl`: esquema de filas de Chispa (`model/esquema.md`), tipo `choice`, con `texto` (estado), `opciones`, `descripciones`
  (propias de cada turno), `etiqueta` (la opción del maestro).
- `blandas.jsonl`: aparte, `{id, blanda}` con softmax(valor/T), T = 1 por defecto.
- No se commitea el conjunto; `fixtures/muestra-*.jsonl` son 50 filas de muestra.

### Camino de ajuste propuesto (no entrenado)
Investigado sin entrenar:
- **`chispa train`** (`sdk/python/chispa/train.py`) toma **un esquema fijo** (opciones y descripciones únicas) y ejemplos
  `texto,etiqueta`: sirve para L0/L1 con opciones estables. Aquí las descripciones cambian en cada turno, así que descarta.
  Con `--ckpt`/`--l2` solo arma el `.chispa` con torre al vuelo; no ajusta pesos.
- **`model/l2/entrenar.py`** sí: sus filas llevan `descripciones` **por fila** y `blanda` (KL), y la torre de opción se calcula
  al vuelo con el texto `pregunta · descripción`. `--desde CKPT` es el ajuste fino (lr 3e-5 / 1e-5, pocos pasos) de las ranuras y
  la torre sobre e5 congelado. **Es el camino elegido.** Las `blandas` van por `--maestro-extra` porque `--blandas` espera filas
  completas del maestro de T1.6 (con `--peso-extra 1`, o sin `blanda` previa, queda la extra).

Comando exacto (desde la raíz del repo, tras `generar --salida DATOS`):

    python -m model.l2.entrenar --salida CKPT_TETRIS --datos DATOS/filas.jsonl --maestro-extra DATOS/blandas.jsonl \
        --peso-extra 1.0 --desde CKPT_BASE/mejor.pt --pasos 300 --lote 64 --texto-torre v2_sin_id

Requisitos: **torch** (y numpy, transformers y e5 en `HF_HOME`); sin GPU funciona en CPU (`--device cpu`, se elige solo), pero el
codificador congelado hace lenta cada época (16k filas × 7 opciones ≈ 112k pasajes únicos; la caché de vectores por hash ayuda
porque muchas descripciones se repiten). Para ajuste real, una GPU pequeña. `--texto-torre` debe coincidir con el del checkpoint
base. Después, calibrar y exportar con `model.l2.calibrar` / `model.l2.exportar` (ver `model/l2/README.md`). Tras ajustar, medir
con `evaluar --url`: la coincidencia debe subir del azar (~0,14–0,3) hacia el 0,75 publicado.
Pendiente de confirmar al entrenar: que las 7 opciones por fila no excedan `K` de las ranuras (K = 16) ni el límite de tokens.

## Para la parte ALE (`interfaces.py`)
`Percepcion.leer(obs) → (tablero, pieza, siguiente)` y `Controlador.acciones(colocacion, obs) → [acciones]`, abstractas y sin
implementar. Faltan: leer el tablero y la pieza de la RAM o los píxeles, mapear `giro`/`col` a los giros y desplazamientos de Atari,
verificar que el simulador y el juego real coinciden (reglas de fin de partida, orden de las piezas), y el bucle con `ale-py`.
