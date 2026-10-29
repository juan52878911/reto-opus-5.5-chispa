# R9 Arreglos del exportador: noul invertido y multi sin L2

## Antecedentes
La revisión R9 encontró dos fallos en `model/`.

1. **noul invertido.**
   - `model/l2/exportar.py` y `model/l2/modelo.py` (`texto_consulta`, que usa `fila["opciones"][-1]`) guardan en
     ESQUEMAS la torre de la **última** opción.
   - El runtime (`server/decide`, desde R3) interpreta esa entrada como la torre de `true`.
   - Con una pregunta noul cuyas opciones vengan como `[true, false]`, la decisión sale al revés.
2. **multi sin L2.** El exportador escribe una sola clave por pregunta en multi, y el servidor busca una por opción
   (ver `server/decide/multi.go`). Así L2 nunca opina en multi cuando usa ESQUEMAS precalculados.

## Terminado cuando
- **noul.**
  - El exportador elige siempre la opción `true` para la torre de noul, sea cual sea el orden de `opciones`.
  - Revisa también `texto_consulta` en `modelo.py`. Si cambiarlo altera el entrenamiento, no lo toques ahí y corrige
    solo la exportación. Explica la decisión.
  - En score, el criterio debe ser el «nivel máximo» de forma explícita, no la posición `[-1]`. Comprueba con el runtime
    qué espera.
  - Test: exporta una pregunta noul con `[false, true]` y otra con `[true, false]`, y comprueba que la clave y el vector
    guardados son los de `true`. Si se puede hacer sin ORT, añade también un test de paridad de decisión con el servidor
    en Go: un `.chispa` mínimo y el mismo texto deben dar la misma decisión en los dos órdenes.
- **multi.**
  - Lee `server/decide/multi.go` y sigue **exactamente** su convención de claves para multi: kind, opciones y
    HashEsquema2 por opción, o la que use.
  - El exportador escribe una entrada de ESQUEMAS por opción en multi.
  - Test de paridad: el servidor encuentra cada clave escrita por el exportador. Es un test Go en
    `model/l2/empaquetar_go` que use la función del servidor que construye la clave, o un fixture con las claves esperadas
    calculadas con esa función.
- `python -m unittest discover -s model -t .`, `go test` de `model/l2/empaquetar_go`, `make test` y `make smoke` en verde
  **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/exportar.py`, `model/l2/modelo.py` (solo si hace falta), `model/l2/empaquetar_go/**` y `model/l2/tests/**`.
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion`. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. Sin red salvo la API de Claude.

## Tope
- ≤ 60 min de reloj · ≤ 4 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- qué cambió en noul y en score;
- convención de multi;
- tests.
