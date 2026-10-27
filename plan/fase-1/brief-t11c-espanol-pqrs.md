# T1.1c Conversores de datos de libre uso en español y PQRS reales de Colombia

Encargo: `plan/fase-1/encargo.md` (ver su sección de cambios del 2026-10-27). Esquema: `model/esquema.md`,
congelado. Sigue el patrón de `model/datos/`: un módulo por fuente, `validar.py` y `LICENCIAS.md`.

## Hipótesis
- Todas las fuentes de abajo están en el dorado y se llevan al esquema con un módulo pequeño cada
  una. Las PQRS de datos.gov.co se pueden anonimizar con reglas, sin perder el tipo ni el sentido.
- Se refuta si una fuente no está, no tiene licencia comercial en su tarjeta primaria, o si la
  anonimización deja nombres visibles en una revisión de 100 filas.

## Fuentes, en `~/hf` y en `~/datos/datosgov/`
| Fuente | Tarea | Tipo |
|---|---|---|
| SINAI/ALIA-es-discriminative-hate-speech | `odio` | noul |
| bgonzalezbustamante/toxicity-protests-ES y toxicity-Constitution-ES | `toxicidad` | noul o score según traigan; con el consenso como `etiqueta` |
| mrm8488/go_emotions-es-mt | `emocion` | choice, 28 clases; si es multietiqueta, la primera o «neutral», dilo |
| tanaos/synthetic-spam-detection-dataset-spanish | `spam` | noul |
| tasksource/it-support-tickets | `soporte_ti` | choice; el texto puede estar en inglés, marca `idioma` |
| FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1 y _2 | `ciberacoso` | noul, `idioma: es-CO` |
| somosnlp/suicide-comments-es, somosnlp/spa_climate_detection | `riesgo_suicida`, `clima` | noul; solo si están |
| datos.gov.co gb9w-jt96, e86p-frfd, xtj2-ipwy | `pqrs` | choice: petición, queja, reclamo, sugerencia, denuncia, felicitación… con el mapeo del campo «tipo» documentado |
| datos.gov.co m3mt-c275 | `pqrs_enrutamiento` | choice sobre dependencia (≤ 30 clases más frecuentes y «otra») |

## Terminado cuando
- **Licencias:** lee la licencia de cada fuente en su tarjeta (README del snapshot o
  `*.meta.json` de datos.gov.co) y anótala en `LICENCIAS.md`. Aplica la regla de siempre: NC, ND o
  sin verificar → `uso_comercial: false`, solo test. CC BY-SA marca `licencia` con SA.
- **Anonimizar PQRS** (`model/datos/anonimizar.py`), antes de escribir ninguna fila:
  - reemplaza nombres propios de persona, cédulas o números de 6+ dígitos, teléfonos, correos,
    direcciones («calle», «carrera», «cra», «#») y placas por `[NOMBRE]`, `[DOC]`, `[TEL]`,
    `[CORREO]`, `[DIR]` y `[PLACA]`;
  - para nombres usa listas de nombres y apellidos comunes en Colombia escritas a mano en el código
    (≥ 300) más heurística de mayúsculas tras «señor/a», «yo», «me llamo», «firma»;
  - tests con frases inventadas;
  - informe: cuántos reemplazos por tipo y, en 100 filas al azar, cuántas aún parecen tener un
    nombre (cuéntalas, **no las copies**).
- **Datos reales fuera del repo:** no metas ninguna fila real de PQRS en el repo, en tests ni en el
  informe; los fixtures son inventados. Las salidas convertidas van a `/tmp` y no a git.
- **Reparto:** train/dev/test 80/10/10 con semilla fija; en PQRS, test estratificado por tipo.
- **Recuento:** una tabla de filas por fuente y split en el informe.
- **Tests y verificación:** tests por fuente con fixture inventado; `python -m unittest discover
  -s model -t .`, `make test` y `make smoke` en verde.
- **Parada:** si una fuente falla 2 veces, márcala «no convertida» y sigue.

## Zona
- `model/datos/` (módulos nuevos y `LICENCIAS.md`; no rompas los existentes). **No tocar**:
  `model/esquema.md` ni otras carpetas.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, datos en `~/hf` y `~/datos/datosgov`. Sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 150 min de reloj · ≤ 8 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
≤ 15 líneas: qué cambiaste, rama y sha, tabla de filas por fuente y split con su licencia, cifras de
la anonimización, qué no se convirtió y por qué, qué recomiendas.
