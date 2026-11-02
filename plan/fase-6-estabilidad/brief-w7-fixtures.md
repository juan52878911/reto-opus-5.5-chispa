# W7 Unificar los fixtures de texto de torre v2 y de normalización con el runtime

## Antecedentes
- `model/l2/tests/fixtures/texto_torre_v2.json` es la **fuente única** de los casos de texto de torre. La otra sesión lo
  copiará tal cual a `server/decide/testdata/`.
- Hoy tiene 21 casos en `preguntas` y el runtime tiene 28. Los 21 coinciden.
- Los 13 que faltan están en `model/l2/tests/fixtures/texto_torre_v2-faltan.json`, en el mismo formato `preguntas`:
  - tres iguales y una distinta;
  - noul;
  - score;
  - espacios Unicode NBSP, U+3000, U+2028 y U+0085;
  - U+200B, que **no** cuenta como espacio.
- `model/l2/tests/fixtures/normalizacion.json` tiene 15 casos. El runtime añadió un 16.º: «ⓉⓄⒹⓄ ⓂⒶⓁ ok», que no cambia.
  Python cuenta 2 letras y 0 mayúsculas.

## Terminado cuando
1. **Las 13 preguntas de `-faltan.json` pasan a la lista `preguntas` de `texto_torre_v2.json`**, con sus `v1` y `v2`
   **regenerados con `texto_opcion` y `texto_consulta`**, no copiados.
   - Compara lo generado con lo que trae `-faltan.json`. **Cualquier diferencia es un fallo real de un lado:** dila en el
     informe con el caso, el texto de Python y el del runtime.
   - **No corrijas `texto_opcion` para que cuadre** sin explicar por qué el lado de Python era el incorrecto (p. ej., que
     `str.strip()` de Python y el `strip` del contrato traten distinto U+200B o U+0085).
   - Si la diferencia sale de que el contrato no define un caso, propón la regla en el informe.
2. **El caso 16** «ⓉⓄⒹⓄ ⓂⒶⓁ ok» → «ⓉⓄⒹⓄ ⓂⒶⓁ ok» va al final de `normalizacion.json`. El test pasa a esperar 16 y
   `contrato-normalizacion.md` dice 16.
3. Borra `texto_torre_v2-faltan.json` cuando sus casos estén dentro, o deja una nota si queda alguno pendiente por una
   discrepancia.
4. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para. No lances nada en AWS.

## Zona
- `model/l2/**` (salvo `resultados/`). No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf`. Sin red salvo la API de Claude.

## Tope
- ≤ 30 min de reloj · ≤ 2 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- el número de casos por fichero;
- las discrepancias, una por una, o «ninguna».
