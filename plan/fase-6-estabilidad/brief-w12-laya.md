# W12 Medir Laya (zero-shot, CPU) frente a Chispa en la batería M1 y en M4

## Antecedentes
- **Laya** es un motor de decisiones tipadas abierto (`pip install laya`, v0.4.21 en PyPI, Apache-2.0 en el paquete). Pesos en
  HF: `convaiinnovations/laya`, en tres checkpoints:
  - `english`: ModernBERT-large, 421M, 512 tokens;
  - `multilingual`: mmBERT-base, 322M, más de 100 idiomas, 1024 tokens; ampliable con `max_len`;
  - `typed-decisions`: ajustado sobre las typed decisions.
- **API**, de su README (sin red aquí: no la puedes consultar):

  ```python
  from laya import Router
  router = Router()   # descarga el checkpoint la primera vez
  questions = {"department": {"type": "choice", "instructions": "Which department should handle this?",
                              "criteria": {"billing": "invoices, payments, refunds", "technical": "bugs", "other": "everything else"}},
               "urgency": {"type": "score", "instructions": "How urgent is this?", "criteria": ["not urgent", "soon", "blocking"]},
               "churn_risk": {"type": "noul", "instructions": "Does the user threaten to cancel or leave?"}}
  r = router.predict(state, questions, model="multilingual")   # o model="typed-decisions"; max_len=…
  r["answers"]["department"]["choice"]   # id elegido
  r["answers"]["churn_risk"]["noul"]     # probabilidad de «sí»
  r["routing"]["model"]
  ```

  **No sabes la forma exacta de las probabilidades en choice y score.** El script tiene que volcar en el log la respuesta
  completa de la primera pregunta de cada tipo y adaptarse a ella: busca `probs` o `distribution`; si solo viene el id, usa
  la confianza que traiga o 1,0.
- **Qué se compara.** Chispa tiene dos referencias:
  - el ajuste 1, línea base oficial, en `model/l2/resultados/linea-base-oficial-20261102/`: exactitud 0,6436;
  - v2, en `model/l2/resultados/linea-base-v2-20261102/`: 0,5836.

  Las dos se midieron con la batería `sdk/python/chispa/bateria.py` y el manifiesto `sdk/python/ejemplos/bateria.json`, sobre
  las filas de test de `python -m model.datos.convertir` más JevBench.

## Terminado cuando
1. **`model/evaluacion/laya.py`** (nuevo): adaptador de nuestra fila (`model/esquema.md`) a la pregunta de Laya.
   - **choice:** `criteria = {id: descripción}`.
   - **noul:** pregunta noul; `true` si `p ≥ 0,5`.
   - **score:** `criteria` = descripciones de los niveles `1..K` en orden ascendente; el nivel elegido se mapea a su id.
   - `instructions` = `pregunta`.

   Corre los modelos `multilingual` y `typed-decisions`, sin ajustar, sobre **las mismas filas** que la batería: el mismo
   manifiesto y los mismos conjuntos (JevBench, massive, clinc150, hatecheck, spam, inyecciones y herramientas), solo split
   test. Saca, por conjunto y modelo:
   - exactitud por argmax y F1 macro, con la misma definición que `bateria.py`: **reutiliza sus funciones de métrica**, no
     las copies;
   - ECE sin calibrar;
   - latencia p50 y p99 por pregunta, en CPU con 4 hilos (`torch.set_num_threads(4)`).
2. **M4 en español:** MASSIVE-es y MMMLU ES_LA, con `model/l2/espanol.py` (lee cómo carga esos conjuntos). Exactitud en
   español y, donde haya pareja, frente a la inglesa.
3. **Licencia y datos:** el script lee la tarjeta de HF de cada checkpoint en la instancia y guarda `license` y lo que diga
   de los datos de entrenamiento en `resultados/laya-licencia.json`.
4. **`model/evaluacion/aws/laya.sh`** (nuevo): user-data de una **c6a.2xlarge en CPU**, con el patrón de
   `model/l2/aws/estabilidad.sh` (convierte los datos igual que su paso M1).
   - Lleva `__CHISPA_S3__`, `shutdown -h +90` y el coste declarado en la cabecera (≈ 0,3 USD).
   - **Primero, prueba de velocidad:** 50 preguntas de massive con `multilingual`. Si la proyección del total pasa de 70 min,
     recorta con un tope de filas por conjunto, de forma determinista, y anótalo. No sigue sin recortar si no cabe.
   - Sube `resultados.tgz`, `estado.tsv` y una tabla `laya-frente-chispa.md` con: conjunto · Laya multilingual · Laya
     typed-decisions · Chispa ajuste 1 · Chispa v2 · latencias. Las cifras de Chispa se leen de los `linea-base*.json` del
     repo.
5. **Prueba en seco** (`CHISPA_LOCAL=1`) con un Laya falso (un stub con la misma interfaz `Router.predict`, que devuelve la
   primera opción), sin `FALLO`. Tests del adaptador:
   - choice;
   - noul;
   - score con niveles desordenados (ordena por int);
   - el mapeo de ids.
6. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/evaluacion/**`. No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. **Commits simples, sin firmas ni `Co-Authored-By`.** Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, datos en `~/datos`. Sin red salvo la API de Claude: `laya` no está instalado y no
  se puede instalar aquí.

## Tope
- ≤ 75 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- el adaptador;
- qué se mide;
- la tabla de `estado.tsv` de la prueba en seco;
- cómo se lanza.
