# T2.6d: ASR de la Arena con la cascada nueva y curvas de cobertura de T2.4

`aws.sh` es el user-data de una c6a.xlarge spot (patrón de `../aws/e2e.sh`, que no se toca). El código sale de
`bash server/deploy/arena/empaquetar.sh > codigo.tgz` (el de e2e más `arena/`).

- **Detector:** `arena/internal/detectors/cascada.go`, `chispa-cascada`: adaptador HTTP a `POST /v1/decide`. `Decision.Label` es
  `answer` del servidor (o la de mayor probabilidad si escala sin respuesta) y `Escalate` es `escalate`. Si el servidor falla, escala y
  escribe `chispa-cascada: …` en stderr (aws.sh lo trata como fallo: el ASR no valdría).
- **Flag:** `arena run -cascada spam=http://…,injection=http://… [-solo-cascada]`. Sin el flag no cambia nada. Con él solo corren esas
  dimensiones, `chispa-cascada` se suma a los 4 detectores (o es el único con `-solo-cascada`) y el aprendizaje queda apagado.
- **Esquema:** pregunta y opciones de cada dimensión están en `esquemas.json` (entrenamiento) y en `cascada.go`; un test las compara.
- **Salida** (`resultados.tgz`): `asr-{solo,enjambre,base}/asr.{md,json}`, `ledger-*.jsonl.gz`, `curvas/{massive,herramientas,hatecheck}.{md,svg}`,
  `curvas/curvas.json`, `arena-*.txt`, `servidores/*.log`, `log.txt`.
- **Lectura del ASR.** En «solo» el número que cuenta es el del detector: el veredicto del enjambre de un único voto tiene su propia
  regla de escalado y no equivale a `escalate`. En «enjambre» cuenta el ASR del enjambre. «base» es el control con los 4 detectores y
  el aprendizaje apagado (el ASR del README se midió con el aprendizaje por defecto).
- **Ataques.** El README no da el total: son ~37.000 (10 s a 3.700/s), el valor por defecto de `CHISPA_ATAQUES`. En «solo» y «enjambre»
  se reparten entre 2 dimensiones; en «base», entre 6.
- Pruebas: `python -I server/deploy/arena/test_util.py`; en seco: `CHISPA_LOCAL=1 bash server/deploy/arena/aws.sh`.
