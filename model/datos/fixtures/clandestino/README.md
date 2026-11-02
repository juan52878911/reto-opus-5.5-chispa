Muestra de `microsoft/Clandestino` (GitHub, licencia MIT, con la condición de uso de Microsoft: «no dañar», sin
vigilancia; aceptada por Juan el 2026-11-02). Son las primeras filas de `data/clandestino_no_ontology_42023.json` en su
formato real, una fila JSON por línea.

- 16 filas en las que ningún anotador marca PII = Yes (Question 7). 3 de ellas tienen algún Maybe y, desde la regla
  «Maybe cuenta como Yes» (2026-11-02), también se descartan: quedan 13 válidas.
- 2 filas con PII, con `Sentence` sustituido: sirven para probar el descarte.
- 1 fila marcada `IsAIGenerated: "True"`, inventada a partir de una real: sirve para probar el filtro.
