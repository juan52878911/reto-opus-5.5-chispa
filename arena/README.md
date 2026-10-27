# Reto Opus 5.5 · Chispa Arena

Arena adversarial automática sobre [kindling](https://kindling.asccilabs.com):
- Un motor ataca sin parar a un **enjambre de clasificadores diminutos**: Chispa (regresión logística, µs por decisión) más uno de reglas.
- El enjambre tiene una dimensión por clasificación: spam, injection y urgencia.
- Lo que el enjambre no resuelve, o en lo que se deja engañar, pasa a **VON**, un LLM pequeño, que lo etiqueta por lotes.
- Chispa se reentrena en sombra y **solo se promociona si gana**: se deja engañar menos, o escala menos sin perder exactitud.
- El objetivo es servirlo todo desde **golden snapshots** con los pesos compartidos entre réplicas.

**Trazabilidad:** abre `http://127.0.0.1:8088/trazabilidad`. Ahí se marca qué funciona en vivo, qué se ha medido en microVMs y qué está pendiente, con las cifras y supuestos de cada cosa.

```sh
make train && ./arena run -ramp -max-vms 36 -cpu-stop 90 -workers-per-vm 4   # panel en http://127.0.0.1:8088
```

Estado:
- **En vivo:** procesos locales con enjambre, ataques, aprendizaje (con oráculo de la semilla), rampa y micro-lotes.
- **Medido en Lima (kindling 0.17, Firecracker):** golden de 53 MB, restore en 171–265 ms, réplicas VON con ~10 MiB privados que comparten 896 MiB de pesos, y 6.400 decisiones/s por microVM.
- **Pendiente:** el enjambre completo en microVMs bajo carga. Está implementado el modo nodo (`-per-node`), pero sin validar.

---

## Detalle del MVP

Arena adversarial automática: un motor ataca sin parar a un **enjambre de detectores
diminutos** (Chispa, de kindling, más uno de reglas) y mide en vivo si el enjambre es
más difícil de engañar que el mejor detector solo.

Estado: MVP. Detectores como procesos locales; el modo microVM de kindling es la Fase A.

```sh
make arena    # dataset → train → 12 detectores → ataques → panel en http://127.0.0.1:8088
make smoke    # 50 ataques y comprobación de detector_result, swarm_result y SSE
make test
```

## Qué hay

| Pieza | Dónde |
|---|---|
| Contratos congelados (§6 del plan) | `contracts/` |
| Dataset sintético por plantillas (WhatsApp, español colombiano), reparto por plantilla sin fugas | `internal/dataset` |
| 4 detectores por dimensión: `chispa-words`, `chispa-char` (3-5), `chispa-sub` (60% y otra semilla), `rules` | `internal/detectors` |
| Servidor por detector: `POST /decide_batch`, `GET /health` | `internal/detsrv` |
| Mutaciones (homoglifos, ruido, emojis, relleno, code-switching, formato) y búsqueda guiada que solo inserta | `internal/attacks` |
| Veredicto del enjambre: media de log-probs; escala si la p verdadera difiere > 0,5 | `internal/swarm` |
| Registro (`data/ledger.jsonl`) y métricas | `internal/ledger` |
| Panel con SSE (`/events`, `/metrics`, matar y revivir detectores) | `internal/web` |

Dimensiones: `spam` (spam/legit), `injection` (injection/safe), `urgencia` (alta/media/baja).

**Cuándo cuenta como engaño:**
- **Un detector** queda engañado si contesta mal sin escalar.
- **El enjambre** queda engañado si no escala y la etiqueta agregada es incorrecta.

## Medido (M4, 20 workers, una ejecución de ~10 s)

- Entrenar los 9 modelos Chispa: 0,26 s. Exactitud en test, con plantillas nunca vistas: 0,57–0,99.
- Unos 3.700 ataques/s y 13.500 decisiones/s. La latencia p95 de un detector va de 0,02 a 0,3 ms.
- Unos 21 MB de RSS por detector. Cuesta ~42 µs de CPU por decisión, contando HTTP y JSON; el modelo solo tarda unos µs.
- Con $0,04 por vCPU-hora (un supuesto, flag `-vcpu-usd`), salen ~$0,0005 por millón de decisiones. Gasto en LLM: $0.

| ASR | enjambre | mejor detector solo |
|---|---|---|
| spam | 0,09 | 0,16 |
| injection | 0,30 | 0,18 |
| urgencia | 0,25 | 0,25 |

El enjambre gana en spam, empata en urgencia y **pierde en injection**: ahí el detector
de reglas y el de n-gramas de caracteres arrastran el promedio. Pendiente: ponderar por
fiabilidad o excluir del veredicto al detector peor calibrado.

## Qué falta (hoja de ruta)

- **A.** Detectores en microVMs de kindling (`kling ai chispa deploy`, snapshots y fork).
  El daemon no estaba accesible al construir el MVP.
- **B.** Registro durable en SQLite WAL.
- **C.** Datos reales por Batch API.
- **D.** `make harden`: reentrenar con los ataques que tuvieron éxito, y Laya/Jev.
- **E.** Prueba en sombra de un candidato con `kling sandbox fork`.
