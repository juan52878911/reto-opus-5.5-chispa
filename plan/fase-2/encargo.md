# Encargo: Chispa fase 2, el modelo L2

Acordado con Juan («sigue hasta terminar», 2026-10-27). G1: (a), (b) y (d) en verde. (c), las
conversaciones con clientes, queda pendiente de Juan: no bloquea entrenar, pero sí la fase 4 (pilotos).
Informe de entrada: `model/informes/fase-1.md`.

## Objetivo y entregable
L2: e5-small (D3) con ranuras de lectura, torres de opción y cabezas por tipo de pregunta, calibrado
y exportado a ONNX int8 dentro de un `.chispa` v3, que el servidor (`server/`) carga en la capa L2.

## Criterio de aceptación (congelado)
- **T2.1**, sobre el codificador congelado: ≥ 5 puntos de macro-F1 sobre e5 con kNN-32 (cifras de
  `model/lineas_base/informe.md`) en ≥ 3 tareas, medido en test con `chispa eval`.
- **T2.2**, ajuste contrastivo y destilación:
  - macro-F1 ≥ 0,95 × la del mejor sistema de referencia disponible en las tareas en español.
    Jev no está medido, así que la referencia es el máximo entre L0, e5 kNN-32 y el maestro Qwen;
  - caída ≤ 5 puntos al renombrar las opciones a A/B/C.
- **T2.4**, calibración: ECE ≤ 0,05 y cobertura a precisión 0,95 ≥ 70 % por tarea. AUROC del
  escalate medido en CLINC `oos` y en herramientas.
- **T2.5**: `.chispa` v3 con cargador en Go que aguanta 10 min de `go test -fuzz` sin fallos.
- **T2.6**:
  - L2 ≤ 60 MB, con p99 < 50 ms a 64 tokens en x86 con AVX2 (c6a);
  - ASR de la Arena ≤ 0,15 en spam e inyección;
  - batería completa con `chispa eval`, también sobre el listón humano (log-loss contra `blanda`).

## Datos
- **Train:**
  - metaentrenamiento en S3: `s3://chispa-pruebas-879381269751/meta-20261027/meta/`, 3,26 M filas;
    se submuestrea a ≤ 600 k, con todo tasksource-jev comercial (581 k) y el resto repartido;
  - train de los conversores de `model/datos/` con `uso_comercial: true`;
  - T1.4;
  - sin corpus sintético: T1.3 quedó fuera tras 4 intentos (ver `model/informes/fase-1.md`).
- **Etiquetas blandas:** las de tasksource-jev y las del maestro Qwen
  (`s3://…/maestro-20261027/ronda1/`). Haiku, nunca.
- **Test:** los de T1.7a, el listón humano y las PQRS (solo test, nunca fuera de kindling ni del bucket).

## Presupuesto
- AWS, total de la fase: ≤ 25 USD. g5.xlarge on-demand (la cuota spot de GPU es 0), siempre con
  apagado forzoso; parada a los 60 USD acumulados del proyecto.
- Cuenta: ≤ 40 USD de workers. Solo el perfil personal, con `--over-budget` por el bug del chequeo diario.

## Fuera de alcance
Fase 3 (L1 destilado, móviles), fase 4 (pilotos), cambiar `model/esquema.md` o `arena/contracts/`.

## Decisiones que son de Juan
Gasto por encima del tope, ALIA y PQRS en train, y cambiar los umbrales de arriba.

## Cambios
| Fecha | Qué cambió | Por qué | OK de Juan |
|---|---|---|---|
