# Batería de regresión: bateria-chispa

Fuente: `/opt/chispa/g8.chispa` · objetivo de precisión: 0,95 · 2026-11-02T18:35:36

## Global
|  | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| global | 11000 | 0,572 | 0,919 | 0,019 | 50,0 % | 0,0 % | 48,0 % | 0,298 | 0,065 | 1,0 % | 98,0 % | 0,0 % | 5,2 | 149,4 |

## Por tipo
| tipo | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| choice | 8981 | 0,439 | 0,914 | 0,021 | 61,2 % | 0,0 % | 36,4 % | 0,263 | 0,026 | 1,2 % | 97,7 % | 0,0 % | 2,6 | 54,6 |
| noul | 2001 | 0,807 | 1,000 | 0,006 | 0,0 % | 0,0 % | 99,4 % | 0,596 | 0,132 | 56,6 % | 99,4 % | 0,0 % | 29,0 | 183,4 |
| score | 18 | 0,111 | sin medir | 0,000 | 0,0 % | 0,0 % | 100,0 % | 0,153 | 0,259 | 0,0 % | 100,0 % | 0,0 % | 24,1 | 212,5 |

## Por grupo
| grupo | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | 0,489 | 0,900 | 0,078 | 0,0 % | 0,0 % | 91,3 % | 0,484 | 0,086 | 5,2 % | 91,3 % | 0,0 % | 109,4 | 298,4 |
| prueba | 10769 | 0,575 | 0,921 | 0,017 | 51,1 % | 0,0 % | 47,1 % | 0,174 | 0,067 | 1,0 % | 98,1 % | 0,0 % | 3,3 | 37,0 |

## Por conjunto
| conjunto | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | 0,489 | 0,900 | 0,078 | 0,0 % | 0,0 % | 91,3 % | 0,484 | 0,086 | 5,2 % | 91,3 % | 0,0 % | 109,4 | 298,4 |
| massive | 2974 | 0,413 | 0,891 | 0,038 | 0,0 % | 0,0 % | 95,7 % | 0,344 | 0,025 | 2,1 % | 95,7 % | 0,0 % | 19,5 | 27,1 |
| clinc150 | 5500 | sin medir | sin medir | 0,000 | 100,0 % | 0,0 % | 0,0 % | 0,000 | sin medir | 0,0 % | 100,0 % | 0,0 % | 2,1 | 3,4 |
| hatecheck | 361 | 0,476 | sin medir | 0,000 | 0,0 % | 0,0 % | 100,0 % | 0,465 | 0,105 | 0,3 % | 100,0 % | 0,0 % | 22,8 | 34,4 |
| spam | 1450 | 0,926 | 1,000 | 0,008 | 0,0 % | 0,0 % | 99,2 % | 0,926 | 0,222 | 93,0 % | 99,2 % | 0,0 % | 29,5 | 38,9 |
| inyecciones | 116 | 0,491 | sin medir | 0,000 | 0,0 % | 0,0 % | 100,0 % | 0,344 | 0,201 | 18,1 % | 100,0 % | 0,0 % | 33,8 | 80,1 |
| herramientas | 368 | 0,633 | 0,968 | 0,163 | 0,0 % | 0,0 % | 83,2 % | 0,609 | 0,099 | 24,7 % | 83,2 % | 0,0 % | 22,1 | 28,0 |

MAE de score (niveles): jevbench 1,222

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
| L2 | noul | tipos_l2 | 1,000 | 4,253 | -3,800 | 0,500 |
| L2 | score10 | tipos_l2 | 1,000 | 4,006 | 1,987 | 0,500 |
| L2 | score10#1 | tipos_l2 | 1,000 | 0,697 | 0,000 | 0,500 |
| L2 | score10#2 | tipos_l2 | 1,000 | 0,688 | 0,000 | 0,500 |
| L2 | score10#3 | tipos_l2 | 1,000 | 0,684 | 0,000 | 0,500 |
| L2 | score10#4 | tipos_l2 | 1,000 | 0,684 | 0,000 | 0,500 |
| L2 | score10#5 | tipos_l2 | 1,000 | 0,684 | 0,000 | 0,500 |
| L2 | score10#6 | tipos_l2 | 1,000 | 0,681 | 0,000 | 0,500 |
| L2 | score10#7 | tipos_l2 | 1,000 | 0,680 | 0,000 | 0,500 |
| L2 | score10#8 | tipos_l2 | 1,000 | 0,685 | 0,000 | 0,500 |
| L2 | score2 | tipos_l2 | 1,000 | 4,000 | 2,000 | 0,500 |
| L2 | score3 | tipos_l2 | 1,000 | 3,851 | 2,134 | 0,500 |
| L2 | score3#1 | tipos_l2 | 1,000 | 0,756 | 0,000 | 0,500 |
| L2 | score4 | tipos_l2 | 1,000 | 3,942 | 2,048 | 0,500 |
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

τ de L2: tau_escalate = 0,895, tau_l2_esquema_nuevo = 0,846
AVISO: la CALIB de L2 no trae multi: esa capa usa parámetros por defecto o no opina en esos tipos.
