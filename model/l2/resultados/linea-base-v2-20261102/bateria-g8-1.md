# Batería de regresión: bateria-chispa

Fuente: `/opt/chispa/g8.chispa` · objetivo de precisión: 0,95 · 2026-11-02T20:24:56

## Global
|  | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | incompletas | sin presup. torres | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| global | 11000 | 0,584 | 0,958 | 0,056 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 94,2 % | 0,530 | 0,110 | 16,4 % | 94,2 % | 0,0 % | 24,1 | 178,9 |

## Por tipo
| tipo | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | incompletas | sin presup. torres | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| choice | 8981 | 0,535 | 0,956 | 0,065 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 93,2 % | 0,530 | 0,106 | 9,2 % | 93,2 % | 0,0 % | 23,3 | 58,0 |
| noul | 2001 | 0,806 | 1,000 | 0,014 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 98,6 % | 0,587 | 0,129 | 57,4 % | 98,6 % | 0,0 % | 30,7 | 200,5 |
| score | 18 | 0,111 | sin medir | 0,000 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 100,0 % | 0,253 | 0,316 | 0,0 % | 100,0 % | 0,0 % | 38,4 | 222,8 |

## Por grupo
| grupo | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | incompletas | sin presup. torres | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | 0,472 | 0,889 | 0,069 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 92,2 % | 0,469 | 0,063 | 6,9 % | 92,2 % | 0,0 % | 119,4 | 297,4 |
| prueba | 10769 | 0,586 | 0,960 | 0,056 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 94,2 % | 0,570 | 0,112 | 19,6 % | 94,2 % | 0,0 % | 24,0 | 39,5 |

## Por conjunto
| conjunto | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | incompletas | sin presup. torres | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | 0,472 | 0,889 | 0,069 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 92,2 % | 0,469 | 0,063 | 6,9 % | 92,2 % | 0,0 % | 119,4 | 297,4 |
| massive | 2974 | 0,353 | 0,866 | 0,037 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 95,7 % | 0,309 | 0,032 | 0,4 % | 95,7 % | 0,0 % | 22,5 | 30,9 |
| clinc150 | 5500 | 0,631 | 0,983 | 0,074 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 92,5 % | 0,671 | 0,186 | 29,2 % | 92,5 % | 0,0 % | 23,5 | 32,3 |
| hatecheck | 361 | 0,488 | sin medir | 0,000 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 100,0 % | 0,478 | 0,092 | 0,0 % | 100,0 % | 0,0 % | 25,6 | 41,3 |
| spam | 1450 | 0,923 | 1,000 | 0,020 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 98,0 % | 0,923 | 0,216 | 93,1 % | 98,0 % | 0,0 % | 31,1 | 42,4 |
| inyecciones | 116 | 0,483 | sin medir | 0,000 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 100,0 % | 0,326 | 0,230 | 23,3 % | 100,0 % | 0,0 % | 34,2 | 66,1 |
| herramientas | 368 | 0,595 | 0,981 | 0,141 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 85,6 % | 0,575 | 0,076 | 20,7 % | 85,6 % | 0,0 % | 27,3 | 34,2 |

MAE de score (niveles): jevbench 1,167

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
| L2 | noul | tipos_l2 | 1,000 | 4,254 | -3,800 | 0,500 |
| L2 | score10 | tipos_l2 | 1,000 | 4,006 | 1,987 | 0,500 |
| L2 | score10#1 | tipos_l2 | 1,000 | 0,697 | 0,000 | 0,500 |
| L2 | score10#2 | tipos_l2 | 1,000 | 0,688 | 0,000 | 0,500 |
| L2 | score10#3 | tipos_l2 | 1,000 | 0,684 | 0,000 | 0,500 |
| L2 | score10#4 | tipos_l2 | 1,000 | 0,684 | 0,000 | 0,500 |
| L2 | score10#5 | tipos_l2 | 1,000 | 0,684 | 0,000 | 0,500 |
| L2 | score10#6 | tipos_l2 | 1,000 | 0,682 | 0,000 | 0,500 |
| L2 | score10#7 | tipos_l2 | 1,000 | 0,680 | 0,000 | 0,500 |
| L2 | score10#8 | tipos_l2 | 1,000 | 0,685 | 0,000 | 0,500 |
| L2 | score2 | tipos_l2 | 1,000 | 4,000 | 2,000 | 0,500 |
| L2 | score3 | tipos_l2 | 1,000 | 3,851 | 2,134 | 0,500 |
| L2 | score3#1 | tipos_l2 | 1,000 | 0,756 | 0,000 | 0,500 |
| L2 | score4 | tipos_l2 | 1,000 | 3,943 | 2,048 | 0,500 |
| L2 | score4#1 | tipos_l2 | 1,000 | 0,716 | 0,000 | 0,500 |
| L2 | score4#2 | tipos_l2 | 1,000 | 0,710 | 0,000 | 0,500 |
| L2 | score5 | tipos_l2 | 1,000 | 3,947 | 2,035 | 0,500 |
| L2 | score5#1 | tipos_l2 | 1,000 | 0,719 | 0,000 | 0,500 |
| L2 | score5#2 | tipos_l2 | 1,000 | 0,727 | 0,000 | 0,500 |
| L2 | score5#3 | tipos_l2 | 1,000 | 0,723 | 0,000 | 0,500 |
| L2 | score6 | tipos_l2 | 1,000 | 4,013 | 1,980 | 0,500 |
| L2 | score6#1 | tipos_l2 | 1,000 | 0,686 | 0,000 | 0,500 |
| L2 | score6#2 | tipos_l2 | 1,000 | 0,687 | 0,000 | 0,500 |
| L2 | score6#3 | tipos_l2 | 1,000 | 0,689 | 0,000 | 0,500 |
| L2 | score6#4 | tipos_l2 | 1,000 | 0,700 | 0,000 | 0,500 |
| L2 | score7 | tipos_l2 | 1,000 | 4,008 | 1,985 | 0,500 |
| L2 | score7#1 | tipos_l2 | 1,000 | 0,692 | 0,000 | 0,500 |
| L2 | score7#2 | tipos_l2 | 1,000 | 0,690 | 0,000 | 0,500 |
| L2 | score7#3 | tipos_l2 | 1,000 | 0,708 | 0,000 | 0,500 |
| L2 | score7#4 | tipos_l2 | 1,000 | 0,692 | 0,000 | 0,500 |
| L2 | score7#5 | tipos_l2 | 1,000 | 0,698 | 0,000 | 0,500 |

τ de L2: tau_escalate = 0,910, tau_l2_esquema_nuevo = 0,846
AVISO: la CALIB de L2 no trae multi: esa capa usa parámetros por defecto o no opina en esos tipos.
