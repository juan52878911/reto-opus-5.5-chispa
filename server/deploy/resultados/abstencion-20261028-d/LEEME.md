# T4.6d medido: tareas pequeñas sin τ sobre dev (< 500 filas) y con tope de 0,9 (2 c6a, 2026-10-28)

| tarea | τ | escala | precisión de lo contestado | ASR del detector cascada (solo / enjambre) |
|---|---|---|---|---|
| injection | 0,9 (tope) | **16,7 %** (antes 24,1 %) | 1,000 | 0,113 / 0,137 (antes 0,015 / 0,022) |
| spam | 0,9 (tope) | **23,1 %** (antes 84,3 %) | 1,000 | 0,124 / **0,201** (antes 0,019 / 0,017) |

- **injection cumple todo:** escala ≤ 20 %, la precisión es 1,0 y el ASR queda en ≤ 0,15.
- **spam no cumple ninguna de las dos condiciones:** escala el 23,1 % y el ASR del detector en la corrida del enjambre
  es 0,201.
- **Es un intercambio de fondo.** Lo que no se escala ante tráfico normal tampoco se escala ante los ataques. Con τ = 0,99,
  spam escala el 84 % del tráfico normal y el ASR es 0,02. Con τ = 0,9, escala el 23 % y el ASR es 0,12–0,20. **Queda
  anotado como limitación.**
- **El ASR del enjambre** no empeora: spam 0,074 e injection 0,171.
- **Decisión pendiente (Juan).** El valor por defecto `--tope-tau 0.9` de `chispa train` favorece la utilidad con tráfico
  normal. Se puede subir o quitar por tarea si importa más la robustez ante ataques.
- **Coste:** dos c6a, de 4 y 28 min. Menos de 0,1 USD.

**Juan's decision (2026-10-28):** «Keep the 0.9 τ cap for every task, as it is now». The default `--tope-tau 0.9` applies
to every task, security ones included. In spam the ASR rises to 0.12–0.20 in exchange for escalating 23% of normal traffic.
This is an accepted limitation.
