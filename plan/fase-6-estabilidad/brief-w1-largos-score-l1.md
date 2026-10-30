# W1 Textos largos (M2), diagnóstico de score (M5) y L1 frente a L2 (M6), con una corrida en c6a

## Antecedentes
- **Checkpoint:** el de G.8, `s3://chispa-pruebas-879381269751/general-20261029b/ckpt/mejor.pt`, con `max_tok` 256 dentro
  del checkpoint. En kindling no hay S3: prueba con el checkpoint aleatorio (`model.l2.exportar.modelo_aleatorio`, como hace
  `model/bench/torre/e2e.sh` con `CHISPA_LOCAL=1`).
- **Evaluación de JevBench con L2 en Python:** `model/evaluacion/jevbench_l2.py`, con `texto_consulta` y
  `predecir_variante`. El modelo está en `model/l2/modelo.py`.
  - JevBench tiene 231 casos.
  - Python k = 0 da 0,485, y por tipo: choice 0,468, noul 0,554 y score 0,333.
  - Entre 49 y 108 casos superan 256 tokens y se truncan por la cabeza.
- **L1:** `model/l1/` (potion con prototipos y cabeza; `evaluar.py` saca la macro-F1 por tarea). Las tareas y el dev de L2
  salen de `model.datos` y de `model/l2/calibrar.py`.

## Terminado cuando
1. **M2, textos largos**, en `model/l2/largos.py` (nuevo). Sin reentrenar, con el checkpoint, en JevBench y sobre los
   casos que superan `max_tok`, mide estas estrategias:
   - cabeza, la actual;
   - cola;
   - cabeza + cola (mitad y mitad);
   - trozos de `max_tok` con solape de 32, agregados con el máximo de s por opción;
   - los mismos trozos agregados con la media.

   Saca la exactitud global y por tipo, y en los casos largos, con IC95 por bootstrap. Recomienda una estrategia solo si
   gana con IC que no se solape en los largos, o si empata y es más barata. Escribe el contrato exacto (tokenización, solape
   y agregación) para que la otra sesión lo implemente en el runtime: `model/l2/contrato-largos.md`.
2. **M5, score**, en `model/l2/diag_score.py` (nuevo). Separa las causas del 0,333 de score en JevBench:
   - (a) ranking: ¿la s de MaxSim ordena bien los niveles? Mide Spearman entre s y la etiqueta, y la exactitud de un
     oráculo que elige el mejor umbral por caso;
   - (b) cabeza CORAL y calibración: exactitud con los umbrales del checkpoint frente a umbrales reajustados en un dev
     (validación cruzada, dejando un esquema fuera);
   - (c) datos: cuántos ejemplos score había en el meta de G.8, por K, y de qué fuentes (lo ves en `model/l2/aws/general.sh`
     y en los conversores de `model.datos`).

   Con eso, propón el arreglo más barato con su coste estimado (CPU o GPU, horas y USD).
3. **M6, L1 frente a L2**, en `model/l1/frente_l2.py` (nuevo). Mide la macro-F1 de L1 (potion con prototipos, el que va en
   producción) y la de L2 (el checkpoint) sobre las mismas tareas y particiones de test que usa `model/l1/evaluar.py`. Saca
   la proporción L1/L2 por tarea y la media. Criterio de la fase 3: ≥ 0,90.
4. **Corrida de AWS:** `model/l2/aws/estabilidad.sh` (nuevo), un user-data de una c6a.2xlarge bajo demanda con el patrón de
   `model/bench/torre/e2e.sh`. Tiene que:
   - llevar el marcador `__CHISPA_S3__`, `shutdown -h +90` y descargas por fichero (el rol no tiene `s3:ListBucket`);
   - clonar JevBench y bajar lo que haga falta de HF y de S3;
   - correr M2, M5 y M6;
   - subir `resultados.tgz` y `log.txt`, con un `estado.tsv` de OK/FALLO por paso;
   - pesar ≤ 16 KB, o comprimido con gzip si pasa de eso;
   - empaquetarse con `model/bench/torre/empaquetar.sh` o uno propio en `model/l2/aws/`.
5. **Prueba en seco** del script completo (`CHISPA_LOCAL=1`) con el checkpoint aleatorio y fixtures, sin `FALLO`.
   - Tests unitarios de cada estrategia de M2: la tokenización de trozos y que cabeza+cola respeta `max_tok`.
6. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/largos.py`, `model/l2/diag_score.py`, `model/l2/contrato-largos.md`, `model/l1/frente_l2.py`,
  `model/l2/aws/estabilidad.sh`, `model/l2/aws/empaquetar_estabilidad.sh` y `model/l2/tests/**`.
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`; datos en `~/datos`. Sin red salvo la
  API de Claude.

## Tope
- ≤ 110 min de reloj · ≤ 7 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- qué mide cada pieza;
- la tabla de `estado.tsv` de la prueba en seco;
- el tiempo estimado de la corrida en c6a;
- qué sustituyo para lanzarla.
