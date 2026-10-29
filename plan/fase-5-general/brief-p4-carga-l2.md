# P4 Carga en el i7 con L2 real (`-tags ort`): objetivo ≥ 300 decisiones/s

## Antecedentes
- **G.4** (`model/bench/carga/resultados-i7.md`) midió L0+L1 en este nodo (pve, i7-8700T): entre 21 y 33 k
  decisiones/s. L2 no se pudo medir porque faltaban `onnxruntime_go` y la red.
- **El dorado ya trae lo que faltaba:** el módulo `github.com/yalue/onnxruntime_go v1.38.0` en GOMODCACHE, ONNX Runtime
  1.31.1 en `~/ort` y gcc. Lo instala `.delega/golden.sh`.
- **El servidor ya tiene la torre al vuelo y el L2 conjunto.** Importante: `chispa-server` arranca solo en loopback sin
  `api_keys` y rechaza las claves de config desconocidas.

## Hipótesis
Con 4 hilos en el i7, `chispa-server -tags ort` sirve ≥ 300 decisiones/s con L2 forzado, un p99 < 50 ms con concurrencia
4 y la consulta int8 a 64 tokens. Se refuta midiendo.

## Terminado cuando
- **Compilación.** `model/bench/carga/` arma los modelos dentro de la VM, como en G.4 (`armar.sh`): L0+L1 con
  `chispa train` y L2 exportado con `model/l2/exportar.py` sobre e5 de `~/hf`, con la cabeza aleatoria y semilla fija.
  - Compila `chispa-server -tags ort` con `CGO_ENABLED=1`, `CHISPA_ORT_LIB=$HOME/ort/lib/libonnxruntime.so.1.31.1` y
    `GOFLAGS=-mod=mod GOPROXY=off`.
  - Si `-tags ort` no compila, para y di por qué.
- **Mide con `server/carga`** (`carga/correr.sh` si existe en esta base; si no, `cmd/carga`). Arranca el servidor en
  127.0.0.1.
  - **Modos:** L2 forzado (L0 y L1 con τ = 1, L2 con τ = 0, configs con claves válidas) y cascada por defecto.
  - **Concurrencia:** 1, 4, 16 y 64.
  - **Tandas:** 30 s por punto y 3 tandas.
  - **Textos:** mensajes reales de massive y, si cabe, los de 256 tokens.
- **Comprueba en `/metrics`** que L2 decide y que, con un esquema que no esté en el `.chispa`, `chispa_torres_calculadas_total`
  es > 0. Usa la consulta int8 y la torre fp32, la configuración de servidor.
- **Resultados:** `model/bench/carga/resultados-i7-l2.md`, con la tabla frente a 300/s, el p50/p99, el loadavg y el aviso
  de que la cabeza es aleatoria (no cambia la latencia).
- No cambies `server/` ni `sdk/`. Si hace falta algo de ahí, descríbelo en el informe.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `model/bench/carga/**`.
- Rama: la que te da delega. Base: `integracion`. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, Python en `~/venv`, modelos en `~/hf`, datos en `~/datos` y ORT en `~/ort`.
- Sin red salvo la API de Claude. Este nodo es solo para medir.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 10 líneas:
- rama y sha;
- la tabla resumida frente a 300/s;
- las métricas de las torres;
- qué no se pudo medir.
