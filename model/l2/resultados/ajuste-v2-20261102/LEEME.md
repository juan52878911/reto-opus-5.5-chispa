# Ajuste fino v2 de G.8: texto de torre sin id, aumento y W5 (g5.xlarge, `23b38e6`, 26 min, ≈ 0,45 USD)

Checkpoint: `s3://chispa-pruebas-879381269751/ajuste-v2-23b38e6/ckpt/mejor.pt`, con `texto_torre = v2_sin_id`.
**Es el mejor modelo hasta ahora.**

| criterio | v2 | G.8 | ¿cumple? |
|---|---|---|---|
| JevBench k = 0 | **0,5022** (F1 0,341) | 0,4805 (0,301) | sí (+2,2) |
| es − en | **−2,6** | −3,3 | sí (< 3) |
| renombrar < 5 % | **0,0 %** | 36,9 % | sí |
| todo en mayúsculas < 5 % | **4,2 %** | 6,1 % | sí |
| ninguna variante > 5 % en L2 | erratas 11,0 · esquema en inglés 10,5 · largo 54,1 · mezcla 5,2 · paráfrasis 11,9 · pregunta en inglés 20,1 | | **no** (6 de 9) |

- **El texto de torre sin id elimina la dependencia del nombre de la opción:** renombrar cae del 37 % al 0 %.
- **Queda por encima del 5 %:**
  - el ruido de superficie del mensaje: erratas, frases añadidas y mezcla;
  - el idioma de la pregunta o del esquema;
  - la paráfrasis de la pregunta.

  La «mezcla de mayúsculas» de E2 queda sin criterio: 23,5 %.
- **Pendiente:** M1 con este modelo, que pasa por el servidor. Espera al arreglo de la caché de torres v2 (R20) de la otra
  sesión.
