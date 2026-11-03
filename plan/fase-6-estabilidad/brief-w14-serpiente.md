# W14 «Chispa: Serpiente», un juego original del género serpiente para ver a Chispa decidir rápido

## Antecedentes
- **Caída** (`demos/caida/`, de otra sesión, solo lectura) es la referencia de estructura.
  - Motor del juego, estado en palabras, cliente HTTP de `/v1/decide` (`api.py`) y agentes.
  - `jugar` (traza JSONL), `medir` (latencia en frío y en caliente), `evaluar` (N partidas por agente) y `renderizar`
    (traza → MP4 1080p a 30 fps con Pillow y ffmpeg).
  - `--decidir argmax|tau` y la marca `decidio` = `chispa_tau` / `chispa_bajo_tau` / `escudo`, con un servidor falso
    para los tests.
  - **Léelo entero y reutiliza su forma**, pero el código es propio: no se importa nada de `demos/caida` (son demos
    independientes).
- Corre en un servidor Linux con Python 3.11 **solo con biblioteca estándar**; el render, en el Mac, con Pillow y ffmpeg.

## Diseño (original: no imites ninguna versión concreta de Snake, ni Nokia ni Laya)
- **Nombre y aspecto propios:** «Chispa: Serpiente», con paleta propia (la de Caída o una nueva), rejilla de 16×16.
- **Reglas:**
  - la serpiente avanza una casilla por paso;
  - comer la chispa hace crecer la serpiente y aparece otra en una casilla libre, con una semilla determinista;
  - chocar con un muro o consigo misma termina la partida;
  - tope de pasos por partida: 500.
- **Decisión por paso:** una pregunta `choice` con 3 opciones **relativas**: `izquierda`, `recto` y `derecha`, con
  descripciones en español.
  - El texto de entrada describe el estado **con palabras**: hacia dónde queda la comida respecto a la cabeza (delante,
    detrás, a la izquierda o a la derecha, con distancia), cuántas casillas libres hay antes de chocar en cada una de las
    3 opciones, si una opción mete a la serpiente en una zona cerrada pequeña, y la longitud.
  - El mismo texto en todos los agentes.
- **Profesor heurístico:**
  - BFS hacia la comida, descartando las opciones que dejan a la cabeza sin camino hacia la cola, o con una zona alcanzable
    menor que la longitud (anti-encierro);
  - si no hay camino, la opción con más espacio libre.
- **Agentes:**
  - aleatorio;
  - profesor;
  - Chispa zero-shot (`/v1/decide` con la pregunta choice, `--decidir argmax|tau`; escudo = profesor si no hay `probs` o en
    modo `tau` si escala).
  - Few-shot no hace falta ahora.

## Terminado cuando
1. **`demos/serpiente/`**, con:
   - `serpiente/{motor,estado,api,agentes,jugar,medir,evaluar,traza,renderizar}.py`, o los que encajen;
   - `correr.sh`, que hace como el de Caída: jugar, medir, evaluar y, si hay Pillow y ffmpeg, renderizar;
   - `README.md`;
   - `requirements-render.txt`;
   - `tests/`.
2. **`evaluar`:** N partidas por agente (por defecto 20, semillas fijas). Por agente:
   - pasos sobrevividos y comida, en media y mediana;
   - % de coincidencia con el profesor, en las decisiones donde Chispa decidió;
   - % de decisiones bajo τ;
   - % de escudo;
   - latencia p50 y p99 por decisión.

   Salida en `evaluacion.md` y `evaluacion.json`.
3. **`renderizar`:** traza → MP4 1080p a 30 fps, de **20 a 40 s** (acelera si la partida es larga y limita los turnos).
   - En cada turno se ve la decisión de Chispa, su confianza, y si fue ≥ τ, bajo τ o escudo.
   - Lleva un panel con la comida, la longitud y los pasos.
   - Busca ffmpeg en el `PATH`.
4. **Tests con servidor falso**, sin red:
   - el motor (choques, crecimiento, determinismo con semilla);
   - el texto de estado;
   - el profesor (no se suicida si hay salida; anti-encierro);
   - el cliente y `--decidir`;
   - `evaluar`.

   `python3 -m unittest discover -s demos/serpiente` en verde, **con Python 3.11 y solo biblioteca estándar** (el render se
   salta si no hay Pillow).
5. `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para. No lances nada en AWS ni toques ningún servidor.

## Zona
- `demos/serpiente/**`. No toques `demos/caida`, `server/`, `sdk/`, `format/` ni `model/`.
- Rama: la que te da delega. Base: `integracion-limpia`. **Commits simples, sin firmas ni `Co-Authored-By`.** Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, aunque el código tiene que valer con `python3` sin dependencias. Sin red salvo la
  API de Claude.

## Tope
- ≤ 75 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- reglas y texto de estado, con un ejemplo;
- el profesor;
- tests;
- cómo se lanza.
