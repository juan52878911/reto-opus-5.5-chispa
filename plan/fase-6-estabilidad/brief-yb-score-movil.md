# yb YB Score solo con ids 1..K en el móvil: chispamovil, Kotlin y Swift

Encargo: Chispa es un clasificador tipado (choice/score/noul) de bajo coste y de propósito general, como Laya o Jev: decide sobre esquemas y opciones que no ha visto, en zero-shot o con pocos ejemplos. Cascada L0 (TF-IDF/logística) → L1 (Model2Vec en Go int8) → L2 (e5-small int8 ONNX con torres; la torre de un esquema nuevo se calcula al vuelo si el `.chispa` trae la sección TORR) → escalar. Formato `.chispa` v3 (`format/chispa3`), servidor Go `/v1/decide` (`server/`), SDKs Python (`sdk/python`), Android (`sdk/android`), iOS (`sdk/ios`) y motor móvil Go (`sdk/movil/chispamovil`). Se venderá en Colombia. massive, clinc, hatecheck, spam e injection son benchmarks.

**Contrato nuevo de score (decisión del responsable; anula la de R15 sobre el orden declarado):** una pregunta score solo es válida para una capa si sus ids son exactamente `1..K` (enteros canónicos, `strconv.Itoa(n)==id`, sin huecos ni repetidos, en cualquier orden en la petición). Los niveles se leen por valor numérico. Con cualquier otro conjunto de ids («bajo/medio/alto», «0..K-1», «01», «+1», huecos) la capa **no opina** y la cascada escala, con un motivo claro (p. ej. `motivo`/razón en la respuesta si existe ese campo, o el contador de métricas que ya haya para «no opina»; documenta cuál). Esto alinea el runtime con el entrenamiento en Python (`model/datos/comun.py` `niveles_score`, que rechaza esos ids). Hoy el runtime usa `tok.OrdenNivel` / `IdsEnteros` (`runtime/tok/orden.go`) y, si los ids no son enteros canónicos, conserva el orden declarado: eso desaparece. Tests: ids `1..K` en cualquier orden dan el mismo resultado; ids no canónicos no opinan en ninguna capa. Otro worker hace el mismo cambio en `runtime/tok` y el servidor en paralelo: **no dependas de él**; chispamovil tiene su propio `ordenNivel`/`idsOrdenados`.

## Hipótesis
Si chispamovil (L0, L1, ids de agregación, torre de consulta) y las capas de Kotlin/Swift (`Capas.kt`, `Capas.swift`, `Cascada.*`, `TextoLargo.*`) comprueban `1..K` antes de opinar, el móvil se comporta igual que el servidor; se refuta con tests por capa.

## Terminado cuando
- chispamovil: un helper propio (`nivelesScore(ids) ([]string, bool)`) usado en `ordinal` (L0), `puntuarNiveles` (L1), `idsOrdenados` (agregación) y en la torre de consulta de score; sin camino de orden declarado. Tests por capa con ids `1..K` permutados (mismo resultado) y no canónicos (no opina).
- Kotlin y Swift: donde decidan score por sí mismos (CORAL de L2 en `Capas.*`, agregación en `TextoLargo.*`), la misma comprobación; la capa no opina con ids no `1..K`. Tests unitarios en `sdk/android/chispa/src/test/**` y `sdk/ios/Tests/**`. No hay JDK ni Swift en el nodo: revisa a mano y dilo.
- **`escalate_reason`** con paridad con el servidor (`docs/03-api.md` y `server/decide`, solo lectura, en la base `sdk` ≥ `92b1707`):
  `sin_opinion` (ninguna capa opina), `baja_confianza` (alguna opina, pero por debajo de τ) y `score_ids_no_validos` (ids de
  score fuera de `1..K`). Va en el resultado de chispamovil y en los tipos públicos de Kotlin y Swift, con el mismo nombre de
  campo y los mismos valores que el servidor. Tests de cada motivo en chispamovil; en Kotlin y Swift, tests escritos y
  revisados a mano.
- **Tres tests de chispamovil que hoy fallan** (VF17 sobre `sdk` `92b1707`: 87 PASS, 3 FAIL, 1 SKIP) tienen que acabar en verde:
  - `TestTiposL2ParidadYCompatibilidad` y `TestTextosYDecisionIgualesAlServidor`: sus fixtures de score usan ids bajo/medio/alto,
    que el servidor ya no admite. Pásalos a `1..K`, o a «no opina» si el test trata justo de eso.
  - `TestTextoLargoL1ParidadConServidor`: el servidor no opina y el móvil sí. Con la regla `1..K` en el móvil tiene que
    coincidir.
- Verde: `cd sdk/movil/chispamovil && go vet ./... && go test -race -count=1 ./...` con `CHISPA_TOK=/tmp/e5.chispa-tok`.
- Parada: si algo falla 2 veces seguidas por la misma causa, manda `blocker` y para.

## Zona
- Escribe solo en `sdk/movil/**`, `sdk/android/**`, `sdk/ios/**`.
- **No tocar:** `runtime/**`, `server/**`, `sdk/python/**`, `docs/**` (otro worker en paralelo) y `model/**`, y siempre `model/**`, `arena/contracts/**`, `server/deploy/resultados/**` (de otra sesión).
- Reglas del CLAUDE.md del repo. Rama: la que te da delega. Commits simples, sin firmas ni Co-Authored-By. Sin push, PR
  ni merge. Nada de publicar paquetes ni subir nada a la red.
- Propiedad: Chispa es de Juan Bedoya. Autor y licencia de cualquier SDK o paquete: Juan Bedoya. Antes de commitear, pasa
  `delega scan` sobre tu rama (lo hace el orquestador al traerla) y comprueba `git config user.email`: debe ser
  user52878911@gmail.com.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, ORT en `~/ort` y el tokenizador e5 se construye con `runtime/tok/exportar.py` si
  hace falta para `CHISPA_TOK`. Para `-race` hace falta gcc (está en el dorado).
- No hay JDK ni Swift: revisa a mano Kotlin y Swift. Sin red salvo la API de Claude. No cargues `data/`, `models/` ni
  `data/ledger.jsonl`.
- Línea base: la rama con la que te lanza delega (`sdk`).

## Tope
- ≤ 60 min de reloj · ≤ 5 USD de cuenta · cómputo de pago: 0.
- Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas: rama y sha; por capa y plataforma: cambio y test; recuento de chispamovil; qué no se pudo compilar; qué quedó sin verificar.
