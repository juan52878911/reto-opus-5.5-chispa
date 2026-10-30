# Batería de regresión: bateria-chispa

Fuente: `/opt/chispa/g8.chispa` · objetivo de precisión: 0,95 · 2026-10-30T02:26:35

## Global
|  | n | exactitud | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| global | 11000 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,9 | 3,5 |

## Por tipo
| tipo | n | exactitud | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| choice | 8981 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 2,0 | 3,5 |
| noul | 2001 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 2,6 |
| score | 18 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,4 | 2,1 |

## Por grupo
| grupo | n | exactitud | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 250,2 |
| prueba | 10769 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,9 | 3,5 |

## Por conjunto
| conjunto | n | exactitud | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 250,2 |
| massive | 2974 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,7 | 3,0 |
| clinc150 | 5500 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 2,2 | 3,6 |
| hatecheck | 361 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 2,4 |
| spam | 1450 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 2,6 |
| inyecciones | 116 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,4 | 2,4 |
| herramientas | 368 | 0,000 | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,6 | 2,8 |

## Conjuntos omitidos
- massive-nv: sin datos: ${CHISPA_DATOS}/no_vistas/massive.jsonl
- hatecheck-nv: sin datos: ${CHISPA_DATOS}/no_vistas/hatecheck.jsonl
- inyecciones-nv: sin datos: ${CHISPA_DATOS}/no_vistas/inyecciones.jsonl
- clinc150-control: sin datos: ${CHISPA_DATOS}/no_vistas/clinc150_control.jsonl
- herramientas-control: sin datos: ${CHISPA_DATOS}/no_vistas/herramientas_control.jsonl

Exactitud y F1 cuentan un error de petición o una fila sin respuesta como fallo. ECE con 10 cubos sobre la confianza de la mejor respuesta (en multi, una decisión por opción). Cobertura = fracción de decisiones que un umbral único de confianza acepta con precisión ≥ objetivo. p50/p99: cliente, extremo a extremo.
