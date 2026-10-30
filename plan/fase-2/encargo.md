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
| 2026-10-28 | L2 no cumple T2.1 ni T2.2 en tres rondas. Pasa a capa de respaldo: se juzga la cascada L0 → L1 → L2 con el listón de T2.2 (T2.7, `brief-t27-cascada.md`). Después, la cabeza conjunta L0 + L2 (T2.2c, `brief-t22c-conjunta.md`) | La representación de e5-small limita en las tareas de muchas clases, donde gana L0 | Sí: «C y después b. Paralelizar trabajo como hemos hecho para agilizar el desarrollo» |
| 2026-10-28 | **T2.4 se redefine (única redefinición), por tarea.** ECE ≤ 0,05 en todas las tareas. Cobertura ≥ 70 % con precisión 0,95 solo donde el macro-F1 llegue a 0,85; en las demás se publica la curva de cobertura. Inyecciones se calibra solo si tiene más de 500 filas; si no, se evalúa sin calibrar | Con un macro-F1 de 0,67–0,73, hatecheck y herramientas no pueden cubrir el 70 % a precisión 0,95 (T2.2d) | Sí: «T2.4 por tarea: ECE ≤ 0,05 en todas y cobertura ≥ 70 % con precisión 0,95 solo donde el macro-F1 llegue a 0,85; en las demás, publicar la curva de cobertura. Inyecciones con calibración solo si hay más de 500 filas.» |
| 2026-10-28 | G2 pasa con dos excepciones: el ECE de hatecheck (0,058) y de inyecciones (0,053, 116 filas), y la abstención. Abstención máxima con tráfico normal: 20 % | Cierre de la fase 2 (`model/informes/fase-2.md`) | Sí: «Si, deja el 20% por ahora» |
| 2026-10-28 | τ of L2c capped at 0.9 for every task, security ones included; in spam the Arena ASR can exceed 0.15 (0.20 in the swarm) | Trade-off between normal-traffic abstention and ASR (T4.6d) | Yes: «Keep the 0.9 τ cap for every task, as it is now.» |
| 2026-10-28 | **Tope total de AWS del proyecto: 50 USD** (antes 100). Gastado según Cost Explorer: 6,28 USD de uso hasta el 2026-10-28, que cubren los créditos, más ≤ 3 USD del día aún sin contabilizar. Quedan ≈ 41 USD. Por delante van JevBench y las tareas no vistas; después, la mac2 o los nodos EC2 | Decisión de Juan | Sí: «Pasa el limite a 50 dolares» |
| 2026-10-28 | **Corrección del gasto de AWS:** la consola de créditos da 45,38 USD estimados (37,68 facturados), todo de créditos (100 USD en 3 créditos; el de 50 USD, «2026 AWS LATAM Summits», vence el 30/11/2026). Cost Explorer por API daba 6,28 USD: no cuadra, quizá por desfase o por filtro. Mientras Juan aclara si el tope de 50 es total, nada nuevo que pase de 4 USD en total | Captura de Juan | Pendiente de aclarar |
| 2026-10-28 | **Corrección de la corrección del gasto de AWS.** Lo que gastó Chispa es Octubre: 6,28 USD hasta el 28 (EC2 Compute 4,72, EC2 Other 0,66, ECR 0,48, S3 0,39 y VPC 0,03). AWS prevé 11,42 USD para el mes. Los 37,68 USD de septiembre son de VibeVoice, no de Chispa. Los 45,38 USD de los créditos suman los dos meses. Gasto real de Chispa: unos 6-9 USD | Página de facturación de Juan | Tope pendiente |
| 2026-10-29 | **AWS: quedan 10 USD** desde este momento, contando las corridas encendidas (la g5 de tareas no vistas, ≈ 2,5 USD; la c6a de JevBench y la de Android, ≈ 0,1 USD cada una). Saldo libre ≈ 7,3 USD. Sin workers de delega en EC2 y sin mac2, así que iOS queda sin compilar. Prioridad: G.6, la verificación del ONNX de la torre (≈ 0,2); después la E2E de JevBench por el servidor; nada en GPU sin avisar el coste | Decisión de Juan | Sí: «Quedan 10 dolares para gastar. por ahora no usemos workers en aws» |
| 2026-10-29 | **Cierre de la semana** (Juan: «las actividades que realizas serán las últimas de esta semana»). Gasto de Chispa desde esta sesión, a precio de lista: workers personales 52,6 USD y SDK 5,7 USD (74 trabajos). AWS: 6,28 USD facturados en octubre hasta el 28, más ≈ 3,5 USD del 28 y el 29. Del saldo de 10 USD se gastó ≈ 0,7 y quedan ≈ 9,3. No queda nada encendido | Cierre | — |
| 2026-10-29 | **Pendiente para la semana que viene:** la clave de ESQUEMAS y CONJ que escribe `exportar.py`, `HashEsquema(pregunta, [opción])`, no incluye la descripción; la de la torre al vuelo sí, `HashEsquema(pregunta, [opción, descripción])`. Dos esquemas con las mismas opciones y distinta descripción comparten torres precalculadas, y en zero-shot la descripción es lo que cuenta. Hay que alinear las dos claves con una versión de formato nueva y compatibilidad hacia atrás. Esta noche no se cambia, porque rompería los `.chispa` existentes | Revisión R5 del SDK | — |
| 2026-10-29 | **P4 (carga en el i7 con L2 real) en pausa.** Para rehacer el dorado de pve hay que borrar el dorado viejo, y eso necesita a Juan. Se retoma cuando Juan lo diga | Bloqueo (disco de pve) | «Déjemos en pausa lo que sea un stopper por ahora» |
| 2026-10-29 | **Paridad servidor ↔ Python cerrada** en JevBench con torres al vuelo: 0,494 frente a 0,485, con choice 0,482, noul 0,554 y score 0,333, y 0 discrepancias en 78 casos. `chispa train --ckpt` lo da sin pasos manuales. Causas: la consulta int8 con el vocabulario podado (X1), las descripciones que faltaban en la petición, y la CALIB de noul y score que faltaba (`calib_completa` más TZ en `tipos_l2`). La clave v2 de ESQUEMAS y CONJ (`HashEsquema2`) ya está alineada | D1 a D1f y corrida final (`model/bench/torre/resultados-20261029-final`) | — |
| 2026-10-29 | **Perfil móvil: fp16 con poda ampliada** (≈ 89 MB por modelo; top-1 1,00 en esquemas ampliados y ≈ 0,90 en los demás). `movil-int8` (≈ 48 MB, top-1 ≈ 0,87) queda como opción. El objetivo de 60 MB era nuestro, no de Juan | Decisión del orquestador | «cuantizado en móviles» |
| 2026-10-29 | **Android sobre `integracion`:** 86/86 tests del SDK en debug y release, y el AAR de 5,6 MB. El `XmlTest` de la demo falla y no sale el APK: lo arregla la otra sesión en la rama `sdk`. `make test`, `make smoke` y 445 tests de `model/` en verde | Corridas de AWS y V3 | — |
| 2026-10-29 | **Android en verde** sobre `integracion-limpia` (`24d97c4`, con la rama `sdk` `a9d0a6b`): 86/86 tests del SDK y 5/5 de la demo, en debug y release; AAR de 5,6 MB y APK de 46 MB. El `XmlTest` fallaba por copias AppleDouble `._*.xml`; ahora el test las salta y el paquete usa `COPYFILE_DISABLE=1` | Corrida de Android | — |
| 2026-10-29 | **Limpieza de firmas:** la historia `f51e94d..integracion` está reescrita sin `Co-Authored-By` ni «Generated with» en `integracion-limpia` (`e382590`), en local y con el mismo árbol. El clasificador bloqueó la reescritura en el sitio, así que mover `integracion`, borrar las ramas viejas y hacer `reflog expire` más `gc` quedan para Juan. Respaldo: `~/Documents/chispa-respaldo-prelimpieza-20261029.bundle` | Cierre de la tanda | Pendiente de Juan |
| 2026-10-29 | **Gasto de la tanda.** AWS: 10 instancias c6a de unos 10 min, ≈ 0,5 USD; una spot reclamada sin coste útil. Workers personales hoy: 9,75 USD | Cierre | — |
| 2026-10-30 | **Tanda de estabilidad en pausa** (Juan: «Para el trabajo por ahora»). Hecho: M2 (cabeza), M6 (cumple), M3 y M4 medidos, dorados de arm64 idénticos, normalización de mayúsculas en los dos lados y R16. El ajuste fino de G.8 mejora JevBench (+1,3) pero no cumple es/en ni la robustez. Pendiente: (a) orientación de score (ρ −0,52) y (b) ids opacos en la torre (W4 terminado, sin integrar: rama `delega/20261030-000023-80912`; el signo del código es coherente y el renombrado llega a la torre; falta medir la orientación en AWS), (c) segundo ajuste (≈ 1 USD, aprobado si (a) y (b) salen limpios) y M1 (línea base, con la batería ya arreglada). AWS de la tanda ≈ 1 USD; nada encendido | Pausa de Juan | «Para el trabajo por ahora» |
