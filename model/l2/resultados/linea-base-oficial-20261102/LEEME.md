# M1: línea base oficial de regresión (2026-11-02)

**Línea base oficial actual:** `linea-base.json`.

- **Modelo:** el ajuste 1 de G.8 (`s3://chispa-pruebas-879381269751/ajuste-80ab8ef/ckpt/mejor.pt`), con texto de torre v1.
  `.chispa` de `chispa train --ckpt --perfil servidor --torre` (945 MB).
- **Código y máquina:** `integracion-limpia` `dea0e88` (con `sdk` `3b579a3`, ZY: torres nuevas hasta 256), en una c6a.2xlarge. Sustituye a la primera corrida (`4b49db4`), que dejó clinc150 sin medir.
- **Servidor:** `/healthz` da `{"capas":{"L0":false,"L1":false,"L2":true,"L3":false},"torre_al_vuelo":true,"texto_torre":"v1"}`.
- **Batería** `sdk/python/ejemplos/bateria.json`, sin `--robustez` y con los umbrales de latencia relajados: 11 000 preguntas.
  Las dos corridas dan **exactitud 0,6436 y F1 0,5769**, idénticas: es determinista.

| conjunto | n | exactitud (argmax) | F1 macro | escalado |
|---|---|---|---|---|
| JevBench | 231 | 0,489 | 0,484 | 91 % |
| massive | 2974 | 0,413 | 0,344 | 96 % |
| clinc150 | 5500 | 0,715 | 0,763 | 83 % |
| hatecheck | 361 | 0,476 | 0,465 | 100 % |
| spam | 1450 | 0,926 | 0,926 | 99 % |
| inyecciones | 116 | 0,491 | 0,344 | 100 % |
| herramientas | 368 | 0,633 | 0,609 | 83 % |

**clinc150:** en la primera corrida salió 100 % sin probs por el tope `max_torres_nuevas = 64` (150 opciones). Con ZY se mide: 0,715. Ninguna fila queda incompleta ni sin presupuesto de torres.

**Escalado alto:** `tau_escalate_l2` es 0,93, y la exactitud es la del argmax de `probs`. Los umbrales propuestos están en
`umbrales-propuestos.json`, sin aplicar al manifiesto.

**Siguiente:** cuando haya un modelo mejor (el ajuste v2), se repite M1 con él.
