# G.8b Barrido de λ, τ para esquemas nuevos y decodificación de score (añadidos a G.8)

## Antecedentes
G.8 (`model/l2/aws/general.sh`, `model/l2/formula-shrinkage.md`, `model/evaluacion/jevbench_l2.py`,
`model/evaluacion/aws/comparar_g8.py`) metaentrena L2 y elige κ en dev. Tres pedidos de otras sesiones llegaron tarde y no
entraron.

## Terminado cuando
1. **Convención de λ.** El runtime (Go y móvil) implementa `p = norm((1−w)·p_desc + w·media_ejemplos)` con `w = k/(k+λ)`.
   - Es la fórmula de G.8 con κ = λ: con λ = 0 solo cuentan los ejemplos; con λ = ∞, solo la descripción.
   - Añádelo de forma explícita a `formula-shrinkage.md`, con la tabla de equivalencias κ ↔ λ. Indica también qué hace el
     runtime con λ = ∞ por defecto: solo la torre de descripción, es decir, zero-shot.
2. **Barrido en test** en un script nuevo, `model/l2/aws/barrido.sh`, para una c6a.xlarge spot en CPU con el patrón de siempre. Usa el checkpoint que deja `general.sh` en `$CHISPA_G8_S3/ckpt/mejor.pt` (la g5 ya está lanzada y no se toca). Además del κ elegido en dev, evalúa las tareas no vistas (las excluidas) y JevBench
   con soporte k = 8 para λ ∈ {0, 1, 2, 4, 8, ∞}. λ = ∞ es el zero-shot.
   - Reutiliza S y las torres: no recalcules el codificador para cada λ. Si `evaluar` no lo permite, implementa una caché o
     una función que reciba las S ya calculadas.
   - Saca una tabla λ × tarea en `comparacion.md`.
   - Si cabe en la misma instancia y en el tiempo, haz lo mismo con L1 (potion con prototipos, `model/cascada/capas.py`):
     p_desc es el embedding de la descripción, con la misma fórmula.
3. **τ para esquemas nuevos.** Sobre las tareas no vistas, con λ = ∞ y con el λ elegido:
   - el τ de L2, sobre la confianza top-1, que da precisión 0,95 en lo contestado, y su abstención;
   - el τ que deja la abstención en ≤ 20 %, y su precisión.

   Lo mismo en JevBench, solo como comprobación. Sección «τ para esquemas nuevos» en `comparacion.md`, con el valor
   recomendado.
4. **score con la mediana CORAL.** En `model/**`, la etiqueta predicha de `score` es el número de umbrales j con
   `P(y>j) > 0,5`, no el argmax de `P(y=k)`. Así coincide con el runtime.
   - Aplícalo en `modelo.py`, `evaluar.py`, `jevbench.py` y `jevbench_l2.py`. Si `conjunta.py` también lo necesita, cámbialo.
   - Un test con acumuladas no monótonas.
- `barrido.sh` ≤ 16 KB, con `shutdown -h +90`. Si el barrido no cabe, recórtalo y dilo. **No toques `general.sh`**: ya está corriendo.
- Prueba en seco `CHISPA_LOCAL=1`, `bash -n`, `python -m unittest discover -s model -t .`, y `make test`/`make smoke` en
  verde **después** del último cambio.
- **Parada:** si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/**` (salvo `exportar.py` y `contrato-torre.md`), `model/evaluacion/**` y `model/cascada/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv` y modelos en `~/hf`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 60 min de reloj · ≤ 4 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- tamaño de `barrido.sh`;
- coste estimado nuevo;
- qué sustituyo para lanzar.
