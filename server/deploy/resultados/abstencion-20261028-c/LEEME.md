# T4.6c medido: τ de L2c elegido sobre dev (c6a, 2026-10-28)

Criterio de cada tarea: escalar ≤ 20 % con tráfico normal y precisión ≥ 0,95 en lo contestado (Juan: abstención máxima
20 %).

| tarea | τ (método) | escala | precisión de lo contestado | con abstención exacta del 20 %, precisión |
|---|---|---|---|---|
| clinc150 | 0,601 (dev, 3.223 filas) | 11,7 % | 0,918 | 0,949 |
| massive | 0,713 (dev, 2.053 filas) | 22,2 % | 0,933 | 0,929 |
| injection | 0,992 (dev, 152 filas) | 24,1 % | 1,000 | 1,000 |
| spam | 0,998 (dev, 152 filas) | 84,3 % | 1,000 | 1,000 |

- **clinc150 y massive: límite del modelo, anotado.** Ningún τ cumple las dos condiciones a la vez: con una abstención del
  20 %, la precisión es 0,949 en clinc150 y 0,929 en massive. Ajustar el margen no lo arregla, por eso no hubo otra
  corrida. Elegido sobre dev, el τ estima la precisión 0,02–0,03 por encima de la real.
- **ASR de la Arena con este τ:** detector cascada solo / en el enjambre: injection 0,015 / 0,022 y spam 0,019 / 0,017.
- **Arena:** con 152 filas de dev, todas correctas y confiadas, τ ≈ 0,99 y escala mucho. Lo intenta arreglar T4.6d.
