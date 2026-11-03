# W16 Tetris ALE, parte sin emulador: simulador de colocaciones, rasgos, maestro, opciones autodescriptivas y datos de imitación

## Antecedentes
- **Juan pidió una demo de Tetris en ALE** (`ALE/Tetris-v5`, `frameskip=1`, `repeat_action_probability=0`, semillas fijas).
  Chispa elige la colocación de cada pieza y un controlador fijo pulsa los botones. Todo el código va en `demos/tetris-ale/`.
- **`ale-py` todavía no está autorizado** en el servidor. Esta pieza hace **todo lo que no necesita el emulador**; la
  percepción (RAM o píxeles → tablero) y el controlador irán en otra pieza.
- **Lo publicado** (Laya y Jev): nadie juega en zero-shot sobre el tablero crudo. El juego enumera unas pocas colocaciones
  legales con sus rasgos ya calculados y el clasificador elige entre ellas. Ajustar por imitación del maestro (unas 16k
  decisiones) sube la precisión de ~0,3 a ~0,75.
- **Referencia de estructura:** `demos/caida/` y `demos/serpiente/` (solo lectura).
  - Ahí están el cliente de `POST /v1/decide`, `--decidir argmax|tau`, el servidor falso para tests, `evaluar` y la traza JSONL.
  - Léelas y reutiliza su forma, pero **sin importar nada de ellas**: las demos son independientes.
  - Contrato de la API: `docs/03-api.md` y `server/api/openapi.yaml`.
- **Entorno:** Python 3.11 **solo con biblioteca estándar** en el paquete. **Nada de torch** en el servidor CT.

## Qué construir (`demos/tetris-ale/`, paquete `tetris_ale`)
1. **Simulador de planificación**:
   - tablero de 10 × 20 y los 7 tetrominós estándar con sus giros distintos;
   - `colocaciones(tablero, pieza)` → todas las (giro, columna) legales con caída directa (unas 34 para la mayoría de piezas);
   - `aplicar` devuelve el tablero nuevo, las líneas borradas y si la partida termina;
   - secuencia de piezas determinista por semilla.

   Que el giro y la columna sean parámetros limpios, para poder mapearlos luego a los giros de Atari.
2. **Rasgos por colocación** (Dellacherie / El-Tetris):
   - altura de aterrizaje;
   - líneas, celdas erosionadas;
   - transiciones de fila y de columna;
   - huecos (y su variación);
   - pozos acumulados;
   - altura agregada y máxima;
   - bumpiness.

   Cada rasgo con un test sobre tableros pequeños calculados a mano.
3. **Maestro**:
   - con los pesos publicados de Dellacherie (y El-Tetris como alternativa, con la fuente de los pesos citada en un comentario);
   - desempate determinista.
   - **Veto de seguridad:** se descarta toda colocación que termina la partida si hay alternativa. Lo usan todos los agentes.
4. **Opciones autodescriptivas** (una sola pregunta `choice` por pieza):
   - las K = 5 mejores según el maestro, más 2 al azar (semilla), barajadas, con ids `1`…`7`;
   - cada descripción es un texto en español con los rasgos ya calculados, p. ej. «limpia 1 línea, huecos +0, altura 7,
     irregularidad 4, pozos 2»;
   - el texto de estado es breve (pieza actual, siguiente si se conoce, altura y huecos del tablero).

   La decisión la llevan los rasgos de cada opción, no el tablero.
5. **Agentes**:
   - aleatorio (colocación legal);
   - maestro;
   - Chispa (cliente HTTP a `/v1/decide` con `--decidir argmax|tau`). Si Chispa escala o falla la red, juega el maestro y
     cuenta como escudo, igual que en Caída.
6. **`evaluar`** en el simulador: N partidas por agente con tope de piezas.
   - Métricas: líneas por partida (la principal), piezas, coincidencia con el maestro, % bajo τ y p50/p99 de latencia.
   - Salida en JSON y en Markdown.
   - Con un servidor falso en los tests; con `--url` contra un servidor real.
7. **Datos de imitación**:
   - `generar` escribe unas 16k decisiones del maestro, con ruido en la política para cubrir estados malos;
   - cada fila es la pregunta `choice` con sus opciones y descripciones de ese turno, la etiqueta (la opción del maestro) y,
     aparte, el objetivo blando softmax(valor/T).
   - **Investiga sin entrenar** (`sdk/python/chispa/train.py`, `model/l2/`) qué camino admite opciones que cambian en cada
     turno (descripciones variables, torre al vuelo): ajustar solo la torre, una cabeza sobre el codificador, o `chispa train`.
   - Escribe el formato que use ese camino y deja en el README el comando exacto y si necesita torch/GPU. **No entrenes.**
8. **Interfaz para la parte ALE:** un `Protocol` o una clase abstracta `Percepcion` (observación → tablero, pieza) y
   `Controlador` (colocación → secuencia de acciones), documentados y sin implementar. No instales ni importes `ale-py`.

## Hipótesis y criterio
- **Hipótesis:** con opciones autodescriptivas, un Chispa que siga los rasgos se acerca al maestro.
  - En el simulador, el maestro debe limpiar ≫ líneas que el aleatorio en 20 semillas fijas: por ejemplo, ≥ 50 líneas de
    media con un tope de 500 piezas, frente a < 2 del aleatorio.
  - **Si el maestro no llega a 50, revisa los rasgos y los pesos antes de seguir: es un bug.**
- **Hecho cuando:**
  - `python -m unittest discover -s demos/tetris-ale` pasa, con tests de motor, rasgos, maestro, veto, opciones,
    agentes con servidor falso y `generar`;
  - la tabla de `evaluar` en el simulador (aleatorio y maestro, 20 semillas) está en `demos/tetris-ale/resultados-sim.md`;
  - `generar` produce el conjunto de 16k en menos de 10 min de CPU (no lo commitees: solo una muestra de 50 filas en `fixtures/`);
  - el README explica las reglas, los agentes, los comandos y el camino de ajuste elegido.
- **Para y avisa con `blocker`** si algo falla dos veces.

## Límites
- **Tope:** 60 min y 8 USD.
- **Alcance:** solo escribes en `demos/tetris-ale/`. Sin red salvo el repo y nada de cómputo de pago.
- **Rama:** `delega/<id>`. Commits sin firmas ni trailers.

## Informe de cierre
- Rama y commits.
- Tabla del simulador.
- Tests.
- Camino de ajuste propuesto, con su comando y requisitos.
- Lo que queda para la parte ALE.
