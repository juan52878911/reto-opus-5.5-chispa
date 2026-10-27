# T1.5b Muestra para el etiquetado humano

Encargo: `plan/fase-1/encargo.md`. La herramienta ya está en `model/etiquetado/`; lee su `README.md`.

## Hipótesis
- `preparar.py` saca 300 filas estratificadas por tarea de los test reales sin cambios. Se refuta si
  alguna tarea tiene menos de 300 filas o clases sin representar.

## Terminado cuando
- Corre `python -m model.datos.convertir --salida /tmp/conv` y luego `model/etiquetado/preparar.py`
  con semilla 7 y 300 por tarea sobre estos test:
  - `whatsapp_comercio` e `intencion`, de `model/sondeo/`;
  - `herramientas`, de `model/herramientas/test.jsonl`;
  - `toxicidad`, de HateCheck-ES convertido;
  - `pqrs`, solo si ya hay test; si no, dilo.
- Deja `model/etiquetado/muestras/lote-1.jsonl`, sin la columna `etiqueta` visible para quien
  etiqueta: la herramienta ya la oculta, pero el fichero debe conservarla para medir.
- Deja también `model/etiquetado/muestras/LEEME.md`, con el recuento por tarea y clase y la semilla.
- Abre `etiquetar.html` con `node` como en sus tests, carga `lote-1.jsonl` y comprueba que lo parsea entero.
- `python -m unittest discover -s model -t .` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/etiquetado/muestras/`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, datos en `~/hf`. No hay red.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 30 min de reloj · ≤ 1,5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas: rama y sha, el recuento por tarea y lo que no se pudo hacer.
