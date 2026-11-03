# Hito 2: τ por conjunto con validación, sobre la línea base oficial (M1), 2026-11-03

- **Modelo:** `modelo-servidor.chispa`, el ajuste 1 en fp32, la misma línea base oficial. La exactitud de argmax en test coincide con M1 (clinc150 0,7155 frente a 0,715).
- **Servidor:** sin `-config`, como en M1 (L2 sola).
- **Máquina y coste:** el i7 (CT 109), 0 USD.
- **Elección de τ:**
  - se elige en calibración: el split dev de cada conjunto (hasta 1500 filas) o, en herramientas, que no tiene dev, la mitad de test por plantilla;
  - es el τ con más cobertura y precisión ≥ 0,85;
  - luego se aplica a test sin tocarlo.
- **Criterio del plan:** escalada ≤ 30 % con precisión ≥ 0,85, al menos en clinc150, spam y herramientas.

| conjunto | calibración | τ elegido | cobertura / precisión en cal. | **escalada en test** | **precisión cuando no escala (test)** | escalada actual (τ 0,93) | cumple |
|---|---|---|---|---|---|---|---|
| clinc150 | dev | 0,077 | 0,94 / 0,851 | **11,0 %** | **0,777** | 100,0 % | no |
| spam | dev | 0,500 | 1,00 / 0,939 | **0,0 %** | **0,926** | 99,2 % | sí |
| herramientas | ½ test por plantilla | 0,276 | 0,48 / 0,852 | **55,7 %** | **0,832** | 98,5 % | no |
| massive | dev | 0,406 | 0,10 / 0,854 | **90,7 %** | **0,848** | 100,0 % | no |
| hatecheck | dev | 0,714 | 0,01 / 1,000 | **99,7 %** | **1,000** | 100,0 % | no |
| inyecciones | dev | 0,718 | 0,22 / 0,850 | **77,6 %** | **0,885** | 100,0 % | no |

## Resultado
- **Solo spam cumple:** τ 0,50, 0 % de escalada y precisión 0,926.
- **clinc150 no cumple.**
  - En dev, τ 0,077 da cobertura 0,94 con precisión 0,85.
  - En test la precisión cae a 0,777 con un 11 % de escalada. Dev y test de clinc_oos no se parecen lo bastante (test trae más casos difíciles) para que el τ de dev aguante.
  - Para llegar a 0,85 en test haría falta escalar bastante más.
- **herramientas no cumple:** para precisión 0,85 escala el 56 % (0,83 en test).
- **massive, hatecheck e inyecciones,** fuera del criterio, quedan muy lejos: escalan el 78–100 %.
- **Conclusión, dicha como pide el plan:** con el modelo de la línea base, el zero-shot de Chispa no consigue un τ vendible (≤ 30 % de escalada con precisión ≥ 0,85) en clinc150 ni en herramientas. Es la prueba de que el zero-shot, tal como está, no vende; solo spam (binaria y fácil) lo logra.
- **Ficheros:** `tau.json` con el detalle por conjunto. El script es `model/bench/tau/calibrar_tau.py`.
