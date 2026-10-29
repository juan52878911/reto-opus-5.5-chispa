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
