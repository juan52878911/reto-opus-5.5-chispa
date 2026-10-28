# T2.7 Medir la cascada completa L0 → L1 → L2 frente al listón (opción (c))

Decisión de Juan del 2026-10-28: «C y después b». L2 falla T2.1 y T2.2 por sí solo
(`model/l2/resultados/ronda3-t22/LEEME.md`). Queda como capa de respaldo, y lo que se juzga ahora es lo que ve el
producto: la cascada del servidor (`server/decide/cascada.go`). Cada capa responde si su confianza top-1 es ≥ τ; si no,
pasa a la siguiente, y la última responde siempre.

## Hipótesis
- En las tareas de muchas clases L0 acierta más que L2. En las de pocas clases, o con poco train, L2 acierta más.
  La confianza de cada capa separa bien sus aciertos de sus fallos. Por eso una cascada con τ elegidos sin mirar el test
  llega a ≥ 0,95 × la mejor referencia (el criterio de T2.2) en ≥ 4 de las 5 tareas, con la latencia media dominada por L0.
- Se refuta si la cascada no supera a la mejor capa sola en ninguna tarea, o si pierde más de 1 punto frente a ella en ≥ 2 tareas.

## Terminado cuando
- `model/cascada/` (paquete Python con tests propios) contiene:
  - `capas.py`: predicciones `{id, probs, ms}` por capa y tarea (formato de `model/esquema.md`) en test, para estas capas:
    - **L0**: el TF-IDF de caracteres con regresión logística de `model/lineas_base/correr.py`. Ya hay predicciones
      en `model/lineas_base/pred/*__l0_tfidf_lr.jsonl*`; reúsalas si traen `probs`, y si no, recalcúlalas con el mismo código.
    - **L1-zs**: lo que hace hoy el servidor (`server/decide/l1.go`): coseno de potion-multilingual-128M entre el mensaje y
      «pregunta · opción · descripción». choice usa softmax(coseno/T) con la T por defecto del servidor; noul y score, igual
      que en `l1.go`. Hazlo en Python con el modelo de `~/hf` y comprueba en 50 frases que coincide con `runtime/l1`
      (mismo top-1).
    - **L1-proto**: potion con prototipos por clase, la media normalizada de los vectores de train de cada clase, y
      softmax(coseno/T). Es una capa candidata, no la del servidor; va marcada así en el informe.
    - **L2**: lee las predicciones ya hechas, `pred_soporte/<tarea>.jsonl` (con soporte) y `pred/<tarea>.jsonl` (sin
      soporte), de dos rondas: T2.1b `l2-20261028b` y T2.2 `l2-20261028c`.
  - `cascada.py`: dada una lista ordenada de capas, elige τ por capa y tarea y devuelve la decisión, la capa que respondió y
    el coste en ms.
    - Elige τ **sin mirar el fragmento que evalúa**: validación cruzada a 2 pliegues sobre test, partiendo por hash del `id`
      con semilla fija. τ se elige en un pliegue y se evalúa en el otro, y al revés. No hay predicciones de L2 en dev, por eso.
    - Dos puntos de operación:
      - «calidad»: τ que maximiza el macro-F1 en el pliegue de ajuste;
      - «rápida»: la mayor cobertura de las capas tempranas con una precisión ≥ 0,95 en lo que aceptan.
  - `informe.py`: escribe `model/cascada/resultados/<fecha>/informe.md` y `resultados.json`. Por tarea y punto de operación:
    - macro-F1 de cada capa sola y de la cascada;
    - el listón: 0,95 × el máximo entre L0, e5 kNN-32 y el maestro Qwen, con las cifras de `model/lineas_base/informe.md`
      y `model/l2/resultados/ronda3-t22/delta.md`;
    - si pasa;
    - qué fracción responde cada capa;
    - la latencia media y la p99 esperadas en el i7. Usa L0 ≈ 6 µs (`server/README.md`), L1 = 166 µs y
      L2 = 30,6 ms a 64 tokens (`model/bench/i7/resultados.md`), y cita la fuente de cada cifra;
    - un oráculo, la mejor capa por fila, como techo.
    - Cascadas a medir: L0 → L2, L0 → L1-zs → L2, L0 → L1-proto → L2 y L1-proto → L2, cada una con L2 de las dos rondas.
- Tareas: las 5 de T2.2 (massive, clinc150, herramientas, hatecheck, inyecciones). Los conjuntos del listón humano no
  tienen train para L0: quedan fuera, y el informe lo dice.
- `model/cascada/aws/arranque.sh`: user-data para Amazon Linux 2023 x86_64 con el patrón de `model/l2/aws/arranque.sh`:
  - marcador `__CHISPA_S3__`, `shutdown -h +60` y un trap que sube `log.txt` y `resultados.tgz`;
  - descargas de S3 **por fichero**: el rol de la instancia tiene Get/Put y no List, así que nada de `--recursive` ni `sync`;
  - código en `$CHISPA_S3/codigo.tgz`. Los datos convertidos salen de las mismas claves que usa `model/l2/aws/arranque.sh`
    (`model/meta/resultados/conversion-20261027.json`). Las predicciones de L2 están en
    `s3://chispa-pruebas-879381269751/l2-20261028b/pred.tgz` y `…/l2-20261028c/pred.tgz`, y cada una se desempaqueta en
    `pred/<tarea>.jsonl` y `pred_soporte/<tarea>.jsonl`;
  - potion se baja de Hugging Face, porque la instancia tiene red;
  - pasos: instala Python y las dependencias, calcula L0, L1-zs y L1-proto, corre la cascada y sube el informe.
  - Su `aws/empaquetar.sh`, con `find` y `tar` portables, sin `-C` combinado con `-T`, porque también se ejecuta con bsdtar.
- Prueba en seco aquí, en la VM, que no tiene S3:
  - tests con fixtures diminutas (3 tareas inventadas);
  - una corrida real de L0 → L1-zs y L0 → L1-proto sobre los datos del golden, sin L2. Pega la tabla en el informe;
  - `CHISPA_LOCAL=1 bash model/cascada/aws/arranque.sh` con fixtures;
  - `bash -n` de los scripts.
- `python -m unittest discover -s model -t .`, `make test` y `make smoke` en verde.
- Parada: si algo falla 2 veces, márcalo y para.

## Zona
- Solo `model/cascada/**`. No toques `server/`, `model/l2/` ni `model/lineas_base/`; si hace falta algo de ellos, impórtalo.
- Rama: la que te da delega. Commits simples, sin firmas. Sin push ni merge.

## Entorno
- `source ~/.profile`. Python en `~/venv`, modelos en `~/hf`, Go en `~/go-sdk/bin` y datasets en `~/datos`.
- Sin red salvo la API de Claude.
- Línea base: la rama `claude/chispa-plan-83616c` en el sha con el que te lanzan.
- No vuelques datos ni predicciones en el contexto: usa `head` o cuenta filas. Las PQRS no entran.

## Tope
- ≤ 120 min de reloj · ≤ 6 USD de cuenta · cómputo de pago: 0. Sin subagentes.

## Informe
Termina con un informe de ≤ 15 líneas:
- rama y sha;
- la tabla L0 → L1 de la prueba en seco;
- qué sustituyo para lanzar `arranque.sh` (claves de S3 y marcadores);
- qué quedó sin verificar y qué recomiendas.
