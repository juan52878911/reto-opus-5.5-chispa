# W2 Robustez de L1 y L2 (M3) y español frente a inglés (M4), en la misma corrida de c6a que W1

## Antecedentes
- **Checkpoint:** el de G.8, `s3://chispa-pruebas-879381269751/general-20261029b/ckpt/mejor.pt`. En kindling, el
  checkpoint aleatorio de `model.l2.exportar.modelo_aleatorio`.
- **W1 ya dejó `model/l2/aws/estabilidad.sh`.** Es el user-data de una c6a.2xlarge que corre M2, M5 y M6 y escribe
  `estado.tsv`. Léelo y **añade** tus pasos al final, sin romper los suyos.
- **L1:** potion con prototipos, en `model/l1/`. **L2:** `model/l2/modelo.py`, y la evaluación en
  `model/evaluacion/jevbench_l2.py` y `model/l2/calibrar.py`.
- La otra sesión hará un generador de variantes en el runtime (E2). Hasta que llegue, el generador es propio, en Python.
- **Meta de G.8:** sobre todo en inglés. Fuentes con español de licencia comercial: massive (es) y las conocidas de
  `model.datos`.

## Terminado cuando
1. **M3**, `model/l2/robustez.py` (nuevo).
   - **Generador** de variantes deterministas con semilla, sobre JevBench y el dev de las tareas de `model.datos`:
     - permutar el orden de las opciones;
     - renombrar los ids de las opciones (manteniendo la descripción);
     - paráfrasis ligera de la pregunta (plantillas: reordenar, sinónimos de una lista fija, sin LLM);
     - erratas en el mensaje (1–3 por texto: cambio, borrado o duplicado de carácter);
     - mayúsculas/minúsculas;
     - pregunta en español frente a inglés: traducción con plantillas para las tareas cuyo esquema exista en los dos
       idiomas; si no se puede de forma determinista, márcalo como no medido.
   - **Medida**, para L1 y L2: el porcentaje de decisiones (argmax) que cambian frente al original y la diferencia de
     exactitud, por tipo de variante, con IC95.
   - **Umbral:** si un tipo rompe más del 5 % de las decisiones, propón el arreglo (aumento de datos en el entrenamiento,
     normalización en el runtime, etc.) con su coste estimado. No lo ejecutes.
2. **M4**, `model/l2/espanol.py` (nuevo).
   - Saca la exactitud y la macro-F1 de L2 en las tareas que existen en español e inglés (p. ej. massive es/en, y las que
     encuentres en `model.datos`), con el mismo esquema y el mismo número de casos.
   - Saca la diferencia es − en con IC95.
   - Si la diferencia es mayor de 3 puntos, prepara (sin lanzar) el plan de reentrenamiento:
     - fuentes en español de licencia comercial (ALIA, MultiPICo, toxicity-es, PAWS-X y SIB-200, con su licencia
       comprobada en la tarjeta de HF), y PQRS solo en test;
     - tamaño;
     - cambios en `model/l2/aws/general.sh`;
     - coste en GPU (g5, horas y USD).
3. **Añade M3 y M4** a `model/l2/aws/estabilidad.sh`, con sus líneas de `estado.tsv`, y comprueba que el total sigue cabiendo
   en ≤ 90 min en una c6a.2xlarge.
4. **Prueba en seco** (`CHISPA_LOCAL=1`) del script completo, sin `FALLO`. Tests del generador: es determinista, la
   permutación conserva la etiqueta y el renombrado la mapea.
5. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/robustez.py`, `model/l2/espanol.py`, `model/l2/aws/estabilidad.sh`, `model/l2/aws/empaquetar_estabilidad.sh` y
  `model/l2/tests/**`.
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, modelos en `~/hf` y datos en `~/datos`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 110 min de reloj · ≤ 7 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- variantes y tareas medidas;
- la tabla de `estado.tsv` de la prueba en seco;
- el tiempo total estimado en c6a.
