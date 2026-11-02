# Batería de regresión: bateria-chispa

Fuente: `/opt/chispa/g8.chispa` · objetivo de precisión: 0,95 · 2026-11-02T17:07:18

## Global
|  | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| global | 11000 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,8 | 3,2 |

## Por tipo
| tipo | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| choice | 8981 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,9 | 3,2 |
| noul | 2001 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,4 | 2,4 |
| score | 18 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,6 | 2,3 |

## Por grupo
| grupo | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 202,2 |
| prueba | 10769 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,8 | 3,2 |

## Por conjunto
| conjunto | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,5 | 202,2 |
| massive | 2974 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,6 | 2,6 |
| clinc150 | 5500 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 2,0 | 3,3 |
| hatecheck | 361 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,4 | 2,3 |
| spam | 1450 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,4 | 2,4 |
| inyecciones | 116 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,4 | 2,3 |
| herramientas | 368 | sin medir | sin medir | 0,000 | 100,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 1,6 | 2,4 |

## Conjuntos omitidos
- massive-nv: sin datos: ${CHISPA_DATOS}/no_vistas/massive.jsonl
- hatecheck-nv: sin datos: ${CHISPA_DATOS}/no_vistas/hatecheck.jsonl
- inyecciones-nv: sin datos: ${CHISPA_DATOS}/no_vistas/inyecciones.jsonl
- clinc150-control: sin datos: ${CHISPA_DATOS}/no_vistas/clinc150_control.jsonl
- herramientas-control: sin datos: ${CHISPA_DATOS}/no_vistas/herramientas_control.jsonl

Exactitud y F1 cuentan un error de petición o una fila sin respuesta como fallo. ECE con 10 cubos sobre la confianza de la mejor respuesta (en multi, una decisión por opción). Cobertura = fracción de decisiones que un umbral único de confianza acepta con precisión ≥ objetivo. p50/p99: cliente, extremo a extremo.


## CALIB del servidor
| Capa | Tipo | Origen | T | a | b | θ |
|---|---|---|---|---|---|---|
| L2 | choice | tipos_l2 | 0,022 | 0,000 | 0,000 | 0,500 |
| L2 | noul | tipos_l2 | 1,000 | 4,250 | -3,804 | 0,500 |
| L2 | score2 | tipos_l2 | 1,000 | 4,000 | 2,000 | 0,500 |
| L2 | score3 | tipos_l2 | 1,000 | 3,857 | 2,130 | 0,500 |
| L2 | score3#1 | tipos_l2 | 1,000 | 0,753 | 0,000 | 0,500 |
| L2 | score4 | tipos_l2 | 1,000 | 3,945 | 2,046 | 0,500 |
| L2 | score4#1 | tipos_l2 | 1,000 | 0,715 | 0,000 | 0,500 |
| L2 | score4#2 | tipos_l2 | 1,000 | 0,709 | 0,000 | 0,500 |
| L2 | score5 | tipos_l2 | 1,000 | 3,950 | 2,032 | 0,500 |
| L2 | score5#1 | tipos_l2 | 1,000 | 0,718 | 0,000 | 0,500 |
| L2 | score5#2 | tipos_l2 | 1,000 | 0,725 | 0,000 | 0,500 |
| L2 | score5#3 | tipos_l2 | 1,000 | 0,722 | 0,000 | 0,500 |

τ de L2: tau_escalate = 0,933, tau_l2_esquema_nuevo = 0,846
AVISO: la CALIB de L2 no trae multi: esa capa usa parámetros por defecto o no opina en esos tipos.
