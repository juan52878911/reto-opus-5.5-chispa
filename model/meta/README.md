# model/meta: datos de metaentrenamiento (T1.8)

Cuatro conversores al esquema `model/esquema.md` (sin cambiarlo). Los datos salen a JSONL.gz fuera de git.

| Módulo | Fuente | Tipo | Idioma | Licencia |
|---|---|---|---|---|
| `tasksource_jev.py` | tasksource/tasksource-jev-typed-decisions | choice, score, noul | en (mul en `multilingual/*`) | por fila; **solo `license_use == "commercial"`** |
| `synthetic_zeroshot.py` | MoritzLaurer/synthetic_zeroshot_mixtral_v0.1 | noul (hipótesis) | en (sin traducir) | apache-2.0 (la tarjeta lo confirma) |
| `pawsx_es.py` | google-research-datasets/paws-x `es` | noul «¿son paráfrasis?» | es | libre uso (tarjeta) |
| `sib200_es.py` | Davlan/sib200 `spa_Latn` | choice de 7 temas | es | cc-by-sa-4.0 (tarjeta) |

- PAWS-X: `texto` = frase 1 + `" [SEP] "` + frase 2 (`pawsx_es.SEPARADOR`).
- tasksource: el fragmento de `~/hf` trae solo metadatos (`sources.yaml`, manifiestos), **sin filas**; el conversor
  espera las columnas documentadas en el README del dataset (`state`, `question`, `kind`, `options`, `target`, `source`,
  `license`, `license_use`) en `data/*.parquet` (config `default`) o `full/*.parquet` (`CHISPA_TS_SUBDIR=full`).
  Descarta y cuenta las filas no comerciales, las tareas que `sources.yaml` marca como no comerciales y las que
  tocan GLiClass, XNLI o ANLI (o derivados: `comun.PROHIBIDOS`). `Salida` repite la comprobación al escribir.
- `python -m model.meta.convertir SALIDA [--solo tsjev,synzs,pawsx,sib200]` escribe `SALIDA/<fuente>/<split>-NNNNN.jsonl.gz`
  y `SALIDA/resumen.json`. `CHISPA_LIMITE=N` topa las filas por fuente (solo pruebas).
- AWS: `aws/arranque.sh` (user-data, c6a.xlarge) y `aws/empaquetar.sh` (codigo.tgz). Prueba en seco:
  `CHISPA_LOCAL=1 bash model/meta/aws/arranque.sh`.
- Tests: `python -m unittest discover -s model -t .`
