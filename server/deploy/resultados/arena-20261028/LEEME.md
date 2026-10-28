# T2.6d, ASR de la Arena con la cascada nueva (c6a, 2026-10-28)

Detector `chispa-cascada`: llama a `/v1/decide` de `chispa-server -tags ort`. Lleva un `.chispa` con L0TF y L2c entrenado
por `chispa train --conjunta` con el train de cada dimensión de la Arena. Engañar al detector = contestar mal sin escalar.

| dimensión | ASR del detector cascada | escala | ASR del enjambre con cascada | ASR del enjambre base | mejor detector base |
|---|---|---|---|---|---|
| injection | **0,021** | 47 % | 0,164 | 0,251 | 0,143 (sub) |
| spam | **0,021** | 83 % | 0,075 | 0,081 | 0,143 (words) |

- **Criterio de T2.6 (ASR ≤ 0,15): se cumple** con el detector cascada en las dos dimensiones. En el enjambre baja el ASR de
  injection de 0,251 a 0,164.
- **Pero escala mucho.** El ASR es bajo en parte porque el detector se abstiene en el 47 % de los ataques de injection y
  en el 83 % de los de spam. El criterio no limita la abstención; en producto, eso es la carga que pasa a L3 o a una
  persona. Medir y fijar la abstención sobre tráfico **no adversarial** queda pendiente.
- **Corridas incompletas.**
  - La corrida «solo» tuvo errores del servidor: 5.759 en spam, por saturación al principio. El detector escala ante un
    error, así que no inflan el ASR, pero sí el escalado.
  - La del enjambre: 1 error en injection y 85 en spam.
  - El tope de 15 min dejó 22–27 k ataques de los 37 k pedidos. Por eso el script marca FALLO; no es un error de
    medida.
- **user-data comprimido.** El script pasaba de 16 KB y se lanzó con gzip.
- **Coste:** una c6a de 27 min, ≈ 0,06 USD.
