# W6 Texto de torre v2 (sin id cuando hay descripción) en `model/`, variante «todo en mayúsculas» y ajuste fino v2

## Antecedentes
- El segundo ajuste fino no movió la robustez: renombrar ids cambia el 35 % de las decisiones de L2 porque el id va dentro
  del texto de la torre (`model/l2/resultados/ajuste2-20261102/LEEME.md`).
- **El contrato nuevo está en `model/l2/contrato-torre.md`**, en la sección «Texto de torre versión 2». Léelo entero: es la
  especificación.
- La variante «mayusculas» de `sdk/python/chispa/variantes.py` (E2) mezcla mayúsculas y minúsculas. Casi nunca activa la regla
  de normalización del 70 % (`model/l2/contrato-normalizacion.md`).

## Terminado cuando
1. **Texto v2 en `model/l2/modelo.py`.** `texto_opcion` y `texto_consulta` tienen el parámetro de versión (`"v1"` por
   defecto) y aplican la regla exacta del contrato.
   - La versión vive en la configuración del modelo y en el checkpoint (`texto_torre`). Un checkpoint sin ella es `"v1"`.
   - Al partir de G.8 con `--desde`, la versión viene de un flag nuevo, `--texto-torre v2_sin_id`, en `model/l2/entrenar.py`.
   - Entrenamiento, `calibrar.py`, la evaluación (`jevbench_l2`, `robustez.py`, `espanol.py` y `diag_score.py`) y el aumento
     usan la versión del checkpoint.
2. **El exportador** (`model/l2/exportar.py`):
   - escribe `META.texto_torre`;
   - calcula las torres de ESQUEMAS con esa versión.

   `chispa train` copia META del `l2.chispa`: compruébalo leyendo `sdk/python/chispa/train.py` (solo lectura). Si no lo
   copiara, dilo en el informe.
3. **Fixture de paridad** `model/l2/tests/fixtures/texto_torre_v2.json`, con ≥ 10 casos `{pregunta, opcion, descripcion, v1,
   v2}`:
   - con descripción;
   - sin descripción;
   - descripción de solo espacios;
   - acentos y ñ;
   - multi.

   Más un test que los compare con `texto_opcion`.
4. **Variante «todo en mayúsculas»** en `model/l2/robustez.py`:
   - nombre `todo_mayusculas`;
   - el mensaje entero con `str.upper()`; sobre él se aplica la normalización del modelo como en producción;
   - la variante «mayusculas» de E2 pasa a llamarse en el informe «mezcla de mayúsculas», **sin el criterio del 5 %**;
   - `todo_mayusculas` sí entra en el criterio.
5. **`model/l2/aws/ajuste.sh`** acepta `CHISPA_TEXTO_TORRE=v2_sin_id`, que pasa `--texto-torre v2_sin_id` al ajuste.
   - Mide el nuevo y G.8 (este con v1) en la misma máquina, con JevBench, M3 (con `todo_mayusculas`) y M4.
   - Tope y coste: ≈ 1 USD y `shutdown -h +75`.
6. **Tests:**
   - con v1 todo da exactamente lo mismo que antes (un test lo compara con la implementación anterior);
   - con v2, renombrar los ids de una fila con descripciones no cambia los textos de torre;
   - el exportador escribe META y las torres v2.
7. **Prueba en seco** de `ajuste.sh` (con `CHISPA_TEXTO_TORRE=v2_sin_id`) y de `estabilidad.sh`, sin `FALLO`.
8. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio. Si
   `make smoke` falla por un puerto ocupado, repítelo una vez y anótalo.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/l2/**` (salvo `resultados/`).
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, modelos en `~/hf` y datos en `~/datos`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 90 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- dónde se aplica la versión;
- el fixture;
- si `chispa train` copia META;
- la variante nueva;
- la tabla de `estado.tsv` de las dos pruebas en seco.
