# M1: línea base oficial de regresión (2026-11-02)

**Línea base oficial actual:** `linea-base.json`.

- **Modelo:** el ajuste 1 de G.8 (`s3://chispa-pruebas-879381269751/ajuste-80ab8ef/ckpt/mejor.pt`), con texto de torre v1.
  `.chispa` de `chispa train --ckpt --perfil servidor --torre` (945 MB).
- **Código y máquina:** `integracion-limpia` `4b49db4` (con `sdk` `ce1bfde`, verificado en VF18), en una c6a.2xlarge.
- **Servidor:** `/healthz` da `{"capas":{"L0":false,"L1":false,"L2":true,"L3":false},"torre_al_vuelo":true}`.
- **Batería** `sdk/python/ejemplos/bateria.json`, sin `--robustez` y con los umbrales de latencia relajados: 11 000 preguntas.
  Las dos corridas dan **exactitud 0,5718 y F1 0,2980**, idénticas: es determinista.

| conjunto | n | exactitud (argmax) | F1 macro | escalado |
|---|---|---|---|---|
| JevBench | 231 | 0,489 | 0,484 | 91 % |
| massive | 2974 | 0,413 | 0,344 | 96 % |
| clinc150 | 5500 | **sin medir: 100 % sin probs** | — | 100 % |
| hatecheck | 361 | 0,476 | 0,465 | 100 % |
| spam | 1450 | 0,926 | 0,926 | 99 % |
| inyecciones | 116 | 0,491 | 0,344 | 100 % |
| herramientas | 368 | 0,633 | 0,609 | 83 % |

**clinc150 sin probs:** el p50 es de 2 ms, así que L2 no corre. «Nadie opinó» es el 0 % y los errores, el 0 %. Sospecha: 150
opciones superan algún tope del runtime (opciones por pregunta o torres al vuelo) y la respuesta escala sin probs ni motivo. Lo
investiga la otra sesión.

**Escalado alto:** `tau_escalate_l2` es 0,93, y la exactitud es la del argmax de `probs`. Los umbrales propuestos están en
`umbrales-propuestos.json`, sin aplicar al manifiesto.

**Siguiente:** cuando haya un modelo mejor (el ajuste v2), se repite M1 con él.
