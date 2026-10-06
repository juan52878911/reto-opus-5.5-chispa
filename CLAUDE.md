# Chispa Arena

Mapa: ver README.md. Plan completo: ~/.claude/plans/quiero-que-crees-un-happy-rabbit.md.

Reglas:
- `contracts/` está congelado: solo lo cambia la sesión principal.
- Cada subagente escribe solo en su carpeta.
- Los subagentes usan `model: sonnet` y no hay modo rápido.
- Presupuesto de USD 100: revisa `/cost` al cerrar cada fase y nunca toques la reserva.
- Si algo falla dos veces, para y escala a la sesión principal.
- Para `kling`: lee `kling --help` antes de usarlo y no inventes flags.
- No cargues en contexto `data/`, `models/` ni `data/ledger.jsonl`.
- Antes de dar algo por terminado: `make test` y `make smoke`.
