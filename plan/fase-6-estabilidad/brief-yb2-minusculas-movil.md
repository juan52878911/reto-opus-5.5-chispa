# YB2 Minúsculas como Go en Kotlin y Swift, y la tabla de diferencias del contrato

## Antecedentes
- La regla de normalización de mayúsculas está en `model/l2/contrato-normalizacion.md` y `docs/contrato-normalizacion.md`, con
  15 casos en `server/decide/testdata/normalizacion.json` y `model/l2/tests/fixtures/normalizacion.json`. Python y Go bajan a
  minúsculas **carácter a carácter con el mapeo simple**: «İ» → «i» y la sigma final → «σ».
- Kotlin y Swift todavía no:
  - Kotlin, con `lowercase(Locale.ROOT)`, da «i̇» (con punto combinante);
  - Swift, con `lowercased()`, da «ς» al final de palabra.
- Tu base ya trae YB: score `1..K` y `escalate_reason`, fusionado con la rama `sdk` `4b1afce`.

## Terminado cuando
- **Kotlin:** la normalización baja a minúsculas por punto de código con `Character.toLowerCase(codePoint)`.
- **Swift:** escalar a escalar con `properties.lowercaseMapping`, quedándose con un solo escalar (el primero si son varios).
- **Tests de Kotlin y Swift** con los 15 casos, leídos del JSON si el test ya lo lee o copiados. Como mínimo,
  «İSTANBUL ŞEHİR» → «istanbul şehir» y «ΟΔΟΣ ΑΘΗΝΩΝ» → «οδοσ αθηνων».
- **`docs/contrato-normalizacion.md`:** la sección de diferencias conocidas ya no dice que «İ» difiere. Las cuatro
  implementaciones (Python, Go, Kotlin y Swift) usan el mapeo simple carácter a carácter.
- **Sin regresiones en Go:** `cd sdk/movil/chispamovil && go vet ./... && go test -race -count=1 ./...` con `CHISPA_TOK`
  construido con `runtime/tok/exportar.py`; antes daba 93 PASS y 1 SKIP. Y `cd server && go test ./decide/...`.
- Parada: si algo falla 2 veces seguidas por la misma causa, para y dilo en el informe.

## Zona
- `sdk/android/**`, `sdk/ios/**` y `docs/contrato-normalizacion.md`.
- Rama: la que te da delega. Commits simples, sin firmas ni `Co-Authored-By`. Sin push, PR ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, ORT en `~/ort`. No hay JDK ni Swift: revisa Kotlin y Swift a mano y dilo. Sin red
  salvo la API de Claude. No cargues `data/`, `models/` ni `data/ledger.jsonl`.

## Tope
- ≤ 35 min de reloj · ≤ 3 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- el cambio en Kotlin y en Swift;
- los tests;
- el recuento de chispamovil;
- qué quedó sin compilar.
