# T0.1 Monorepo: la Arena pasa a `arena/` con su historial y nace el esqueleto de Chispa

Encargo: `plan/fase-0/encargo.md` (criterio de aceptación congelado; no lo cambies tú).

## Hipótesis
- Mover con `git mv` todo lo de la Arena (cmd, internal, contracts, scripts, go.mod, go.sum, Makefile,
  README) a `arena/` conserva el historial con `--follow`, y un Makefile raíz que delega en `arena/`
  mantiene `make test` y `make smoke`. Se refuta si algún import o ruta relativa se rompe: córrelo.

## Terminado cuando
- `make test` y `make smoke` en verde desde la raíz (pega la salida resumida).
- `git log --follow --oneline arena/go.mod | wc -l` ≥ 2.
- Existen `sdk/README.md`, `server/README.md`, `nix/flake.nix` (Python fijado con torch,
  sentence-transformers, onnxruntime y optimum, más Go 1.27) y un `README.md` raíz con el mapa.
  `nix develop` no se puede probar aquí: dilo en el informe.
- `contracts/` se mueve tal cual a `arena/contracts/`, sin cambiar su contenido (el orquestador lo autoriza).
- Parada: si tras 2 intentos algo no pasa, avisa con `blocker`.

## Zona
- Todo lo que hay hoy en la raíz, `nix/`, `sdk/`, `server/`. **No tocar** `model/`, `plan/` ni `.delega/`.
- Reglas del CLAUDE.md del repo: no cargues `data/`, `models/` ni `data/ledger.jsonl` en contexto
  (muévelos con `git mv` sin leerlos). Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile` antes de nada (Go en `~/go-sdk`). Sin red salvo la API de Claude.
- Línea base: `25d934f`.

## Tope
- ≤ 90 min de reloj · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤15 líneas: qué cambiaste, rama y sha, qué verificaste ejecutando (con
números), qué quedó sin verificar y qué recomiendas a continuación.
