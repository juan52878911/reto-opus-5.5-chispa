# Pong: redacción de las opciones y acierto de Chispa zero-shot (CT 109, servidor fp32), 2026-11-02

Una partida por redacción, Chispa (pala derecha) contra el jugador óptimo, en tiempo real (30 tics/s), semilla 1.
Mismas 3 opciones barajadas; «acierto» = % de decisiones que eligen la opción óptima (la de menor distancia).

| redacción | marcador | duración | acierto | entropía normalizada | qué elige | p50 / p99 ms | decisiones/s |
|---|---|---|---|---|---|---|---|
| px («subir: la pala queda a 12 px del punto de corte») | 0–7 | 48,8 s | 16,5 % | 0,974 | «quieta» el 94 % | 12 / 122 | 21,2 |
| cualitativa («subir: lleva la pala al punto donde llegará la pelota, la alcanza» / «…, falla») | 0–7 | 14,2 s | **5,4 %** | 0,994 | opciones que dicen «falla» el 79 % | 7 / 81 | 27,4 |

- **El azar daría 33 %.** Con las dos redacciones Chispa queda por debajo.
- **Con px** se fija en la palabra de la acción (casi siempre «quieta»).
- **Con la cualitativa** la distribución es aún más plana y se va hacia las opciones que dicen «falla».
  - No distingue «la alcanza» de «falla»: el embedding de la opción se parece al de la pregunta por las palabras compartidas
    (pala, pelota, punto), no por si el resultado es bueno.
- Prueba anterior con px, también contra el óptimo: 22,4 %, «quieta» el 84 %.
