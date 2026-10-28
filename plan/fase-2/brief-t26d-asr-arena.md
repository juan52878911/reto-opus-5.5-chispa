# T2.6d ASR de la Arena con la cascada nueva y curvas de cobertura de T2.4

## Antecedentes
- **ASR.** El criterio T2.6 (`plan/fase-2/encargo.md`) pide un ASR de la Arena ≤ 0,15 en spam e inyección. La Arena
  (`arena/`, README) ataca a un enjambre de detectores (`arena/internal/detectors`, interfaz `Detector`; servidor por
  detector `POST /decide_batch` en `internal/detsrv`) y mide el ASR por dimensión: un detector queda engañado si contesta
  mal sin escalar. Hoy hay 4 detectores por dimensión: chispa-words, chispa-char, chispa-sub y rules. La referencia es
  spam 0,09 / 0,16 e injection 0,30 / 0,18, con el enjambre y con el mejor detector solo.
- **Cascada nueva** (`model/informes/fase-2.md`, `server/`): L0TF → L2c, que es la cabeza conjunta sobre e5-small int8 y
  prototipos. Se entrena con `chispa train --conjunta`. `chispa-server -tags ort -tok e5.chispa-tok` sirve `/v1/decide`.
  `server/deploy/aws/e2e.sh` monta todo esto en una c6a.
- **Curvas de T2.4.** El criterio redefinido pide publicar la curva de cobertura donde el macro-F1 < 0,85: massive,
  herramientas y hatecheck. Las predicciones de la cabeza `cvtest` de T2.2d están en
  `s3://chispa-pruebas-879381269751/t22d-20261028/resultados.tgz` (`cvtest/pred/…`).

## Hipótesis
- H1: un detector «chispa-cascada» que llama a `/v1/decide`, con un `.chispa` entrenado por `chispa train --conjunta` en
  los datos de train de spam e inyección de la Arena, saca un ASR ≤ 0,15 en spam y en inyección. Se mide solo y dentro del
  enjambre. Se refuta midiendo.
- Sin hipótesis para las curvas: es publicar una medida.

## Terminado cuando
- `arena/internal/detectors/`: un detector `chispa-cascada`, adaptador HTTP a `/v1/decide`.
  - Mapea la decisión y `escalate` como espera la Arena.
  - Se activa con un flag; si no hay servidor, no cambia nada.
  - **No toques `arena/contracts/`**: está congelado. Si hace falta cambiar algo ahí, para y dilo.
  - Con tests.
- `server/deploy/arena/aws.sh`: user-data de una c6a.xlarge spot con el patrón de `server/deploy/aws/e2e.sh`. Copia lo
  mínimo y no cambies `e2e.sh`. Lleva:
  - marcador `__CHISPA_S3__`, `shutdown -h +75` y un trap que sube `log.txt` y `resultados.tgz`;
  - descargas por fichero;
  - `CHISPA_EXPORT_ARGS` admitido, igual que en `e2e.sh`.
  - Pasos:
    1. genera el dataset de la Arena (`make arena` o su paso de dataset) y saca train y test de spam e inyección;
    2. exporta L2 y corre `chispa train --conjunta` por dimensión;
    3. arranca `chispa-server -tags ort`;
    4. corre la Arena con el detector nuevo solo y en el enjambre, con el mismo número de ataques que en el README;
    5. calcula el ASR por dimensión;
    6. baja `t22d-20261028/resultados.tgz` y genera las curvas de cobertura (precisión frente a cobertura al barrer τ) de
       massive, herramientas y hatecheck: una tabla cada 5 % de cobertura y un SVG por tarea, con un script pequeño en
       Python incluido en `server/deploy/arena/`.
- **Prueba en seco aquí:**
  - tests Go de la Arena y del adaptador;
  - `CHISPA_LOCAL=1 bash server/deploy/arena/aws.sh` con fixtures y sin ORT (L2 en stub);
  - el script de curvas con unas predicciones inventadas;
  - `bash -n`.
- `make test` y `make smoke` en verde. Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `arena/internal/detectors/**`, `arena/cmd/**` (solo el flag) y `server/deploy/arena/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin` y Python en `~/venv`. Sin GPU y sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos en el contexto.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 12 líneas:
- rama y sha;
- la prueba en seco;
- qué sustituyo para lanzar `aws.sh`;
- qué quedó sin verificar.
