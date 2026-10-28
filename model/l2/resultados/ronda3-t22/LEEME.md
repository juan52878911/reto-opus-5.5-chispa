# T2.2, ronda 1 (g5.xlarge, 2026-10-28): no cumple

- Parte del mejor checkpoint de T2.1b, con 4 capas de e5 descongeladas, renombrado 0,3 y episodios con soporte.
- Con soporte, frente a 0,95 × la mejor referencia (máximo de L0, kNN-32 y el maestro): pasa en hatecheck (0,616) e
  inyecciones (0,957); falla en massive (0,604 frente a 0,644), CLINC (0,762 frente a 0,770) y herramientas (0,527 frente a 0,661).
- Caída al renombrar las opciones a A/B/C: 7,9 puntos en massive y 16,6 en CLINC. El criterio pide ≤ 5: no cumple.
- Descongelar casi no cambia nada frente a T2.1b (±0,03).
- Lectura del orquestador: en tres rondas, L0 (TF-IDF de caracteres con regresión logística) gana a todo lo basado en e5-small
  en las tareas de muchas clases (massive 60, CLINC 150, herramientas 32). Lo que limita es la representación, no la cabeza.
- La segunda iteración de T2.2 no se lanza sin Juan, porque las opciones cambian el diseño:
  (a) un codificador mayor (e5-base, unos 2× más lento; ojo con el p99 del i7, que hoy es de 30,6 ms con e5-small);
  (b) L2 con las características de L0 como entrada, en una cabeza conjunta;
  (c) aceptar L2 como capa de respaldo y medir la cascada completa (L0 → L1 → L2), que es lo que ve el producto.
- Coste: g5.xlarge on-demand, unas 2 h (≈ 2 USD).
