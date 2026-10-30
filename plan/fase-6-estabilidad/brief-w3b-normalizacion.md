# W3b Normalización de mayúsculas en los dos lados y nota de M2 (sobre la rama de W3)

## Antecedentes
- **Rama de partida:** `delega/20261029-213652-68883`, que es W3: el aumento de datos (`model/l2/aumento.py`),
  `--desde` en `entrenar.py`, sib200 y pawsx, y `model/l2/aws/ajuste.sh`. Léelo antes de cambiar nada.
- **Decisión del orquestador:** las mayúsculas se normalizan **en los dos lados**: entrenamiento y evaluación en Python, y el
  runtime de la otra sesión. El formato del texto de la torre **no** cambia; el problema de los ids renombrados lo resuelve
  solo el aumento con ids opacos.

## Terminado cuando
1. **Función `normalizar_mayusculas(texto)`**, pública, en `model/l2/modelo.py`. Regla exacta: sobre el **texto del mensaje**
   (no la pregunta ni las descripciones), si tiene **≥ 8 letras** (`str.isalpha`) y **más del 70 %** de ellas son mayúsculas
   (`str.isupper`), devuelve `texto.lower()`; si no, el texto sin tocar.
2. **Dónde se aplica:**
   - en `texto_consulta` y en cualquier otro sitio donde se arme el texto de entrada de L2 (entrenamiento, evaluación,
     `calibrar.py`, exportador si aplica);
   - en el aumento: la variante de mayúsculas se genera antes de normalizar, así que el modelo ve lo mismo que verá en
     producción.
   - **No** la apliques a L1 ni al runtime de Go.
3. **Tests** de los bordes:
   - 7 letras en mayúsculas, que no cambia;
   - exactamente el 70 %, que no cambia;
   - el 71 %, que cambia;
   - texto sin letras;
   - acentos y ñ (`ÁRBOL ÑANDÚ…`);
   - números y emojis mezclados;
   - idempotencia.
4. **`model/l2/contrato-normalizacion.md`** con:
   - la regla exacta;
   - qué campo se normaliza y en qué momento: antes de tokenizar y de truncar;
   - **12 casos entrada → salida**, incluidos los bordes, como JSON en `model/l2/tests/fixtures/normalizacion.json`, para
     que la otra sesión haga su test de paridad en Go.
5. En `model/l2/contrato-largos.md`, una línea que diga que la estrategia por defecto sigue siendo `cabeza`: en M2 dio 0,485
   global y 0,366 en los 82 casos largos, y cola, cabeza+cola y trozos no la superan
   (`model/l2/resultados/estabilidad-20261029/m2/`).
6. Repite la **prueba en seco** de `model/l2/aws/ajuste.sh` (`CHISPA_LOCAL=1`), sin `FALLO`.
7. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio. Si
   `make smoke` falla por un puerto ocupado, repítelo una vez y anótalo.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/l2/**` (salvo `resultados/`).
- Rama: `delega/20261029-213652-68883`, para continuar sobre sus commits. Commits simples, sin firmas ni `Co-Authored-By`.
  Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. Sin red salvo la API de Claude.

## Tope
- ≤ 45 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- dónde se aplica la normalización;
- tests;
- la tabla de `estado.tsv` de la prueba en seco.
