He encontrado 7 fallos de paridad entre lo que entrena y exporta W4 y lo que hace el runtime. Los tres más graves están en la calibración: el τ de CALIB se mide sobre una regla de decisión y una confianza distintas de las que usa el servidor. Revisé la rama `delega/chispa-rm4` en el sha `71a7374`; no hay commits ni cambios en el árbol, y borré `/tmp/rm4` y `/tmp/rm4_s.py`. El directorio `/tmp/tmppgb3rm4n` no lo creé yo y lo dejé.

**Hallazgos, de más a menos grave:**

1. **El τ se calcula con parámetros por tarea que CALIB no lleva** (CONFIRMADO por lectura).
   - Modelo: `model/l2/calibrar.py:246-253` calcula el τ global con las probabilidades que da la cabeza ajustada a cada tarea (`params[(tarea, clave)]`).
   - Runtime: `format/chispa3/secciones.go:92,102` (`Tipos`/`TiposL2`) y `server/decide/calibvis.go:259` solo conocen parámetros por cabeza (`choice`, `noul`, `scoreK`).
   - Escenario: una tarea con la T de choice muy distinta de la global. Su confianza en el servidor no es la que se usó para elegir τ, así que la cobertura y la precisión del informe no se cumplen al servir.
   - Arreglo (modelo): calcular el τ con los parámetros de `tipos`, los mismos que se escriben en CALIB.

2. **noul: τ y acierto con argmax, pero el runtime decide con θ** (CONFIRMADO, ejecutado).
   - Modelo: `calibrar.py:185` (`_conf_ok`) toma confianza = máx(p) y predicción = argmax.
   - Runtime: `server/decide/l1.go:284` (`respuestaNoul`) responde «true» si pt ≥ θ, con confianza pt.
   - Escenario: θ = 0,3 y pt = 0,4. El runtime responde true con confianza 0,40; Python cuenta false con confianza 0,60.
   - Arreglo (modelo): en `_conf_ok` de noul, usar la regla con θ y la confianza de la clase decidida.

3. **score: la confianza de τ es máx(p), la del runtime es la probabilidad de la mediana** (CONFIRMADO, ejecutado).
   - Modelo: `calibrar.py:185`. Runtime: `server/decide/l2.go:642` (`r.Conf = r.Probs[mediana]`).
   - Escenario: p = [0,40, 0,15, 0,45]. Ambos lados responden «2», pero el runtime da confianza 0,150 y Python 0,45.
   - Arreglo (modelo): en score, usar como confianza p[etiqueta_coral(p)].

4. **score con ids no numéricos: Python lo rechaza y el runtime opina en el orden declarado** (CONFIRMADO, ejecutado).
   - Modelo: `model/datos/comun.py:188` (`niveles_score` lanza error).
   - Runtime: `server/decide/l2.go:647`, `runtime/torre/torre.go:77` y la misma lógica en `sdk/movil/chispamovil/chispamovil.go:1392`.
   - Escenario: [bajo, medio, alto] con s = 0,9 responde «alto»; las mismas opciones en orden descendente responden «bajo». La torre de consulta también cambia (alto/bajo). El modelo nunca se entrenó ni se calibró en estos casos.
   - Arreglo (runtime): no opinar si los ids no son exactamente 1..K.

5. **`_ajuste` de score con soporte pondera por el orden declarado, no por nivel** (CONFIRMADO, ejecutado con torch y un codificador falso).
   - Modelo: `model/l2/modelo.py:420,447`.
   - Escenario: la misma fila de score con soporte da {1: 0,305, 2: 0,162, 3: 0,533} con orden [1,2,3] y {1: 0,317, 2: 0,165, 3: 0,518} con orden [3,2,1]. Sin soporte, las dos coinciden.
   - Afecta al entrenamiento con `--episodios` en `ajuste.sh` cuando las filas del meta no vienen en orden ascendente. `validar.py` solo exige 1..K en orden para los datos propios, no para el meta.
   - Arreglo (modelo): reordenar sp por `niveles_score` antes de aplicar el linspace.

6. **No hay cabezas score con K ≥ 6 en `CABEZAS_L2`** (PLAUSIBLE: no cargué los datos para ver si existen).
   - Modelo: `model/l2/exportar.py:669`. Runtime: `l2.go:642` no opina si falta `scoreK`.
   - Escenario: una cabeza score6 entrenada sin filas en el dev no llega a CALIB, y el runtime escala siempre ese esquema.
   - Arreglo (modelo): añadir a CALIB todas las cabezas que existan en el checkpoint.

7. **La normalización de mayúsculas difiere en İ y en la sigma final** (CONFIRMADO, ejecutado; gravedad baja).
   - Modelo: `modelo.py:34` (`str.lower`). Runtime: `server/decide/normalizar.go:22` (`strings.ToLower`).
   - Python da «i̇stanbul» y «οδος»; Go da «istanbul» y «οδοσ».
   - Arreglo (modelo): reproducir en Python el `ToLower` de Go por carácter.

**Comprobado sin diferencias:**
- **Texto de torre y consulta:** el texto de torre es idéntico en los dos lados (`passage: ¿Tema? · a · `, ejecutado). Los prefijos `query: ` y `passage: ` y las torres de consulta («true» en noul, «K» en score) también coinciden.
- **Hash de ESQUEMAS v2 en noul:** el de Python y el de Go son iguales (`9b7b42bf…`, ejecutado).
- **Orden de score:** en ids 1..K, el entrenamiento y el runtime indexan igual. `orientacion_score.py` ordena por nivel y no por el orden declarado. Las filas con «01» o 0..K-1 las descarta sin avisar en `orientacion_score.py:80`, y el runtime tampoco opina en ellas.
- **Renombrado de ids:** solo toca filas choice. No cambia `pregunta`, el hash de ESQUEMAS ni las claves de CALIB, y `origen` se conserva bien.
- **Normalización:** se aplica en `Codificador.tokens`, así que cubre el entrenamiento, el aumento, la evaluación, la calibración y `orientacion_score`.
- **CALIB:** los incrementos `scoreK#j` y a/T se leen igual en los dos lados.
- **max_tok:** el del checkpoint llega bien a la exportación.

**Sin verificar:** el runtime más reciente (Itoa canónico, prompt de L3 por nivel, Swift), los SDK de Android e iOS, la calibración de multi y si hay datos de score con K ≥ 6.