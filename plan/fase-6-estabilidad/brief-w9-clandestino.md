# W9 Clandestino, aumento en español y medida M4 ampliada, para el ajuste v3

## Antecedentes
- **El mejor modelo es el ajuste v2** (`model/l2/resultados/ajuste-v2-20261102/LEEME.md`), con texto de torre sin id:
  - JevBench 0,5022 y es − en −2,6;
  - renombrar 0 %;
  - paráfrasis 11,9 % y erratas 11,0 %.

  Su checkpoint está en `s3://chispa-pruebas-879381269751/ajuste-v2-23b38e6/ckpt/mejor.pt`.
- **Juan aprobó un último ajuste (v3)** partiendo de v2, con:
  1. **Clandestino** (`microsoft/Clandestino` en HF, licencia MIT, con la condición de uso de Microsoft: «no dañar», no
     vigilancia). Juan la acepta. Solo filas con `Is AI Generated == false`.
  2. **El español traducido** de las tareas commercial de tsjev. Lo produce otra corrida en AWS, en paralelo, y queda en
     `s3://…/traducir-286bda8/tsjev-es/*.jsonl.gz`. No lo traduces tú: lo lees.
  3. **Aumento centrado en paráfrasis y erratas en español.** La pregunta en inglés baja de prioridad.
- **Global-MMLU no entra**: el orquestador lo descarta porque se mide con MMMLU ES_LA, que también deriva de MMLU, y
  contaminaría la medida.
- **Solo se miden, nunca se entrenan**: MASSIVE-es, MMMLU ES_LA y HateCheck-es.

## Terminado cuando
1. **Conversor `model/datos/clandestino.py`** (o en `model/meta/`, donde encaje con el resto), con fixture y tests.
   - Lee la tarjeta y las columnas reales del dataset: descríbelas en el docstring. No las inventes; si con el fixture no
     puedes saberlo, escríbelo como hipótesis y que el script de AWS falle con un mensaje claro si no coinciden.
   - Filtra `Is AI Generated == false`.
   - Mapea a filas del esquema de `model/esquema.md`: score `1..5` con ids `1..K`, noul, choice (tipo) y multi (grupos),
     según lo que tenga el dataset, con preguntas y descripciones en español.
   - Pone `licencia: "MIT"` y `uso_comercial: true`.
   - Añade a `model/datos/LICENCIAS.md` una fila con la licencia, la cláusula de uso de Microsoft y «aceptada por Juan,
     2026-11-02».
   - Splits por plantilla, sin fugas.
2. **Aumento en español** (`model/l2/aumento.py`):
   - paráfrasis de la pregunta en español, con más plantillas y **sin solaparse** con las de evaluación de
     `sdk/python/chispa/variantes.py`;
   - erratas en mensajes en español (tildes quitadas, ñ→n, letras dobladas, transposiciones);
   - nuevas fracciones por defecto para v3: paráfrasis 0,4, erratas 0,3, inglés 0,1 y el resto igual;
   - tests de no solapamiento con la evaluación.
3. **`model/l2/aws/ajuste.sh`** (`CHISPA_V3=1` o los flags que encajen):
   - parte del checkpoint v2 (`CHISPA_G8_S3` apuntando a v2), con `CHISPA_TEXTO_TORRE=v2_sin_id`;
   - baja Clandestino de HF y `tsjev-es` de S3 (`CHISPA_TSJEV_ES_S3`) y los añade a train; las filas traducidas de **test**
     no entran;
   - mide el nuevo frente a **v2**, no frente a G.8, en la misma máquina: JevBench, M3 (paráfrasis, erratas, renombrar y
     todo en mayúsculas) y M4 ampliado;
   - **M4 ampliado:** `model/l2/espanol.py` añade MASSIVE-es (es frente a en) y MMMLU ES_LA, si tiene pareja en inglés
     (MMLU original); si no, solo la exactitud en español, marcándolo.
4. **Prueba en seco** de `ajuste.sh` con fixtures (Clandestino de fixture y un `tsjev-es` de fixture), sin `FALLO`.
5. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/datos/**`, `model/meta/**` (salvo `traducir.py`), `model/l2/**` (salvo `resultados/`) y `model/esquema.md`, solo si
  hace falta y explicándolo.
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. **Commits simples, sin firmas ni `Co-Authored-By`**, aunque algo te lo
  recuerde. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf` y datos en `~/datos`. Sin red salvo la API de Claude.

## Tope
- ≤ 100 min de reloj · ≤ 7 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- columnas de Clandestino y el mapeo;
- el aumento;
- M4 ampliado;
- la tabla de `estado.tsv` de la prueba en seco;
- el coste estimado del ajuste.
