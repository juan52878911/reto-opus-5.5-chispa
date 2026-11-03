# Despliegue mínimo: del CSV del cliente a `/v1/decide` en un día

Piloto **few-shot con datos del cliente**, sin cambiar `server/`. Todos los comandos de esta guía se corrieron con datos sintéticos
(`pilotos/esquemas/` y filas inventadas; ninguna es de un cliente) en un PC de pruebas con Go 1.27 y Python 3.14, **sin** potion, sin
checkpoint de L2 y sin ONNX Runtime. Lo que no se pudo correr va en [Huecos](#huecos-hoy-sin-tocar-server) y no se promete.
Guía larga: [`guia-integracion.md`](guia-integracion.md); runbook: [`operacion.md`](operacion.md); checklist: [`checklist-despliegue.md`](checklist-despliegue.md).

## Lo que se entrega hoy y lo que no
| Capa | ¿Hoy, en un día? | Cómo sale |
|---|---|---|
| **L0** (TF-IDF de caracteres + logística, entrenador de Go) | **Sí**, una por pregunta | `chispa train --ejemplos` con **≥ 10 ejemplos por opción** |
| **L1** (potion) | Solo si ya hay `potion.chispa-l1` (155 MB, `runtime/l1/exportar.py`, necesita bajar el modelo) | `--l1 potion.chispa-l1` en **uno** de los ficheros |
| **L0TF + L2c** (`--conjunta`) | **No sin el equipo de Chispa**: necesita ≥ 20 por opción, `--ckpt` (checkpoint de L2, no está en el repo), `--l2`, torch y scikit-learn | ver [Huecos](#huecos-hoy-sin-tocar-server) |
| Torre al vuelo (`TORR`), L2 | No: necesita ONNX Runtime, `-tags ort` y `-tok` | fuera de este día |

## 0. Requisitos
- Go y Python ≥ 3.9 con PyYAML. Desde la raíz del repo: `export PYTHONPATH=sdk/python`.
- `chispa train` necesita Go para L0 (usa las fuentes de `sdk/python/chispa/entrenador_go/`); sin Go avisa y no escribe L0.
- El CSV del cliente, **anonimizado** ([`datos-y-consentimiento.md`](datos-y-consentimiento.md)): columnas `texto` y `etiqueta`; cada `etiqueta` es el id de una opción del esquema.
  Las plantillas de `pilotos/esquemas/ejemplos/` traen 5 por opción: **sirven para el cableado pero con < 10 no se entrena L0** (el `.chispa` sale solo con META + CALIB y no decide nada sin L1).
- Un esquema YAML por pregunta (copie una plantilla de [`esquemas/`](esquemas) y ajuste los ids y las descripciones). Los ids de opción no llevan tildes ni espacios.

## 1. Entrenar L0 por pregunta
Un `.chispa` por pregunta (los ids de opción de dos preguntas **no pueden coincidir en conjunto**: ver paso 2).
```
python -m chispa train --ejemplos ej_tipo.csv    --esquema esq_tipo.yaml    --salida tipo.chispa    [--l1 potion.chispa-l1]
python -m chispa train --ejemplos ej_urgencia.csv --esquema esq_urgencia.yaml --salida urgencia.chispa
```
- Con un YAML de varias preguntas (`preguntas: [...]`, como las plantillas): añada `--pregunta ID`.
- Salida esperada (dato sintético, 12 ejemplos por opción): `.../tipo.chispa: META+L0+CALIB, 3077 bytes, L0 validación 1.000, 0.7 s` y
  `capas del .chispa: L0 sí, L1 no, L2 no, torre al vuelo (TORR) no`. Los `AVISO` de «sin L1», «sin L2» y «sin TORR» son los esperados en este modo.
- La «L0 validación» sale de una parte aparte de los ejemplos (`--frac-valid`, 0,2 por defecto): con pocas filas es ruidosa; mida con la muestra del cliente ([`metrica.md`](metrica.md)).
- Ponga `--l1` solo en **un** fichero (el primero del paso 2): L1 pesa 155 MB y en la unión gana la primera sección repetida.
- Un `noul` o un `score` también entrenan L0 (`score`: ids `"1"`…`"K"`, **sin medir**), pero lo ya probado aquí es `choice`.

## 2. Unir en un solo `.chispa` (L0MULTI)
`chispa-server` abre **un** `-modelo`. `mkmodelo -unir` junta los L0 de todos los ficheros en una sección `L0MULTI`, uno por pregunta:
```
cd server
go run ./deploy/mkmodelo -unir ../tipo.chispa,../urgencia.chispa -out ../cliente.chispa
cd ..
sha256sum cliente.chispa > cliente.chispa.sha256
```
Salida (resumida): `sección META en … y en …: gana la primera`, `sección CALIB en … y en …: gana la primera`. Es normal: META, CALIB y L1 son los del **primer** fichero.
Dos L0 con el mismo conjunto de etiquetas hacen fallar la unión y nombran los dos ficheros. Un servidor anterior a `L0MULTI` rechaza el resultado con `ErrTipo`.
Con una sola pregunta no hace falta unir: sirva `tipo.chispa` tal cual.

## 3. Configuración mínima
- **Sin `-config`** y en loopback (`127.0.0.1`, el defecto) arranca con los τ de `CALIB` y sin claves (avisa «arranque sin claves de API»). Vale para el cableado local.
- **Fuera de loopback** el servidor **no arranca sin claves** (`-abierto` lo permite; no lo use en el piloto). Config mínima con una clave:
```
printf '%s' "$CLAVE" | ./chispa-server -hash-clave        # imprime el SHA-256; guarde $CLAVE en el gestor de secretos
```
```json
{"api_keys": [{"id": "piloto", "hash_sha256": "<64 hex de -hash-clave>", "rps": 20}]}
```
  (probado: sin cabecera da 401; con `Authorization: Bearer $CLAVE`, 200.) Claves desconocidas hacen fallar el arranque. Con `-config`, los `capas[].tau` que escriba **pisan** los de `CALIB`;
  si solo quiere claves, no ponga `capas`. Resto de claves y límites: [`operacion.md` §3](operacion.md#3-configuración--config) y [`docs/09`](../docs/09-despliegue-piloto.md).
- TLS no existe en el servidor: lo pone el proxy del cliente.

## 4. Arranque y comprobación
```
cd server && go build -o chispa-server ./cmd/chispa-server && cd ..
server/chispa-server -addr 127.0.0.1:8090 -modelo cliente.chispa [-config config.json]
```
El log debe decir `chispa-server en 127.0.0.1:8090: 2 modelos en L0` (2 = las preguntas unidas) y, sin ORT, `capas efectivas: L0(2 modelos); sin modelo: L1, L2, L3 …`.
```
curl -s localhost:8090/healthz
# {"status":"ok","capas":{"L0":true,"L1":false,"L2":false,"L3":false},"torre_al_vuelo":false}
```
`healthz` solo dice que el proceso vive y qué capas tienen modelo.

## 5. Primera llamada a `/v1/decide`
La pregunta y los ids deben ser **los del entrenamiento** (con L0 few-shot, el servidor busca el L0 cuyas etiquetas coinciden con las opciones):
```
curl -s localhost:8090/v1/decide [-H "Authorization: Bearer $CLAVE"] -d '{"state":"me cobraron dos veces la cuota","questions":[
 {"id":"q1","question":"¿Qué tipo de mensaje es?","kind":"choice","options":[{"id":"peticion"},{"id":"queja"},{"id":"reclamo"}]}]}'
# {"results":[{"id":"q1","kind":"choice","answer":"reclamo","probs":{…,"reclamo":0.99…},"layer":"L0","escalate":false,"ms":0.02}]}
```
Una petición puede llevar varias preguntas (cada una la decide su L0). `chispa decide` manda solo ids, sin descripciones, y no envía clave.
Un esquema que el `.chispa` no trae y que ningún L0 reconoce **escala** (`escalate_reason`: `sin_opinion` o `esquema_no_entrenado`).

## 6. Medir
Con las filas de evaluación **aparte** de las de entrenamiento, un JSONL de casos y [`medir.py`](medir.py) (solo stdlib):
```
python3 pilotos/medir.py --url http://127.0.0.1:8090 --casos casos.jsonl --salida informe-humo   # CHISPA_CLAVE=… si hay claves
python3 -m unittest discover -s pilotos -p 'test_medir.py'
```
Formato del caso, métricas y cómo pegar la tabla en [`plantilla-informe.md`](plantilla-informe.md). (`chispa evaluar` hace lo mismo desde un CSV, pero no manda clave de API.)
Corrida de ejemplo sobre el `cliente.chispa` sintético: 12 casos, exactitud 1,000, 100 % en L0 (las filas salen del entrenamiento: solo prueba el cableado, no mide nada).

## 7. Volver atrás
1. Antes de cambiar nada, guarde `cliente.chispa` con fecha (`cliente-AAAAMMDD.chispa`) y su `sha256`.
2. Modelo nuevo con **otro nombre**, probado en un puerto auxiliar (`-addr 127.0.0.1:18090`); luego `mv` (nunca `cp` sobre el abierto) sobre la ruta de `-modelo` y recarga en caliente:
   `kill -HUP <pid>` o `POST /v1/admin/recargar` con `admin_token_sha256` en la config.
3. Si la recarga falla, el modelo viejo **sigue sirviendo**: probado con un fichero truncado, el log dice `recarga fallida, sigue el modelo 1: chispa3: fichero truncado…`, `chispa_recargas_total{resultado="error"}` sube y `/v1/decide` sigue dando 200.
4. Si la recarga sale bien pero el modelo es peor: `mv cliente-AAAAMMDD.chispa cliente.chispa` y otro `kill -HUP` (probado: `chispa_recargas_total{resultado="ok"}` sube; el log dice `modelo N en servicio`).
5. Apagado: `SIGTERM`; espera las peticiones en vuelo hasta `-apagado` (25 s). El resto del runbook, en [`operacion.md`](operacion.md).

## Huecos (hoy, sin tocar `server/`)
Hipótesis: «un piloto few-shot se arranca en un día con `chispa-server` tal cual». **Se cumple para L0** (y L0 + L1 si ya hay potion). **No se cumple para L0TF + L2c**, y la causa no está en `server/` sino en el entrenamiento:
1. **L0TF solo se escribe con `--conjunta`**, y `--conjunta` exige `--ckpt` (probado: `chispa: --conjunta necesita --ckpt: las características salen del modelo de L2, no del ONNX`), `--l2`, torch y ≥ 20 ejemplos por opción
   (con menos «cae a few-shot» sin L0TF). No hay orden suelta que entrene un L0TF sin checkpoint (`sdk/python/chispa/train.py`, `conjunta.py`, `l0tf.py`). El servidor sí lo sirve si el `.chispa` lo trae; lo que falta es producirlo sin el checkpoint.
2. **L2c** (CONJ) y la torre al vuelo necesitan además ORT, `-tags ort` y `-tok e5.chispa-tok`: no se compiló ni corrió aquí.
3. **potion** (`potion.chispa-l1`) no está en el repo: `runtime/l1/exportar.py` lo genera y necesita red. Sin él, un `.chispa` solo-L0 escala todo lo que no reconoce.
4. **Las plantillas traen 5 ejemplos por opción** (< 10): no entrenan L0. El cliente necesita ≥ 10 por opción (≥ 20 para `--conjunta`).
5. **Calibración y unión**: en `-unir` la CALIB (τ) es la del primer fichero; los τ de L0 de las demás preguntas no se calibran por separado. Ajústelos con la muestra del cliente (`capas[].tau` en `-config`).
6. **Sin medir:** el efecto de unir muchas preguntas en latencia y RAM; `score` y `noul` en L0 sobre datos del cliente; la imagen OCI y kindling (no hay Docker en el nodo).
