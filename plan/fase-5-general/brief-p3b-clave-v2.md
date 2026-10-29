# P3b Exportador con la clave v2 acordada (`HashEsquema2`) y cabeceras v2 de ESQUEMAS y CONJ

## Antecedentes
P3 (rama base `p3-v2`) implementó una clave equivocada:
- usó `HashEsquema(pregunta, [opción, descripción])`;
- guardó la versión en `META.version`.

La clave acordada con el runtime ya está en esta base (T3):
- `format/chispa3/clave2.go`: `HashEsquema2`, que es
  `sha256(pregunta · 0x1f · kind · 0x1f · por cada opción ordenada por id: id · 0x1e · descripción · 0x1d)` truncado a
  16 bytes;
- los vectores en `format/chispa3/vectores-clave-v2.json`, 5 en total;
- el escritor en Python en `sdk/python/chispa/formato.py`: `hash_esquema2`, `esquemas(dim, entradas, version)` y
  `conj(entradas, version)`.

## Terminado cuando
- **ESQUEMAS v2.** `model/l2/exportar.py` (y `empaquetar_go/`, si es quien escribe) escribe ESQUEMAS v2:
  - primer u32 = `(2<<16 | dim)`;
  - claves de 16 bytes con `HashEsquema2`;
  - choice: una entrada por opción, con `kind = "choice"`;
  - noul y score: una por pregunta, con la lista de opciones.
  - Mira cómo lo lee `format/chispa3` y aprovecha `formato.esquemas(..., version=2)` o la API Go de chispa3.
- **CONJ v2**, donde se escriba en `model/**`: `versión = 2` y claves de 16 bytes. **SOPL1 sigue con la clave v1.**
- **Deshacer lo de P3:** quita la clave `HashEsquema(pregunta,[opción,descripción])` y el uso de `META.version` como
  versión de la clave.
  - Regenera `model/l2/tests/fixtures/esquemas-v2.chispa` y su JSON con el formato correcto, y verifica que chispa3 lo
    abre (`go test` con un test pequeño en `model/l2/empaquetar_go`, o el lector de Python).
  - Actualiza `contrato-torre.md` y `model/l2/README.md`; `docs/04-formato-chispa.md` ya lo explica T3.
- **Test:** reproduce los 5 vectores de `format/chispa3/vectores-clave-v2.json` desde el código del exportador.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/l2/**` y `model/bench/**`.
- No toques `format/`, `server/` ni `sdk/`.
- Rama: la que te da delega. Base: `p3-v2`. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin` y modelos en `~/hf`. Sin red salvo la API de Claude.

## Tope
- ≤ 60 min de reloj · ≤ 4 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 8 líneas:
- rama y sha;
- vectores (5 de 5);
- fixture;
- tests.
