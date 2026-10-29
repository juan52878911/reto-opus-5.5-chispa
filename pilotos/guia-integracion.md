# Guía de integración: de cero a `/v1/decide` en su sistema

Para el equipo de TI del cliente y el responsable técnico de SDK. Los comandos salen de [`docs/`](../docs) y de
[`sdk/python/chispa/cli.py`](../sdk/python/chispa/cli.py) y se corren desde la raíz del repositorio. En el nodo donde se escribió esta guía no hay Go:
**los comandos de compilación y de servidor no se ejecutaron**; sí se comprobó que `python -m chispa train --help` y `decide --help` muestran los flags usados aquí.
Cifras y límites: [`docs/07`](../docs/07-rendimiento-y-limites.md); lo que Chispa todavía no hace, en [`README.md`](README.md#pendiente-de-producto).

## 0. Antes de empezar
1. Cierre el checklist de [`datos-y-consentimiento.md`](datos-y-consentimiento.md): sin autorización de tratamiento no se usan mensajes reales.
2. Elija **un** esquema para empezar: PQRS, soporte o ventas ([`esquemas/`](esquemas)). Un `.chispa` sirve una pregunta.
3. Decida dónde corre el servidor (paso 3).

## 1. Requisitos (docs/02)
- Python ≥ 3.9 y PyYAML (`pip install pyyaml`) para los esquemas `.yaml`. Los comandos de Python van con `PYTHONPATH=sdk/python` o tras `pip install ./sdk/python`.
- El potion exportado: `python runtime/l1/exportar.py` produce `potion.chispa-l1` (155 MB). Sin él, el zero-shot falla porque no habría ninguna capa.
- Go, para el entrenador de L0 y para compilar `chispa-server`. Sin Go, `chispa train` escribe META + L1 + CALIB y no lleva L0, y se usa la imagen OCI (paso 3).
- Modo avanzado (solo `choice`): torch, transformers, un checkpoint de L2 y e5. El repositorio no trae el checkpoint (pendiente de producto, ver el README).

## 2. Esquema (el que usará el cliente)
Copie una plantilla y ajuste las descripciones a su vocabulario (son lo que ve el zero-shot):
```
cp pilotos/esquemas/pqrs.yaml mi-esquema.yaml
```
Si el fichero trae varias preguntas, elija una con `--pregunta` (por ejemplo `pqrs_tipo`).

## 3. Levantar el servidor

### Compilar (on-prem, con Go)
```
cd server && go build -o chispa-server ./cmd/chispa-server
./chispa-server -addr 127.0.0.1:8090 -modelo ../zero.chispa
```
Variante con L2: `go build -tags ort ./cmd/chispa-server` (necesita cgo, `libonnxruntime.so` ≥ 1.17 y `-tok e5.chispa-tok`). Detalle en
[`docs/06`](../docs/06-despliegue.md). Con `-modelo` y sin `-config`, el τ sale de `CALIB`.

### Imagen OCI (on-prem o nube, sin Go en el servidor)
```
bash server/deploy/aws/empaquetar.sh > codigo.tgz
mkdir ctx && tar -xzf codigo.tgz -C ctx
docker build -f ctx/server/deploy/Dockerfile --build-arg ORT_VERSION=1.22.0 -t chispa-server ctx
docker run --rm -p 8090:8090 -v /ruta/modelos:/modelos:ro chispa-server
```
- Construir necesita red (baja ORT y `onnxruntime_go`). El `.chispa` va en `/modelos/modelo.chispa`; para `-tok` o `-config`, sustituya `CMD`.
- Tamaño de la imagen: sin medir. Nix: `nix build ./nix#chispa-server`, sin probar.

### Nube
Lo medido corrió en una instancia c6a.xlarge de AWS (4 vCPU, sin GPU) con el patrón de `arranque.sh` ([`docs/06`](../docs/06-despliegue.md#el-patrón-de-aws)).
Otras nubes: el contenedor es el mismo; no se ha probado en ninguna.

### Seguridad de red (pendiente del lado del cliente)
`chispa-server` no pide credenciales ni usa TLS (no hay flags para ello en [`main.go`](../server/cmd/chispa-server/main.go)): por defecto escucha solo en `127.0.0.1`.
Ponga delante un proxy inverso del cliente con TLS y autenticación, y no lo exponga a internet. Sin medir ni probado aquí.

### Comprobar
```
curl -s localhost:8090/healthz          # {"status":"ok"}: el proceso responde, no dice qué capas hay cargadas
curl -s localhost:8090/metrics          # Prometheus
```
Vigile `chispa_escalados_total` frente a `chispa_preguntas_total` y `chispa_capa_errores_total`.

## 4. Los tres modos y cuándo pasar de uno a otro

### Modo 1: zero-shot (sin ejemplos)
```
PYTHONPATH=sdk/python python -m chispa train --esquema mi-esquema.yaml --pregunta pqrs_tipo --salida zero.chispa --l1 potion.chispa-l1
```
Trae META, L1 y un `CALIB` sin calibrar con τ = 0,6; no lleva L0. Decide L1. L1 es flojo: macro-F1 medio 0,455 en cinco benchmarks
([`informe.md`](../model/l1/resultados/2026-10-28/informe.md)); en español de Colombia y PQRS, sin medir. Úselo para probar el cableado y las descripciones,
**con revisión humana de lo que escala**. `score` no tiene capa en este modo.

### Modo 2: few-shot (pocos ejemplos)
Ejemplos en CSV o JSONL, columnas `texto` y `etiqueta`; cada etiqueta debe ser una opción y cada opción necesita ≥ 1 ejemplo (las plantillas traen 5):
```
PYTHONPATH=sdk/python python -m chispa train --ejemplos pilotos/esquemas/ejemplos/pqrs_tipo.csv --esquema mi-esquema.yaml \
  --pregunta pqrs_tipo --salida fs.chispa --l1 potion.chispa-l1
```
Con menos de 10 ejemplos en alguna opción no se entrena L0 y L1 se calibra con todos; con 10 o más por opción también se entrena L0.
Referencia: L1 con 32 ejemplos por clase sube de 0,455 a 0,654 de macro-F1 (`informe.md`, mismo fichero); con k = 5, sin medir.
La calibración con pocos ejemplos es ruidosa: deje aparte unas decenas de casos reales y mida.

### Modo 3: con datos del cliente (`--conjunta`, avanzado)
Necesita **al menos 20 ejemplos etiquetados por opción** y el checkpoint de L2; con menos, `chispa train` avisa por stderr y cae a few-shot. Solo `choice`.
```
PYTHONPATH=sdk/python python -m chispa train --ejemplos ejemplos.csv --esquema mi-esquema.yaml --pregunta pqrs_tipo \
  --salida conj.chispa --ckpt mejor.pt --l2 l2.chispa --conjunta --repo .
```
Referencia en benchmarks: macro-F1 0,814 en massive y 0,887 en clinc150 por `/v1/decide`
([`e2e-20261028/LEEME.md`](../server/deploy/resultados/e2e-20261028/LEEME.md)). Con este modo, la pregunta y los ids de la petición deben ser los del entrenamiento.
Sirve con `-tags ort` y `-tok`. `--validacion <csv>` fija el τ de L2c sobre filas aparte; `--precision-objetivo` (0,95) fija la precisión.

### Cuándo pasar de uno a otro
| De → a | Señal (con la muestra etiquetada, [`metrica.md`](metrica.md)) |
|---|---|
| zero-shot → few-shot | Siempre que haya ≥ 5 ejemplos por opción; o la exactitud o la cobertura no llegan al umbral, o las descripciones ya no se pueden afinar más |
| few-shot → con datos del cliente | Hay ≥ 20 ejemplos por opción **y** el checkpoint de L2 **y** la tarea es `choice` **y** few-shot no llega al umbral |
| quedarse | El umbral se cumple con tasa de escalado aceptable; un modo más caro no se justifica |
| parar | Ni con datos del cliente se llega al umbral: el esquema es ambiguo (revise opciones) o la tarea no es para Chispa |

## 5. Pedir una decisión

### curl (el esquema viaja en la petición)
```
curl -s localhost:8090/v1/decide -d '{"state":"Me cobraron dos veces la cuota y quiero que me devuelvan la plata","questions":[{"id":"q1","question":"¿Qué tipo de PQRS es este mensaje?","kind":"choice","options":[{"id":"peticion","description":"la persona solicita algo que la empresa puede hacer, sin expresar inconformidad"},{"id":"queja","description":"la persona expresa inconformidad por el trato o la atención recibida"},{"id":"reclamo","description":"la persona exige que se corrija o repare algo que falló"},{"id":"sugerencia","description":"la persona propone una mejora, sin un problema que resolver"},{"id":"felicitacion","description":"la persona agradece o elogia la atención"}]}]}'
```
Respuesta: `results[].answer`, `probs`, `layer` (qué capa respondió) y `escalate` ([`docs/03`](../docs/03-api.md)). Si `escalate` es `true`, `answer` es solo la mejor pista:
**envíe el caso a una persona**. Errores: 400 (JSON o regla incumplida; una pregunta mala rechaza toda la petición), 405, 413 (> 1 MiB). Ahora, la pregunta
y las descripciones de la petición deben ser las del esquema (en modos 2 y 3 los ids deben coincidir con los del entrenamiento).

### Python
```python
from chispa import Chispa, Choice
rs = Chispa("http://127.0.0.1:8090").decidir("Me cobraron dos veces la cuota",
    [Choice("q1", "¿Qué tipo de PQRS es este mensaje?",
            [("peticion", "solicita algo que la empresa puede hacer"), ("queja", "inconformidad por el trato"),
             ("reclamo", "exige corregir algo que falló"), ("sugerencia", "propone una mejora"),
             ("felicitacion", "agradece o elogia")])])
rs[0].answer, rs[0].probs, rs[0].layer, rs[0].escalate
```
El cliente reintenta con espera exponencial y fija un `nonce` automático: un reintento es idempotente ([`sdk/python/README.md`](../sdk/python/README.md)).

### Línea de comandos
```
PYTHONPATH=sdk/python python -m chispa decide --url http://127.0.0.1:8090 --estado "Me cobraron dos veces la cuota" \
  --tipo choice --pregunta "¿Qué tipo de PQRS es este mensaje?" --opciones peticion queja reclamo sugerencia felicitacion
```
Atención: este comando manda **solo los ids** de las opciones, sin descripciones. Sirve para probar el cableado, no para medir el zero-shot: use curl o Python.

### Varias preguntas
Una petición admite hasta 256 preguntas ([`docs/03`](../docs/03-api.md#límites)); cada pregunta la decide el `.chispa` cuyas etiquetas coinciden. Para servir varios `.chispa`
(p. ej. `pqrs_tipo` y `pqrs_urgencia_cat`), use `-config` con una lista `modelos` ([`docs/03`](../docs/03-api.md#configuración--config)) o únalos con
`go run ./deploy/mkmodelo -unir a.chispa,b.chispa -out modelo.chispa` (gana el primero si repiten sección, así que no sirve para dos preguntas con las mismas secciones). Servir varios modelos a la vez: sin probar aquí.

## 6. Conectar su sistema
- Llame a `/v1/decide` desde su sistema de PQRS, mesa de ayuda o CRM, **sin enviar datos personales** del paso de anonimización ([`datos-y-consentimiento.md`](datos-y-consentimiento.md)).
- Trate `escalate: true` como «va a una persona»; no lo descarte ni use `answer` sin revisar.
- Registre en su sistema texto o id del mensaje, `answer`, `layer`, `escalate` y la decisión final de la persona: con eso se mide el piloto sin trabajo extra ([`metrica.md`](metrica.md)).
- Haga el piloto en **paralelo** (modo sombra): la persona sigue decidiendo y Chispa se compara. No lo ponga a decidir solo durante el piloto.
- Sondas: `/healthz` para vida y `/metrics` para Prometheus.

## 7. Qué hacer si algo falla
| Síntoma | Causa probable |
|---|---|
| El entrenamiento falla en zero-shot | No pasó `--l1`: sin él no hay ninguna capa |
| `chispa train` sale sin L0 | No hay Go en esa máquina (lo avisa por stderr) |
| `escalate` casi siempre `true` | τ de zero-shot sin calibrar (0,6), descripciones parecidas entre opciones, o esquema `score` (sin capa) |
| 400 con `questions[0].…` | La petición incumple el contrato; el error trae la ruta del campo |
| L2 no responde | Falta `-tags ort` o `-tok`; con `-modelo` solo L0/L1 y L2 queda en stub con un aviso en el log |
