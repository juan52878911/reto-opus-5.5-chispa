# G.1 JevBench público con la cascada, como lo usaría un cliente nuevo

## Antecedentes
Juan, el 2026-10-28: «Estas son pruebas para su funcionalidad, no un objetivo. Recuerda que debe ser multipropósito como
Laya o Jev mismo». Chispa tiene que decidir sobre esquemas que nunca vio, sin ejemplos o con pocos. El criterio de la fase
2 incluye **JevBench público ≥ 0,55** (el nivel de Qwen3-0.6B sin entrenar), que sigue sin medir.

- JevBench: <https://github.com/fstandhartinger/jevbench>, 231 decisiones públicas, en inglés y con licencia MIT para el
  arnés.
- Adaptador: `model/evaluacion/jevbench.py`. Su formato de volcado es inventado («hasta ver el real»).
- L2: checkpoint `s3://chispa-pruebas-879381269751/l2-20261028b/ckpt/mejor.pt`, con `model/l2/evaluar.py` (`--soporte`).
- La cascada se arma con `chispa train` (`sdk/python/chispa/`) y se sirve con `chispa-server`.
- Patrón de AWS: `server/deploy/aws/e2e.sh` y `model/l2/aws/arranque.sh`.

## Hipótesis
- H1: L2 zero-shot, sin soporte, saca ≥ 0,55 de exactitud en JevBench público. Se refuta si queda por debajo.
- H2: con k ejemplos por opción, la cascada que montaría un cliente mejora a L2 zero-shot. La cascada es `chispa train`
  sin `--conjunta` (L0 de Chispa más L2 con soporte), y la conjunta solo como modo opcional.
  - Si JevBench no trae ejemplos aparte, el soporte sale de los demás casos con el mismo esquema, dejando fuera el caso
    evaluado.
  - Si algún esquema no tiene k casos, se mide con los que haya y se dice.
  - Lo que no se pueda hacer limpio, dilo y no lo fuerces.

## Terminado cuando
- `model/evaluacion/jevbench.py` lee el formato **real** del repo de JevBench. Bájalo aquí; este host tiene red. Con tests
  sobre un fixture pequeño copiado del repo, si la licencia lo permite. Si no, uno sintético con la misma forma.
- `model/evaluacion/aws/jevbench.sh`: user-data de una c6a.xlarge spot (CPU basta para 231 casos) con el patrón de siempre:
  - marcador `__CHISPA_S3__`, `shutdown -h +60` y un trap que sube `log.txt` y `resultados.tgz`;
  - descargas por fichero, ≤ 16 KB.
  - Pasos:
    1. clona JevBench;
    2. L2 zero-shot;
    3. L2 con soporte k = 8 y k = 32, dejando fuera el caso;
    4. la cascada de `chispa train` sin `--conjunta` con k = 8 y k = 32 por esquema, servida por `chispa-server -tags ort`
       como en `e2e.sh`;
    5. el informe: exactitud y macro-F1 por variante, cobertura y escalado, y comparación con 0,55.
- Prueba en seco: tests, `CHISPA_LOCAL=1` con fixtures y `bash -n`.
- Tests de Python y recetas de `make`: el venv y Go están en `~/orquestador/herr` (`. ~/orquestador/herr/env.sh`).
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/evaluacion/**`.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Tope
- ≤ 90 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- el formato real;
- cómo se arma el soporte;
- qué sustituyo para lanzar;
- qué quedó sin verificar.
