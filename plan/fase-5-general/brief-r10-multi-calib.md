# R10 CALIB `multi_l2` por esquema: que L2 opine en multi

## Antecedentes
- En multi, L2 solo opina si CALIB trae `multi_l2@<HashEsquema2 hex>` y, por opción, `multi_l2@<hex>#<id>`. Así lo exige
  `server/decide/multi.go` (léelo entero: `claveMultiL2`, `respuestaMultiL2` y el comentario sobre «multi@<hex>»).
- Antes reutilizaba la CALIB de noul, que no tiene sentido para el MaxSim de L2.
- `chispa train` del SDK no puede generarla sin ONNX ni torres.
- Desde R9 el exportador escribe en ESQUEMAS una entrada por opción para multi.

## Terminado cuando
- **`model/l2/calibrar.py`** (y, si hace falta, el exportador) calcula, para cada esquema multi presente en el dev o en
  los ejemplos que reciba:
  - el `maxsim_l2` por opción;
  - el ajuste de calibración que espera `multi.go`: lee qué parámetros usa (T, a, b o θ por opción) y cómo los combina;
  - las claves `multi_l2@<hex>` y `multi_l2@<hex>#<id>` exactamente como las arma el servidor, con el hex de
    `HashEsquema2` en minúsculas, si así lo hace el servidor.
- **El exportador** las escribe en CALIB junto con el resto.
- **Tests.**
  - Un test Go en `model/l2/empaquetar_go` importa `server/decide` (como `r9_test.go`), carga un `.chispa` exportado con
    un esquema multi y comprueba que L2 opina (sin el AVISO de `multi.go`) y que las claves coinciden.
  - Un test Python de la forma de las claves.
- `python -m unittest discover -s model -t .`, `go test` de `model/l2/empaquetar_go`, `make test` y `make smoke` en verde
  **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/calibrar.py`, `model/l2/exportar.py`, `model/l2/empaquetar_go/**` y `model/l2/tests/**`.
- No toques `server/`, `sdk/` ni `format/`.
- Rama: la que te da delega. Base: `integracion`. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. Sin red salvo la API de Claude.

## Tope
- ≤ 75 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- qué parámetros escribe por esquema y por opción;
- tests.
