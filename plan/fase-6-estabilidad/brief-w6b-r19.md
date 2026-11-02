# W6b Torre v2: descripciones repetidas, versión en el ONNX y `empaquetar_go` con `MetaTexto` (R19)

## Antecedentes
- W6 (integrado) dejó el texto de torre v2 en `model/l2`: `texto_opcion` y `texto_consulta` con versión, el checkpoint con
  `texto_torre`, el exportador, el fixture `model/l2/tests/fixtures/texto_torre_v2.json` (13 casos) y `ajuste.sh` con
  `CHISPA_TEXTO_TORRE`.
- **Faltan tres cosas** que la revisión R19 de la otra sesión pidió y que el orquestador decidió. Las tres están en
  `model/l2/contrato-torre.md`, sección «Texto de torre versión 2». Léela entera.
  1. **Descripciones repetidas (R19-9).** En v2, si dentro de una misma pregunta dos o más opciones tienen la misma
     descripción (igualdad exacta tras `strip()`), **esas opciones usan el texto v1**, con id. Solo esas.
  2. **Versión en la metadata del ONNX de la torre:** `chispa.torre.texto_torre` (`"v1"` o `"v2_sin_id"`), junto a
     `chispa.torre.{dim,max_len,prefijo}`. `chispa train` (sdk ≥ `4f4b707`, ya en tu base) la compara con
     `META.texto_torre` y falla si no coinciden.
  3. **`model/l2/empaquetar_go/main.go` (R19-3).** Hoy valida META con `DecodificarMeta` y reinserta `texto_torre` a mano.
     Desde la base actual, `format/chispa3/secciones.go` tiene `MetaTexto` (con `Codificar` y `VersionTextoTorre`) y su
     decodificador: úsalos y quita la reinserción manual.
- **El runtime ya tiene su fixture** de 15 casos, generado con la regla del contrato: `server/decide/testdata/texto_torre_v2.json`.
  La otra sesión le añadirá casos de descripciones repetidas.

## Terminado cuando
1. `texto_opcion` y `texto_consulta` aplican la regla de descripciones repetidas en v2. Con v1 no cambia nada (lo cubren los
   tests de W6).
2. `model/l2/tests/fixtures/texto_torre_v2.json` incluye:
   - los 15 casos de `server/decide/testdata/texto_torre_v2.json`. Si alguno no coincide con `texto_opcion`, **dilo en el
     informe con el caso concreto**: no cambies ninguno de los dos lados sin explicarlo;
   - casos nuevos de descripciones repetidas: dos iguales, iguales salvo espacios en los extremos y tres opciones con dos
     iguales, en choice y en multi.
   - Un test compara todos los casos con `texto_opcion`.
3. El exportador escribe `chispa.torre.texto_torre` en el ONNX de la torre (`--torre-onnx`), con la versión del
   checkpoint. Test: un checkpoint v2 da un ONNX con `v2_sin_id` y un `l2.chispa` con `META.texto_torre = v2_sin_id`.
   **Prueba de punta a punta** con `chispa train --ckpt <ckpt v2 aleatorio> --torre <onnx>`, que debe dar un `.chispa` con
   `texto_torre = v2_sin_id`. Además, con un ONNX v1 y un checkpoint v2, `chispa train` debe fallar.
4. `empaquetar_go` usa `MetaTexto`, sin reinserción manual. `go test` de `model/l2/empaquetar_go` en verde.
5. Los llamadores de `texto_opcion` fuera de `model/l2` que W6 dejó en v1 (`model/bench/torre/movil.py` y
   `paridad_servidor.py`) pasan la versión del checkpoint.
6. Prueba en seco de `ajuste.sh` con `CHISPA_TEXTO_TORRE=v2_sin_id`, sin `FALLO`.
7. `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde **después** del último cambio. Si
   `make smoke` falla por un puerto ocupado, repítelo una vez y anótalo.
- Parada: si algo falla 2 veces, márcalo y para. **No lances nada en AWS.**

## Zona
- `model/l2/**` (salvo `resultados/`) y `model/bench/torre/**`.
- No toques `server/`, `sdk/` ni `format/` (solo lectura).
- Rama: la que te da delega. Base: `integracion-limpia`. Commits simples, sin firmas ni `Co-Authored-By`. Sin push ni
  merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, Go en `~/go-sdk/bin`, ORT en `~/ort`, modelos en `~/hf` y datos en `~/datos`. Sin
  red salvo la API de Claude.

## Tope
- ≤ 60 min de reloj · ≤ 4 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- casos del fixture y las discrepancias con el del runtime;
- la prueba de punta a punta;
- `empaquetar_go`;
- la tabla de `estado.tsv`.
