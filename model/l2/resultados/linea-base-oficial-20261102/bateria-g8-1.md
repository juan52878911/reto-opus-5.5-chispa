# Batería de regresión: bateria-chispa

Fuente: `/opt/chispa/g8.chispa` · objetivo de precisión: 0,95 · 2026-11-02T19:09:55

## Global
|  | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | incompletas | sin presup. torres | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| global | 11000 | 0,644 | 0,976 | 0,104 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 89,4 % | 0,577 | 0,113 | 33,1 % | 89,4 % | 0,0 % | 21,4 | 176,0 |

## Por tipo
| tipo | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | incompletas | sin presup. torres | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| choice | 8981 | 0,608 | 0,976 | 0,126 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 87,1 % | 0,586 | 0,109 | 28,0 % | 87,1 % | 0,0 % | 20,8 | 61,3 |
| noul | 2001 | 0,807 | 1,000 | 0,006 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 99,4 % | 0,596 | 0,132 | 56,6 % | 99,4 % | 0,0 % | 30,4 | 193,7 |
| score | 18 | 0,111 | sin medir | 0,000 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 100,0 % | 0,153 | 0,259 | 0,0 % | 100,0 % | 0,0 % | 24,5 | 212,7 |

## Por grupo
| grupo | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | incompletas | sin presup. torres | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | 0,489 | 0,900 | 0,078 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 91,3 % | 0,484 | 0,086 | 5,2 % | 91,3 % | 0,0 % | 120,6 | 297,6 |
| prueba | 10769 | 0,647 | 0,977 | 0,104 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 89,3 % | 0,639 | 0,115 | 34,0 % | 89,3 % | 0,0 % | 21,3 | 38,4 |

## Por conjunto
| conjunto | n | exactitud (argmax) | exact. contestada | exact. estricta | sin probs | nadie opinó | incompletas | sin presup. torres | baja confianza | F1 macro | ECE | cobertura a 0,95 | escalado | errores | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jevbench | 231 | 0,489 | 0,900 | 0,078 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 91,3 % | 0,484 | 0,086 | 5,2 % | 91,3 % | 0,0 % | 120,6 | 297,6 |
| massive | 2974 | 0,413 | 0,891 | 0,038 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 95,7 % | 0,344 | 0,025 | 2,1 % | 95,7 % | 0,0 % | 20,5 | 26,8 |
| clinc150 | 5500 | 0,715 | 0,989 | 0,171 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 82,7 % | 0,763 | 0,162 | 51,5 % | 82,7 % | 0,0 % | 20,7 | 29,1 |
| hatecheck | 361 | 0,476 | sin medir | 0,000 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 100,0 % | 0,465 | 0,105 | 0,3 % | 100,0 % | 0,0 % | 24,0 | 39,3 |
| spam | 1450 | 0,926 | 1,000 | 0,008 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 99,2 % | 0,926 | 0,222 | 93,0 % | 99,2 % | 0,0 % | 31,1 | 40,8 |
| inyecciones | 116 | 0,491 | sin medir | 0,000 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 100,0 % | 0,344 | 0,201 | 18,1 % | 100,0 % | 0,0 % | 35,2 | 72,7 |
| herramientas | 368 | 0,633 | 0,968 | 0,163 | 0,0 % | 0,0 % | 0,0 % | 0,0 % | 83,2 % | 0,609 | 0,099 | 24,7 % | 83,2 % | 0,0 % | 26,7 | 31,0 |

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
