# T2.2d: conjunta con la cabeza ajustada fuera de pliegue en test, calibración y cascada con L0 completo (m6a, 2026-10-28)

En CPU, sobre las características de T2.2c. Partición de test a 2 pliegues por hash del `id`, la misma que eligió τ en
T2.7.

## H1, cabeza `cvtest`: se cumple
| tarea | L0 completo | L2+sop | conjunta (train) | **conjunta (cvtest)** | Δ vs mejor capa | listón |
|---|---|---|---|---|---|---|
| massive | 0,794 | 0,632 | 0,817 | **0,818** | +2,4 | 0,644 |
| clinc150 | 0,877 | 0,775 | 0,890 | **0,891** | +1,4 | 0,771 |
| herramientas | 0,696 | 0,504 | 0,729 | **0,734** | +3,8 | 0,661 |
| inyecciones | 0,843 | 0,922 | 0,931 | **0,922** | 0,0 | 0,793 |
| hatecheck | 0,592 | 0,630 | 0,571 | **0,667** | +3,7 | 0,550 |

- hatecheck se recupera: sube 9,6 puntos frente a la cabeza `train` y supera a L2 en 3,7.
- Ninguna tarea pierde más de 1 punto.
- La conjunta supera a la mejor capa en 4/5 y pasa el listón en 5/5.
- **Cuidado.** `cvtest` entrena la cabeza con la mitad del test de cada tarea. En producto equivale a ajustar la cabeza
  con datos del cliente (los de L0), no a un modelo genérico.

## H3, (b) frente a (c) con el mismo L0 completo: (b) gana en 4/5
Punto «calidad», L0c → L2b-sop frente a la conjunta (cvtest):
- massive 0,794 vs 0,818;
- clinc150 0,877 vs 0,891;
- herramientas 0,680 vs 0,734;
- hatecheck 0,649 vs 0,667;
- inyecciones 0,931 vs 0,922.

La cascada L0c → conjunta en su punto «rápida» pasa el listón en 5/5 sin perder más de 1 punto en ninguna tarea.

## H2, calibración (criterio de T2.4): refutada
- **Qué se cumple.** ECE ≤ 0,05 en clinc150, massive y herramientas. Cobertura a precisión 0,95 ≥ 70 % solo en clinc150
  (80 %) y massive (72 %).
- **hatecheck y herramientas.** Con macro-F1 de 0,67 y 0,73 no pueden cubrir el 70 % con precisión 0,95: el criterio no
  se alcanza mientras la calidad siga en ese nivel.
- **inyecciones.** Con n = 116, la temperatura ajustada en pliegues de 58 filas sobreajusta: el ECE sube de 0,053 a 0,143.
  Con tan pocos datos conviene no calibrar.
- **AUROC de `escalate`.** 0,893 en clinc150 (`oos`) y 0,535 en herramientas. En herramientas la conjunta no detecta lo
  que no sabe.
- Cambiar los umbrales de T2.4 es decisión de Juan.

## Coste
Una m6a.xlarge on-demand, porque no había capacidad spot; unos 20 min y menos de 0,1 USD.
