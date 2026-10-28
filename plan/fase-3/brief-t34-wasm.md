# T3.4 Demo de L1 en WASM

Plan aprobado, fase 3, T3.4. Criterio: clasifica en el navegador, con la latencia medida a 16, 64 y
256 tokens. Antecedentes:
- `runtime/l1/`: Go puro, determinista en amd64 y arm64;
- `format/chispa3/`;
- `sdk/python/` (`chispa train`, que genera un `.chispa` con L0 y L1).

## Hipótesis
- `runtime/l1` compila a `GOOS=js GOARCH=wasm` sin cambios, o con cambios mínimos detrás de etiquetas de build.
- El `.chispa-l1` de 155 MB es demasiado para el navegador. Para la demo basta un L1 recortado: un
  vocabulario de ≤ 50 k tokens, el de `model/bench/vocab-podado-e5-small.json` u otro sacado del
  sondeo y los datos en español. Debe pesar ≤ 30 MB y, frente al completo, dar un coseno ≥ 0,99 en el sondeo.
- Se refuta midiendo.

## Terminado cuando
- `runtime/l1/` admite exportar un L1 recortado: `exportar.py --vocab <json>`. Si eso toca el
  exportador, lleva tests propios. Mide el tamaño y el coseno frente al completo en las 2.274 frases del sondeo.
- `demo/wasm/`:
  - `main.go` compilado a wasm, que expone `cargar(bytes)` y `decidir(texto, preguntaJSON)` vía `syscall/js`;
  - `index.html` más `wasm_exec.js` (copiado de `$(go env GOROOT)/misc/wasm/` o `lib/wasm/`);
  - un ejemplo con las preguntas de intención de WhatsApp;
  - un botón que mide la latencia a 16, 64 y 256 tokens (p50/p99 de 200 repeticiones) y la muestra en la página;
  - sin CDN ni red: todo local.
- Pruebas sin navegador:
  - `GOOS=js GOARCH=wasm go build` pasa;
  - un test con `node` (está en la VM) que ejecuta el wasm con `wasm_exec_node.js`, carga el L1
    recortado, clasifica 50 frases del sondeo y comprueba que coinciden con la versión nativa
    (mismo hash de embeddings);
  - la latencia en node a 16, 64 y 256 tokens va al README como cota. La del navegador se mide después en Chrome.
- `demo/wasm/README.md` explica cómo construir y servir la demo (`python -m http.server`).
- El L1 recortado no va a git si pasa de 5 MB: se regenera con un comando del README.
- `go vet` y `go test` en `runtime/l1`, más `make test` y `make smoke`, en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- `demo/wasm/` y `runtime/l1/` (solo lo del exportador recortado y las etiquetas de build; no rompas
  el test dorado de arm64 y amd64).
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Go en `~/go-sdk/bin`, Python en `~/venv`, `node` y modelos en `~/hf`. No hay red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas que incluya:
- qué cambiaste, rama y sha;
- el tamaño y el coseno del L1 recortado;
- la latencia del wasm en node;
- qué quedó sin verificar y qué recomiendas.
