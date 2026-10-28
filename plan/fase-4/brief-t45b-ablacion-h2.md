# T4.5b Ablación de H2: qué componente se come 4–5 puntos de punta a punta

## Antecedentes
`server/deploy/resultados/e2e-20261028/LEEME.md` (intentos 3 y 4): la cabeza conjunta L2c servida por `chispa-server
-tags ort` saca 0,771 en massive y 0,846 en clinc150, frente a 0,817 y 0,890 de `model/l2/conjunta.py`.

Descartados:
- la poda del vocabulario: mismo resultado con y sin ella, y 0 % de `<unk>`;
- la cuantización del codificador.

La paridad ONNX ↔ PyTorch de `exportar.py` se queda en 0,84 de top-1.

Candidatos:
- las torres int8 de ESQUEMAS;
- los prototipos int8 de CONJ;
- el simproto int8 del servidor (T4.5, |Δp| ≈ 3e-3 en fixtures);
- la escala de las log-probs del L0 de Chispa (el servidor) frente al L0 de sklearn (`conjunta.py`), aunque `chispa train`
  entrena la cabeza con el L0 de Chispa;
- cómo arma el servidor las entradas de la cabeza: orden de opciones, `escalate`, prefijos «query:»/«passage:», truncado.

Esto es un **diagnóstico**, no un arreglo.

## Hipótesis
Un componente explica ≥ 3 de los 4–5 puntos. Se refuta si ninguno pasa de 3, o si la suma no cierra el hueco.

## Terminado cuando
- `server/deploy/ablacion/ablacion.py`: arnés Python **offline** que reconstruye la decisión de L2c fila a fila desde el
  `.chispa` que produce `chispa train --conjunta`, con estos componentes:
  - **A. Codificador.** El ONNX del `.chispa` o PyTorch con el checkpoint (`model/l2/modelo.py`).
  - **B. Torres y opciones.** Los vectores int8 de ESQUEMAS o las torres de PyTorch en fp32.
  - **C. Prototipos.** Los int8 de CONJ o los de `modelo.prototipos` en fp32.
  - **D. simproto.** La réplica en Python de la versión int8 de `server/decide` o la de referencia en float.
  - **E. L0.** El L0 de Chispa del `.chispa` (su runtime: usa el binario del servidor o el entrenador Go en modo predicción,
    lo que exista) o el L0 de sklearn de `conjunta.py`, cada uno con la cabeza entrenada sobre ese mismo L0.
  - **F. Entradas del servidor.** El campo `pred.jsonl` del servidor, si trae las probabilidades, frente a la
    reconstrucción del arnés. Sirve para ver si el servidor hace algo distinto del arnés.
- Corridas, en massive y clinc150, con macro-F1 de `chispa_eval`:
  1. **todo «servidor»**: debe reproducir el 0,771 / 0,846 ±0,5;
  2. **todo «referencia»**: debe reproducir el 0,817 / 0,890 ±0,5. **Si 1 o 2 no se reproducen, el arnés está mal: dilo
     y no saques conclusiones;**
  3. **una sustitución cada vez**, de servidor a referencia, en A–E.
- Tabla por tarea: Δ de cada sustitución y el culpable o culpables si alguno pasa de 3 puntos.
- `server/deploy/ablacion/aws.sh`: user-data de una c6a.xlarge spot con el patrón de `server/deploy/aws/e2e.sh`:
  - marcador `__CHISPA_S3__`, `shutdown -h +75` y un trap que sube `log.txt` y `resultados.tgz`;
  - descargas por fichero;
  - reconstruye lo que hace falta como en `e2e.sh`: datos, checkpoint `l2-20261028b/ckpt/mejor.pt`, exportación con los
    valores por defecto actuales y `chispa train --conjunta` en las dos tareas;
  - arranca el servidor para obtener las predicciones del modo «forzado» y corre el arnés.
  - Reusa funciones de `e2e.sh` copiando lo mínimo. No cambies `e2e.sh`.
  - Empaquetado con `find` y `tar` portables, sin `-C` combinado con `-T`, porque también se ejecuta con bsdtar.
- **Prueba en seco aquí**, con fixtures y un `.chispa` pequeño generado en la VM:
  - las corridas 1 y 2 coinciden consigo mismas por construcción en los fixtures;
  - tests en `server/deploy/ablacion/test_ablacion.py`;
  - `bash -n` del script.
- `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `server/deploy/ablacion/**`. El resto es de lectura.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, Python en `~/venv` y modelos en `~/hf`. Sin GPU, sin S3 y sin red salvo la
  API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- la prueba en seco;
- qué sustituyo para lanzar `aws.sh`;
- qué no se pudo reconstruir offline, si hay algo.
