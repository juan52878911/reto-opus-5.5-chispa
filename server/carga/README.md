# Arnés de carga (W2)

Mide decisiones/s, p50 y p99 de `chispa-server` por modo y concurrencia, y escribe `resultados-<host>-<fecha>.md` + `.csv`
con el entorno (CPU, núcleos, GOMAXPROCS, loadavg antes y durante, versión de ORT).

- `correr.sh`: compila `chispa-server` y `cmd/carga`, arranca el servidor en el puerto 18090 con la config del modo, calienta 2 s,
  barre concurrencias × tandas y lo para al salir.
- `textos.txt`: 260 frases sintéticas propias. Con `-t fichero` se pasan mensajes reales (uno por línea; `#` comenta).
- Modos:
  - `l1`: cascada normal (L0 τ 0,8 → L1 τ 0,8). Con `-M modelo.chispa` L0/L1/L2 salen del modelo; sin él solo hay los `.chispa` de
    `testdata/` en L0 y L1 es stub (el CSV muestra qué capa decidió).
  - `l2`: L2 forzado. Config con L0 τ=1 y L1 τ=1 (no aceptan salvo confianza 1,0 exacta), L2 τ=0 y sin modelos de L0; `-M` añade el
    modelo (el τ de calibración no pisa la config explícita). Sin `-O -M -T` L2 es stub: el informe lo dice y todo acaba en «escalar».
- `cmd/carga` ganó flags aditivos: `-textos` (rota mensajes), `-csv` (línea CSV) y `-capas` (cuenta la capa que decidió). Sin ellos, igual que antes.

## Receta para el i7 (G.4)
Con `libonnxruntime.so` instalada, el modelo v3 y el `.chispa-tok` de e5:
```
cd server && carga/correr.sh -O -M /ruta/modelo.chispa -T /ruta/e5.chispa-tok -t /ruta/massive.txt   # 1 4 16 64 · 30 s · 3 tandas
```
Sin ORT: quitar `-O` (L2 en stub, no válido para el objetivo de 300/s). Otras opciones: `-m l1`, `-c "1 4 16 64"`, `-d 30s`, `-n 3`, `-o dir`, `-p puerto`.
Máximo 64 conexiones. Si hace falta fijar núcleos: `GOMAXPROCS=4 carga/correr.sh ...`. Objetivos: l1 ≥ 5000 dec/s con p99 < 20 ms; l2 ≥ 300 dec/s.
`make -C server carga-arnes ARGS="-d 10s -n 1"` lo lanza desde el Makefile.

## Sin verificar
`-O` (compilación con ORT, detección de la versión) y `-M/-T` no se han ejecutado en este nodo (sin ORT ni modelos).

## Mensajes realistas en español de Colombia (T4)
- `textos-es-co.txt`: 2.400 mensajes inventados (ninguno copiado de un dataset), uno por línea, UTF-8, sin tabuladores, mezclados al azar (no vienen
  agrupados por dominio, así la rotación de `cmd/carga` mezcla dominios y longitudes). Ocho dominios: PQRS de salud, banca, telecomunicaciones, comercio
  electrónico, ferretería, servicios públicos, soporte técnico y ventas. De 3 a 120 palabras, con faltas de ortografía, sin tildes, MAYÚSCULAS, emojis y jerga
  ocasionales (parce, vaina, de una). Sin datos reales: `[NOMBRE]`, `[CEDULA]`, `[TELEFONO]`, `[CORREO]`, `[DIRECCION]`, `[NUMERO_PEDIDO]` y cifras inventadas.
  Ninguna línea empieza por `#` (`cmd/carga` las tomaría por comentarios).
- `estadisticas_textos.py` (solo stdlib): `python3 carga/estadisticas_textos.py [fichero]` imprime el reparto de longitudes (palabras y bytes) y de dominios
  (estimado por palabras clave: el fichero no lleva etiqueta, es aproximado) y comprueba únicos y tabuladores.
- `esquemas-carga.json`: 8 preguntas zero-shot (3 `choice`, 3 `score`, 2 `noul`: tipo de PQRS, área destino, acción pedida, urgencia, enojo, fraude,
  acción legal, intención de compra) y 4 `lotes` (1, 3, 5 y 8 preguntas por petición). Cada pregunta es una pregunta válida del API tal cual.

### Uso con el arnés
```
cd server && carga/correr.sh -t carga/textos-es-co.txt                      # mensajes realistas, pregunta fija de siempre
carga/correr.sh -O -M /ruta/modelo.chispa -T /ruta/e5.chispa-tok -t carga/textos-es-co.txt -m l1
go run ./cmd/carga -url http://127.0.0.1:18090/v1/decide -textos carga/textos-es-co.txt -c 16 -d 30s -lote 4 -capas -csv
```
`-lote N` repite N veces la pregunta fija (4 opciones); no sirve para probar esquemas distintos.

### Mandar los esquemas (hoy: a mano; `cmd/carga` no lo permite aún)
`construirCuerpos` (`cmd/carga/textos.go`) solo arma la pregunta fija. Para una petición suelta con un lote de `esquemas-carga.json`:
```
python3 - <<'PY' | curl -s -H 'content-type: application/json' --data-binary @- http://127.0.0.1:18090/v1/decide
import json, random
d = json.load(open("carga/esquemas-carga.json")); q = {x["id"]: x for x in d["preguntas"]}
msgs = [l.strip() for l in open("carga/textos-es-co.txt", encoding="utf-8") if l.strip()]
print(json.dumps({"state": random.choice(msgs), "questions": [q[i] for i in d["lotes"]["cinco"]]}))
PY
```
Flag que haría falta (no implementado): `-esquemas carga/esquemas-carga.json -lotes-nombre cinco`, para que `construirCuerpos` use las preguntas del lote nombrado
(en lugar de la fija y de `-lote`), una petición por mensaje de `-textos`, y `decisiones/s` cuente `len(lote)` por petición. Con `-capas` habría que desglosar
también por `id` de pregunta (L0/L1/L2 cambian según el tipo y el número de opciones).

### Qué mirar
L1 debería mostrar su p50/p99 contra la longitud (el coste del tokenizador crece con los bytes del estado): compara `-t textos.txt` (frases cortas) con
`-t textos-es-co.txt`. Si la latencia no depende de la longitud, basta el fichero pequeño. Sin verificar en este nodo (sin Go): ni `correr.sh` ni `cmd/carga` se ejecutaron con estos ficheros.
