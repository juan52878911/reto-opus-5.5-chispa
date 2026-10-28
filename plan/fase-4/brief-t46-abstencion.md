# T4.6 Abstención de la cascada con tráfico no adversarial

## Antecedentes
- **Arena.** En la Arena (`server/deploy/resultados/arena-20261028/LEEME.md`), el detector `chispa-cascada` saca un ASR de
  0,021, pero escala el 83 % de los ataques de spam y el 47 % de los de injection. Falta saber cuánto escala con tráfico
  normal.
- **Prueba de punta a punta.** En `server/deploy/resultados/e2e-20261028-l0tf/informe.md`, modo cascada, la fila «L3» es
  la fracción que ninguna capa aceptó con su τ, es decir, la que escala: 43 % en massive y 46 % en clinc150. Hoy el
  macro-F1 de ese informe cuenta la mejor respuesta incluso cuando escala.
- **τ.** Las τ salen de CALIB (`tau_escalate`, el que da precisión 0,95), por `server/decide/modelo.go`
  (`ArmarDesde`, `tauDeCalib`).

## Hipótesis
- H1: con tráfico normal (test limpio), la cascada escala ≤ 30 % en las tareas con macro-F1 ≥ 0,85 (clinc150 y spam e
  injection de la Arena) y mantiene una precisión ≥ 0,95 en lo que contesta. Se refuta midiendo.
- H2: la abstención frente a la precisión se puede elegir por τ. La curva da, para cada tarea, el τ con abstención ≤ 20 %
  y la precisión que cuesta.

## Terminado cuando
- `server/deploy/abstencion/medir.py`: dado el `pred.jsonl` del servidor en modo cascada (con `escalate`, capa y
  probabilidades), calcula por tarea:
  - la fracción que escala;
  - la precisión y el macro-F1 **solo sobre lo contestado**;
  - el macro-F1 contando lo escalado como fallo;
  - la curva τ → (abstención, precisión) barriendo τ sobre las probabilidades devueltas: tabla cada 5 % de abstención y
    un SVG.
  - Tests con predicciones inventadas.
- `server/deploy/abstencion/aws.sh`: user-data de una c6a.xlarge spot que reutiliza lo mínimo de
  `server/deploy/aws/e2e.sh` y de `server/deploy/arena/aws.sh`, sin cambiarlos. Lleva:
  - marcador `__CHISPA_S3__`, `shutdown -h +75`, un trap que sube `log.txt` y `resultados.tgz`, y descargas por fichero;
  - `CHISPA_EXPORT_ARGS` admitido.
  - **≤ 16 KB.** Si no cabe, el orquestador lo comprime con gzip, pero mejor que quepa.
  - Pasos:
    1. `.chispa` de massive, clinc150 y de spam e injection de la Arena, como en esos scripts;
    2. el servidor en modo cascada con τ de CALIB;
    3. el test limpio completo de cada tarea por `/v1/decide`; en la Arena, el split de test sin ataques;
    4. `medir.py`.
- **Prueba en seco aquí:** `CHISPA_LOCAL=1 bash server/deploy/abstencion/aws.sh` con fixtures y sin ORT, `bash -n` y
  los tests.
- `make test` y `make smoke` en verde. Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `server/deploy/abstencion/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin` y Python en `~/venv`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto.

## Tope
- ≤ 90 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- la prueba en seco;
- qué sustituyo para lanzar `aws.sh` y su tamaño en bytes;
- qué quedó sin verificar.
