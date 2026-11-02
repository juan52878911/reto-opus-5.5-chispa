# Ajuste v3 (desde v2, con Clandestino y el aumento en español, 2 épocas, sin traducción). g5, 26 min, ≈ 0,45 USD. **No cumple.**

| criterio | v3 | v2 | ¿cumple? |
|---|---|---|---|
| JevBench, sin perder más de 1 punto frente a v2 | 0,4892 | 0,5022 | **no** (−1,3) |
| es − en, mejor que −2,6 | −3,0 | −3,0 (en esta máquina) | **no** |
| paráfrasis por debajo de 11,9 % | 12,0 % | 11,9 % | **no** |
| erratas por debajo de 11 % | 12,6 % | 11,0 % | **no** |
| renombrar y mayúsculas sin empeorar | 0 % · 5,0 % | 0 % · 4,2 % | renombrar sí; todo en mayúsculas **no** (+0,8) |

- **Clandestino:** 9998 frases leídas, 1625 de IA y 6479 con PII descartadas (Yes o Maybe en Q7, el 77 % de las humanas). Quedan
  30 055 filas: train 23 963, dev 3091, test 3001.
- No se repite la batería M1 con v3: el criterio ya falla en .
- Checkpoint: `s3://chispa-pruebas-879381269751/v3-ff359773/ckpt/mejor.pt`, guardado pero sin usar.
