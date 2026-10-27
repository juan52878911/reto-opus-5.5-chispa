# T1.5 Herramienta de etiquetado humano y acuerdo κ

Encargo: `plan/fase-1/encargo.md`; esquema `model/esquema.md` (congelado). Criterio de la fase:
300 ejemplos de test por tarea, etiquetados por dos personas distintas de quien escribió los
sintéticos, con κ ≥ 0,7. Las personas etiquetan en su navegador, sin servidor y sin red.

## Hipótesis
- Una página HTML de un solo fichero, que carga un JSONL local y exporta otro, basta para que dos
  personas etiqueten 300 ejemplos por tarea en ≤ 1 h cada una. Se refuta si no funciona sin red o si
  pierde el trabajo al recargar.

## Terminado cuando
- `model/etiquetado/etiquetar.html`: un solo fichero, sin dependencias externas (nada de CDN).
  - Carga un JSONL del esquema con un selector de fichero.
  - Pide el nombre de quien etiqueta.
  - Muestra pregunta, texto y opciones con su descripción; la etiqueta original **no se ve**.
  - Atajos de teclado (1-9, flechas, `e` = escalate, `?` = dudoso).
  - Guarda el progreso en `localStorage` y protege los accesos con try/catch.
  - Exporta `{id, etiqueta, anotador, ts, dudoso}` en JSONL.
  - Orden aleatorio con una semilla por anotador.
- `model/etiquetado/preparar.py --entrada <jsonl…> --por-tarea 300 --semilla 7 --salida <jsonl>`:
  muestra estratificada por clase del test de cada tarea (T1.4, sondeo y lo que haya del conversor).
  No mezcla filas con `uso_comercial: false` si no se piden.
- `model/etiquetado/acuerdo.py --a <jsonl> --b <jsonl> [--oro <jsonl>]`:
  - κ de Cohen por tarea y global.
  - Matriz de confusión entre anotadores.
  - Acuerdo con la etiqueta original.
  - Lista de discrepancias para resolver.
  - Escribe un JSONL «adjudicado» con mayoría o marca de conflicto.
- Tests con `unittest` en `model/etiquetado/tests/`:
  - κ calculado a mano en 2-3 casos, incluido el de acuerdo total y el de acuerdo por azar.
  - Estratificación del muestreo.
  - Exportación con el formato pedido.
- Una prueba del HTML sin navegador: un test que extrae el JS y comprueba con `node`, si está, la
  función de parseo y la de exportar. Si no hay node, dilo.
- `README.md` corto en español para quien etiqueta: cómo abrirlo, atajos y qué entregar.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/etiquetado/`. **No tocar**: `model/esquema.md` ni otras carpetas.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 90 min de reloj · ≤ 4 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas que diga:
- qué cambiaste, con la rama y el sha;
- qué verificaste, con cifras;
- qué quedó sin verificar;
- qué recomiendas.
