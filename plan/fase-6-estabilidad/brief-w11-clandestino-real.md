# W11 Conversor de Clandestino con su formato real (antes del ajuste v3)

## Antecedentes
- W9 dejó `model/datos/clandestino.py` con columnas **supuestas**. **Clandestino no está en HF, sino en GitHub**:
  `microsoft/Clandestino`, MIT. Datos: `https://raw.githubusercontent.com/microsoft/Clandestino/main/data/clandestino_no_ontology_42023.json`,
  103,7 MB, una fila JSON por línea.
- **Muestra real** en `model/datos/fixtures/clandestino/clandestino_muestra.json` (lee su README).
- **Formato** de cada fila: `Key`, `Sentence`, `IsAIGenerated` (cadena `"True"`/`"False"`), `Index`, `Switch` y `Annotators`.
  - `Annotators` es una lista de 5 a 12 dicts, con la clave `Annotator` y las preguntas como claves de texto completo
    («Question 1: In your opinion, will this text be harmful to anyone?», …).
  - **Valores vistos:**
    - Q1, dañino: `"1"` a `"5"`;
    - Q2 (estereotipo positivo), Q3 (contenido sexual), Q7 (PII) y Q8 (información falsa): Yes, No o Maybe;
    - Q4, grupo objetivo: «8. Mujeres», «20. Otro», «21. No aplicable», «7. LGBT+»…; Q4.a lista otros;
    - Q5: cómo se refiere al grupo;
    - Q6: Factual, Opinion o Not applicable.
  - Los textos están en español.
- **Decisión del orquestador:**
  - **Filtro:** `IsAIGenerated == "False"`, y se descartan las filas en las que **algún** anotador marque Q7 = Yes (PII).
  - **score 1–5:** dañino, con la mediana de los anotadores redondeada.
  - **noul:** dañino (mediana ≥ 3).
  - **noul con Q3 y con Q8:** solo con mayoría estricta de Yes o No; Maybe no cuenta, y sin mayoría se omite.
  - **multi:** los grupos de Q4 que marque la mayoría de los anotadores, sin «21. No aplicable».

## Terminado cuando
1. **`model/datos/clandestino.py`** con el formato real.
   - Identifica las preguntas **por prefijo** («Question 1:», «Question 7:»…), no por el texto entero.
   - Si falta alguna clave esperada, falla con un `ValueError` claro que liste lo que trae la fila.
   - Hace la conversión decidida, con preguntas y descripciones en español, ids `1..5` en score y `true`/`false` en noul.
   - Pone `licencia: "MIT"` y `uso_comercial: true`.
   - Plantilla por `Key`, para repartir los splits sin fugas.
2. **`python -m model.datos.clandestino contar FICHERO`** imprime en JSON:
   - filas leídas;
   - filas de IA descartadas;
   - filas con PII descartadas;
   - filas por tipo y split;
   - la distribución de score.
3. **Tests con la muestra real:**
   - la fila de IA y las de PII se descartan;
   - la mediana y el redondeo;
   - el umbral de noul;
   - Q3 y Q8 sin mayoría se omiten;
   - los grupos de multi;
   - los ids `1..K`;
   - es determinista.
4. **`model/l2/aws/ajuste.sh`** (con `CHISPA_V3`) baja el fichero de la URL de GitHub y corre primero el `contar`. Si no hay
   filas válidas, falla con un mensaje claro **antes** de entrenar.
5. **Prueba en seco** de `ajuste.sh` con `CHISPA_V3=1` y la muestra, sin `FALLO`. `python -m unittest discover -s model -t .`,
   `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/datos/**` y `model/l2/aws/**`. No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`. Sin red salvo la API de Claude.

## Tope
- ≤ 50 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- el mapeo;
- los conteos sobre la muestra;
- la prueba en seco.
