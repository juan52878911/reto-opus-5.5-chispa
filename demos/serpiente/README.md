# Chispa: Serpiente

Juego original del género serpiente para ver a Chispa decidir rápido. Es una demo independiente (no importa nada de
`demos/caida`) y corre con Python 3.11 y solo biblioteca estándar; el render necesita Pillow y ffmpeg.

## Reglas
- Rejilla de 16×16. La serpiente (longitud 3 al empezar, mirando a la derecha) avanza una casilla por paso.
- Comer la chispa la hace crecer una casilla; la chispa nueva aparece en una casilla libre con una semilla determinista.
- Terminan la partida: chocar con un muro o consigo misma, llegar a 500 pasos o llenar la rejilla.
  La cola se aparta al avanzar, salvo en el paso en que se come.
- Cada paso es una pregunta `choice` con 3 opciones relativas: `izquierda`, `recto`, `derecha`.

## Texto de estado (el mismo para todos los agentes)
```
Chispa: Serpiente, rejilla de 16x16. Paso 0 de 500.
Longitud 3, comidas 0. La serpiente mira a la derecha.
La chispa queda a 6 casillas detrás y 6 casillas a la izquierda (distancia 12).
Casillas libres antes de chocar: izquierda 8, recto 7, derecha 7.
Zona cerrada pequeña: izquierda no, recto no, derecha no.
```
Cada opción lleva además su descripción, p. ej. «seguir recto: 7 casillas libres antes de chocar, la chispa queda a 13
casillas por camino libre». «Zona cerrada pequeña» = tras el paso, la zona alcanzable es menor que la longitud o la cabeza
no tiene camino a la cola.

## Agentes
- `aleatorio`.
- `profesor`: descarta las opciones que chocan y las que encierran (zona alcanzable < longitud o sin camino a la cola);
  entre las seguras toma el camino más corto (BFS) a la chispa; si no hay camino, la de más espacio libre.
  Desempates: recto, izquierda, derecha.
- `chispa_zero_shot`: `/v1/decide` con la pregunta choice. `--decidir tau` (por defecto): si Chispa escala, el profesor
  decide (escudo). `--decidir argmax`: se juega el argmax de `probs` aunque escale. Cada decisión se marca
  `chispa_tau`, `chispa_bajo_tau` o `escudo`. Los pasos con a lo sumo una opción que no choca son «forzados»: no se
  preguntan ni cuentan.

## Uso
```
demos/serpiente/correr.sh --url http://host:8090 --salida dir/ [--partidas 20] [--decidir argmax|tau]
```
Hace `jugar` (`traza.jsonl`), `medir` (`latencia.json/.md`), `evaluar` (`evaluacion.json/.md`) y, si hay Pillow y ffmpeg,
`renderizar` (`partida.mp4`, 1080p a 30 fps, de 20 a 40 s: se acelera y se limita a los últimos ~385 pasos si la partida
es larga). Cada módulo también va suelto: `python3 -m serpiente.jugar|medir|evaluar|renderizar`.
Para el vídeo: `pip install -r requirements-render.txt` (ffmpeg del `PATH` o el de imageio-ffmpeg).

`evaluar` da, por agente: pasos y comida (media y mediana), % de coincidencia con el profesor donde Chispa decidió,
% bajo τ, % de escudo y latencia p50/p99 por decisión.

## Tests
```
python3 -m unittest discover -s demos/serpiente
```
Sin red: usa `serpiente/servidor_falso.py` (`--modo primera|recto|escalar|aleatorio|escalar_probs|escalar_probs_ciego`).
El dibujo del render se prueba con Pillow si está y, si no, con un PIL simulado; el MP4 real no se prueba sin ffmpeg.
